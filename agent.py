# ============ Agent 主体 ============
# 职责：System Prompt 组装 / 工具注册 / ReAct 推理循环
#      / 推理步骤与 Token 采集 / SSE 流式事件 / HITL 人工确认
#
# 执行范式：ReAct（Thought → Action → Observation 循环）
#   一次性调用：POST /chat          → invoke_once()
#   流式推送  ：POST /chat/stream   → iter_react_events() 逐步产出 thought/action/observation

import json
import os
import re
import time

from langchain.agents import create_agent
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from llm import llm
from tools.registry import get_tools, prompt_catalog

# ============ System Prompt ============
# {tool_catalog} 由 tools/registry.py 自动生成：新增工具无需改这里，自动写进 Prompt
SYSTEM_PROMPT = """你是一个「智能数据分析助手」AI Agent，基于 ReAct 范式工作：
Thought（思考）→ Action（选工具并给出参数）→ Observation（看工具返回结果）→ 循环，直到能回答为止。

【可用工具清单】（自动注册，禁止调用清单以外的工具）
{tool_catalog}

【当前数据文件】
{csv_path}
除非用户明确更换文件，否则后续所有分析都基于上面的文件。若文件路径为空，请提示用户先上传 CSV。

【数据画像】（系统已自动解析，分析时优先参考其中的列名 / 类型 / 缺失值）
{profile}

【工作准则】
1. 先理解用户意图，再决定调用哪些工具；所有数字必须来自工具返回结果，禁止编造。
2. 多步任务要自主拆解：例如"对比两月趋势找异常"→ 先聚合，再画图，最后给结论。
3. 最终回复结构化：关键发现 + 具体数字 + 简短建议。
4. 若用户要求出图，调用 make_chart；要求"报告"时调用 report_tool 生成 Markdown 报告。
5. 多轮追问（"换成饼图""加上环比"）要参考上下文中的上一轮结果。
6. 工具报错时，读取错误提示里的可用列名并自我纠正，最多重试 2 次；仍失败则如实说明。

【图表插入规则（重要，否则前端无法显示图）】
- 每次调用 make_chart 后，必须在最终回复的对应段落正文里，紧贴分析文字，用 Markdown 图片语法引用：
  ![产品销量饼图](charts/chart_pie_product_xxxxxxxx.png)
- 路径取 make_chart 返回值中 "图表已保存:" 后面的相对路径（charts/...png），不要带域名。
"""


# ============ 创建 Agent（工具来自注册中心，新增工具自动生效）============
REGISTERED_TOOLS = get_tools()
agent = create_agent(model=llm, tools=REGISTERED_TOOLS)


def build_system_text(csv_path: str, profile: str, extra: str = "") -> str:
    """组装本轮的 System Prompt（工具清单 / 数据文件 / 数据画像 / 消融用额外提示）"""
    text = SYSTEM_PROMPT.format(
        tool_catalog=prompt_catalog(),
        csv_path=csv_path or "（未加载）",
        profile=profile or "（暂无）",
    )
    return text + ("\n" + extra if extra else "")


# ============ 会话记忆（内存字典，重启即丢；生产环境建议换 Redis）============
# _sessions: session_id -> 消息历史（不含每轮重复注入的 system 消息）
# _context:  session_id -> 当前数据文件路径
_sessions: dict = {}
_context: dict = {}
_profiles: dict = {}     # session_id -> 已生成的数据画像文本（文件变化才重算）
_pending: dict = {}      # session_id -> 待 HITL 确认的高风险操作
_logs: dict = {}         # session_id -> 执行日志列表（供 GET /logs 查看）

# HITL 关键词：命中"删除意图 + 文件对象"即视为高风险操作，需人工确认
_DELETE_RE = re.compile(r"(删除|del|remove|清除|清空|drop)", re.IGNORECASE)
_FILE_RE = re.compile(r"(文件|csv|数据|上传|表|记录|资料)", re.IGNORECASE)

# 响应体统一结构（Pydantic 之外的兜底：保证任何分支字段都不缺失）
EMPTY_TOKENS = {"prompt": 0, "completion": 0, "total": 0}


class StepCollector(BaseCallbackHandler):
    """回调器：记录每次工具调用的名称 / 入参 / 耗时 / 结果摘要（供前端推理时间轴）"""

    def __init__(self):
        self.steps: list[dict] = []
        self._running: dict = {}

    def on_tool_start(self, serialized, input_str, **kwargs):
        name = (serialized or {}).get("name", "unknown")
        self._running[kwargs.get("run_id")] = (name, input_str, time.time())

    def on_tool_end(self, output, **kwargs):
        info = self._running.pop(kwargs.get("run_id"), None)
        if not info:
            return
        name, inp, t0 = info
        self.steps.append({
            "tool": name,
            "args": inp,
            "latency_ms": int((time.time() - t0) * 1000),
            "summary": str(output)[:300],
        })


def _collect_tokens(messages) -> dict:
    """从消息里累计 Token 用量（prompt / completion / total）"""
    prompt = completion = 0
    seen = set()          # 同一条消息可能在流式 update 中重复出现，按 id 去重
    for m in messages:
        mid = id(m)
        if mid in seen:
            continue
        seen.add(mid)
        um = getattr(m, "usage_metadata", None)
        if not um:
            continue
        if isinstance(um, dict):
            prompt += int(um.get("input_tokens") or 0)
            completion += int(um.get("output_tokens") or 0)
        else:
            prompt += int(getattr(um, "input_tokens", 0) or 0)
            completion += int(getattr(um, "output_tokens", 0) or 0)
    return {"prompt": prompt, "completion": completion, "total": prompt + completion}


def _extract_images(messages) -> list[str]:
    """从工具消息里解析本轮新生成的图表路径（替代目录 diff，避免并发竞态）"""
    images = []
    for m in messages:
        text = str(getattr(m, "content", "") or "")
        if text.startswith("图表已保存:"):
            p = text.split(":", 1)[1].strip()
            if os.path.exists(p) and p not in images:
                images.append(p)
    return images


def _last_ai_text(messages) -> str:
    """取最后一条有文本内容的 AI 消息作为最终回答"""
    for m in reversed(messages):
        if isinstance(m, AIMessage):
            text = m.content
            if isinstance(text, list):          # 部分模型返回分块列表
                text = "".join(
                    c.get("text", "") for c in text if isinstance(c, dict)
                )
            if text and text.strip():
                return text
    return ""


def invoke_once(messages: list) -> dict:
    """跑一次完整的 ReAct 循环（框架托管 思考→调用工具→回填→继续）"""
    collector = StepCollector()
    result = agent.invoke({"messages": messages}, config={"callbacks": [collector]})
    raw = result["messages"]
    return {
        "reply": _last_ai_text(raw) or "（模型没有返回文本）",
        "images": _extract_images(raw),
        "steps": collector.steps,
        "tokens": _collect_tokens(raw),
        "messages": raw,
    }


def iter_react_events(messages: list):
    """以生成器方式产出 ReAct 每一步事件，供 SSE 流式推送（方案 Day5 要求）

    事件类型：
      thought      模型的思考文本
      action       准备调用的工具与参数
      observation  工具返回的结果摘要
      final        最终回答 + 图表 + 步骤 + Token 统计
      error        执行过程中的异常
    """
    collector = StepCollector()
    collected: list = []
    try:
        for chunk in agent.stream(
            {"messages": messages},
            config={"callbacks": [collector]},
            stream_mode="updates",
        ):
            for _node, update in chunk.items():
                for m in (update or {}).get("messages") or []:
                    collected.append(m)
                    if isinstance(m, AIMessage):
                        if m.content:
                            yield {"type": "thought", "text": str(m.content)}
                        for tc in (m.tool_calls or []):
                            yield {
                                "type": "action",
                                "tool": tc.get("name", ""),
                                "args": tc.get("args", {}),
                            }
                    elif isinstance(m, ToolMessage):
                        yield {
                            "type": "observation",
                            "tool": m.name or "",
                            "text": str(m.content)[:500],
                        }
    except Exception as e:
        yield {"type": "error", "text": f"{type(e).__name__}: {e}"}

    yield {
        "type": "final",
        "reply": _last_ai_text(collected) or "（模型没有返回文本）",
        "images": _extract_images(collected),
        "steps": collector.steps,
        "tokens": _collect_tokens(collected),
    }


# ============ 对外主入口 ============
def _ensure_profile(session_id: str, csv_path: str) -> str:
    """文件首次加载或发生变化时重新生成数据画像（上传即画像）"""
    prev = _context.get(session_id)
    _context[session_id] = csv_path
    if _profiles.get(session_id) is None or prev != csv_path:
        try:
            from tools.profile_tool import profile_csv
            _profiles[session_id] = profile_csv.invoke({"csv_path": csv_path})
        except Exception:
            _profiles[session_id] = "(数据画像生成失败，请检查文件路径)"
    return _profiles[session_id]


def chat(session_id: str, user_input: str, csv_path: str = "",
         system_extra: str = "") -> dict:
    """处理一轮对话（ReAct 循环），返回 reply / images / steps / tokens / needs_confirm"""
    # ---------- 守门：未加载数据文件时直接提示，避免下游误读 ----------
    csv_path = (csv_path or "").strip()
    if not csv_path:
        return {
            "reply": "⚠️ 尚未加载数据文件。请先在左侧【上传 CSV】，或点击「使用示例数据」加载 demo.csv。",
            "images": [], "steps": [], "tokens": dict(EMPTY_TOKENS),
            "needs_confirm": False, "confirm_payload": None,
        }

    # ---------- HITL 预检：高风险"删除文件"类操作先暂停等人工确认 ----------
    if _DELETE_RE.search(user_input) and _FILE_RE.search(user_input):
        _pending[session_id] = {"action": "delete_file", "path": csv_path}
        return {
            "reply": "⚠️ 检测到高风险操作（删除文件），已按安全护栏暂停。"
                     "请在前端点击【确认执行】；忽略即可取消。",
            "images": [], "steps": [], "tokens": dict(EMPTY_TOKENS),
            "needs_confirm": True,
            "confirm_payload": {"action": "delete_file", "path": csv_path},
        }

    profile = _ensure_profile(session_id, csv_path)
    sys_text = build_system_text(csv_path, profile, system_extra)
    history = _sessions.setdefault(session_id, [])
    history.append({"role": "user", "content": user_input})

    # ---------- ReAct 推理循环 ----------
    try:
        result = invoke_once([SystemMessage(content=sys_text)] + history)
    except Exception as e:
        result = {"reply": f"Agent 执行失败：{type(e).__name__}: {e}",
                  "images": [], "steps": [], "tokens": dict(EMPTY_TOKENS),
                  "messages": []}

    # 存回历史：只保留 user/ai/tool 消息（system 每轮动态注入，避免堆积）
    if result.get("messages"):
        _sessions[session_id] = list(result["messages"])[1:] or history
    _append_log(session_id, user_input, result["reply"], result["images"])

    return {
        "reply": result["reply"],
        "images": result["images"],
        "steps": result["steps"],
        "tokens": result["tokens"],
        "needs_confirm": False,
        "confirm_payload": None,
    }


def stream_chat(session_id: str, user_input: str, csv_path: str = "",
                system_extra: str = ""):
    """chat() 的流式版本：以生成器逐步产出 ReAct 事件，供 SSE 接口推送"""
    csv_path = (csv_path or "").strip()
    if not csv_path:
        yield {"type": "error", "text": "⚠️ 尚未加载数据文件，请先上传 CSV。"}
        yield {"type": "final", "reply": "⚠️ 尚未加载数据文件。请先在左侧【上传 CSV】，"
                                         "或点击「使用示例数据」加载 demo.csv。",
               "images": [], "steps": [], "tokens": dict(EMPTY_TOKENS)}
        return

    if _DELETE_RE.search(user_input) and _FILE_RE.search(user_input):
        _pending[session_id] = {"action": "delete_file", "path": csv_path}
        yield {"type": "final",
               "reply": "⚠️ 检测到高风险操作（删除文件），已按安全护栏暂停。",
               "images": [], "steps": [], "tokens": dict(EMPTY_TOKENS),
               "needs_confirm": True,
               "confirm_payload": {"action": "delete_file", "path": csv_path}}
        return

    profile = _ensure_profile(session_id, csv_path)
    sys_text = build_system_text(csv_path, profile, system_extra)
    history = _sessions.setdefault(session_id, [])
    history.append({"role": "user", "content": user_input})

    for ev in iter_react_events([SystemMessage(content=sys_text)] + history):
        if ev["type"] == "final":
            history.append({"role": "assistant", "content": ev["reply"]})
            _append_log(session_id, user_input, ev["reply"], ev["images"])
        yield ev


def _append_log(session_id: str, user_input: str, reply: str, images: list):
    """记录执行日志，供 GET /logs/{session_id} 查询"""
    _logs.setdefault(session_id, []).append({
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "user": user_input,
        "reply": reply,
        "images": images,
    })


# ============ 供 API 层调用的辅助函数 ============
def tool_catalog() -> list[dict]:
    """返回已注册工具元信息，供 GET /tools"""
    return [{"name": t.name,
             "description": (t.description or "").strip(),
             "risk": (t.metadata or {}).get("risk", "low")}
            for t in REGISTERED_TOOLS]


def get_logs(session_id: str) -> list:
    """返回某会话的执行日志，供 GET /logs/{session_id}"""
    return _logs.get(session_id, [])


def confirm_action(session_id: str) -> dict:
    """执行待确认的高风险操作（HITL 确认后由 POST /confirm 调用）"""
    pending = _pending.pop(session_id, None)
    if not pending:
        return {"ok": False, "msg": "当前没有待确认的操作"}
    if pending["action"] == "delete_file":
        try:
            os.remove(pending["path"])
            return {"ok": True, "msg": f"已删除文件: {pending['path']}"}
        except Exception as e:
            return {"ok": False, "msg": f"删除失败: {e}"}
    return {"ok": False, "msg": "未知操作类型"}


if __name__ == "__main__":
    # 命令行自测：python agent.py "各地区的销量总和是多少？"
    import sys

    q = sys.argv[1] if len(sys.argv) > 1 else "这个文件有哪些列？"
    r = chat(session_id="cli", user_input=q, csv_path="demo.csv")
    print("【工具清单】", json.dumps([t["name"] for t in tool_catalog()], ensure_ascii=False))
    print("【回答】\n", r["reply"])
    print("【步骤】", [(s["tool"], s["latency_ms"]) for s in r["steps"]])
    print("【Token】", r["tokens"])
