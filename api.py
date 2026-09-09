# ============ FastAPI 后端 ============
# 接口清单（方案 Day5 任务 19）：
#   GET  /health            健康检查
#   POST /upload            CSV 上传入库（防路径穿越）
#   POST /chat              对话（一次性返回结果）
#   POST /chat/stream       对话（SSE 流式推送 Thought/Action/Observation）
#   GET  /tools             已注册工具列表（含风险等级）
#   GET  /logs/{session_id} 指定会话的执行日志
#   POST /confirm           HITL 高风险操作二次确认
#   GET  /reports           已生成的 Markdown 报告列表
# 启动：uvicorn api:app --reload --port 8000
# 文档：http://localhost:8000/docs

import json
import os
import re

import agent
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# 运行期产物目录：缺失时自动创建（避免静态挂载 / 首次写文件报错）
for _d in ("charts", "uploads", "data", "reports"):
    os.makedirs(_d, exist_ok=True)

app = FastAPI(
    title="AI Agent 智能任务编排平台 · 数据分析助手 API",
    version="1.0.0",
    description="上传 CSV → 自然语言提问 → Agent 自主规划、调用工具分析并输出报告（含 SSE 推理流）",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# 把 charts 挂载成静态资源，前端靠 URL 直接展示图表
app.mount("/charts", StaticFiles(directory="charts"), name="charts")


# ============ 请求 / 响应模型 ============
class ChatRequest(BaseModel):
    session_id: str                 # 会话 ID（前端按会话隔离记忆）
    message: str                    # 用户问题
    csv_path: str = ""              # 当前数据文件；空串表示未加载


class ChatResponse(BaseModel):
    reply: str
    images: list[str] = []
    steps: list[dict] = []
    tokens: dict = {"prompt": 0, "completion": 0, "total": 0}
    needs_confirm: bool = False
    confirm_payload: dict | None = None


class ConfirmRequest(BaseModel):
    session_id: str


def _to_abs_urls(result: dict, base: str) -> tuple[str, list[str]]:
    """把 Markdown 与 images 里的相对路径 charts/xxx.png 改写成可访问的绝对 URL"""
    reply = re.sub(
        r"(!\[[^\]]*\]\()charts/([^\s\)]+)(\))",
        lambda m: f"{m.group(1)}{base}/charts/{m.group(2)}{m.group(3)}",
        result.get("reply", "") or "",
    )
    urls = []
    for img in result.get("images", []) or []:
        norm = str(img).replace("\\", "/")
        if norm.startswith("charts/"):
            urls.append(f"{base}/{norm}")
        elif norm.startswith("/charts/"):
            urls.append(f"{base}{norm}")
        else:
            urls.append(f"{base}/{norm.lstrip('/')}")
    return reply, urls


# ============ 健康检查 ============
@app.get("/health")
def health():
    return {"status": "ok", "tools": len(agent.REGISTERED_TOOLS)}


# ============ 对话（一次性返回）============
@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest, request: Request):
    # 兜底：任何未捕获异常都转成 JSON，避免返回纯文本 500 导致前端 .json() 报错
    try:
        result = agent.chat(req.session_id, req.message, req.csv_path)
    except Exception as e:
        return ChatResponse(reply=f"后端处理出错：{type(e).__name__}: {e}")

    base = str(request.base_url).rstrip("/")
    reply, urls = _to_abs_urls(result, base)
    return ChatResponse(
        reply=reply,
        images=urls,
        steps=result.get("steps", []),
        tokens=result.get("tokens", {"prompt": 0, "completion": 0, "total": 0}),
        needs_confirm=result.get("needs_confirm", False),
        confirm_payload=result.get("confirm_payload"),
    )


# ============ 对话（SSE 流式推送推理过程）============
@app.post("/chat/stream")
def chat_stream_endpoint(req: ChatRequest, request: Request):
    """SSE 流：依次推送 thought / action / observation / final 事件

    星眠（Starlette）会把同步生成器放到线程池执行，因此这里可以直接写阻塞的 Agent 调用。
    前端解析示例见 docs/API文档.md。
    """
    base = str(request.base_url).rstrip("/")

    def gen():
        try:
            for ev in agent.stream_chat(req.session_id, req.message, req.csv_path):
                if ev.get("type") == "final":
                    reply, urls = _to_abs_urls(ev, base)
                    ev = {**ev, "reply": reply, "images": urls}
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ============ 工具列表 ============
@app.get("/tools")
def tools_endpoint():
    return {"count": len(agent.tool_catalog()), "tools": agent.tool_catalog()}


# ============ 执行日志 ============
@app.get("/logs/{session_id}")
def logs_endpoint(session_id: str):
    return {"session_id": session_id, "logs": agent.get_logs(session_id)}


# ============ CSV 上传 ============
@app.post("/upload")
def upload_endpoint(file: UploadFile = File(...)):
    os.makedirs("uploads", exist_ok=True)
    # 防路径穿越：只取文件名，拼到 uploads/ 下
    name = os.path.basename(file.filename or "upload.csv")
    if not name.lower().endswith(".csv"):
        name += ".csv"
    path = os.path.join("uploads", name)
    with open(path, "wb") as f:
        f.write(file.file.read())
    return {"path": path, "filename": name}


# ============ HITL 确认 ============
@app.post("/confirm")
def confirm_endpoint(req: ConfirmRequest):
    return agent.confirm_action(req.session_id)


# ============ 报告列表 / 下载 ============
@app.get("/reports")
def reports_endpoint():
    os.makedirs("reports", exist_ok=True)
    files = sorted(os.listdir("reports"))
    return {"reports": [f for f in files if f.endswith(".md")]}


@app.get("/reports/{filename}")
def report_download(filename: str):
    path = os.path.join("reports", os.path.basename(filename))
    if not os.path.exists(path):
        return {"error": "报告不存在"}
    return FileResponse(path, media_type="text/markdown", filename=filename)
