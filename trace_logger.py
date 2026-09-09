# ============ 推理轨迹落盘模块（日志可追溯）============
# 每轮对话写一条 JSONL 记录到 logs/trace_YYYYMMDD.jsonl：
#   完整推理过程（Thought / Action / Observation）+ 工具步骤 + Token + 耗时 + 最终回答
# 设计要点：
#   1. 按天切分文件：避免单文件无限增长，便于按日期归档与回溯
#   2. 线程安全：eval.py 会多线程并发调用 agent.chat，用 Lock 保证"一行写入"的原子性
#   3. 体积控制：长文本截断，避免大表格把日志撑爆
#   4. 绝不阻塞主流程：落盘失败只告警，不影响对话

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

LOG_DIR = os.getenv("TRACE_LOG_DIR", "logs")
FILE_PREFIX = "trace_"
FILE_SUFFIX = ".jsonl"

# 单条事件文本截断长度（字符）
MAX_THOUGHT = 2000
MAX_OBSERVATION = 1000
MAX_ARGS = 1000
MAX_REPLY = 4000

# 读取时默认回溯的天数（date 为空时，从今天往前找这么多天）
DEFAULT_LOOKBACK_DAYS = 7

_lock = threading.Lock()


def _ensure_dir() -> None:
    os.makedirs(LOG_DIR, exist_ok=True)


def today_file(date: str = "") -> str:
    """返回当天（或指定日期 YYYYMMDD）的日志文件路径"""
    _ensure_dir()
    day = date or time.strftime("%Y%m%d")
    return os.path.join(LOG_DIR, f"{FILE_PREFIX}{day}{FILE_SUFFIX}")


def list_dates() -> list[str]:
    """列出已产生日志的日期列表（YYYYMMDD，新的在前）"""
    if not os.path.isdir(LOG_DIR):
        return []
    days = []
    for name in os.listdir(LOG_DIR):
        if name.startswith(FILE_PREFIX) and name.endswith(FILE_SUFFIX):
            days.append(name[len(FILE_PREFIX):-len(FILE_SUFFIX)])
    return sorted(days, reverse=True)


def _clip(text: Any, limit: int) -> str:
    s = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False, default=str)
    return s if len(s) <= limit else s[:limit] + f" …[截断 {len(s) - limit} 字符]"


def _normalize_event(ev: dict) -> dict:
    """把 SSE 事件规整成可落盘的结构，并做长度控制"""
    t = ev.get("type", "")
    out = {"type": t}
    if t == "thought":
        out["text"] = _clip(ev.get("text", ""), MAX_THOUGHT)
    elif t == "action":
        out["tool"] = ev.get("tool", "")
        out["args"] = _clip(ev.get("args", {}), MAX_ARGS)
    elif t == "observation":
        out["tool"] = ev.get("tool", "")
        out["text"] = _clip(ev.get("text", ""), MAX_OBSERVATION)
    elif t == "error":
        out["text"] = _clip(ev.get("text", ""), MAX_THOUGHT)
    elif t == "final":
        out["reply"] = _clip(ev.get("reply", ""), MAX_REPLY)
        out["images"] = ev.get("images", []) or []
        out["steps"] = ev.get("steps", []) or []
        out["tokens"] = ev.get("tokens", {}) or {}
    return out


def build_record(session_id: str, question: str, csv_path: str = "",
                 mode: str = "once", events: list[dict] | None = None,
                 steps: list[dict] | None = None, tokens: dict | None = None,
                 reply: str = "", images: list[str] | None = None,
                 latency_ms: int = 0, error: str = "") -> dict:
    """构造一条轨迹记录（字段向后兼容旧的 /logs 结构）"""
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    events = events or []
    steps = steps or []
    images = images or []
    return {
        # ---- 新增：完整推理轨迹 ----
        "ts": now,
        "session_id": session_id,
        "mode": mode,                                  # once（一次性） / stream（SSE）
        "csv_path": csv_path,
        "events": [_normalize_event(e) for e in events],
        "steps": steps,
        "tokens": tokens or {"prompt": 0, "completion": 0, "total": 0},
        "latency_ms": int(latency_ms or 0),
        "error": error or "",
        "event_count": len(events),
        "tool_count": len(steps),
        # ---- 旧字段：保证已有调用方与前端不受影响 ----
        "time": now,
        "user": question,
        "reply": _clip(reply, MAX_REPLY),
        "images": images,
    }


def write_trace(record: dict) -> str:
    """追加写入一条轨迹记录，返回落盘文件路径；失败只告警不抛异常"""
    path = today_file()
    try:
        _ensure_dir()
        line = json.dumps(record, ensure_ascii=False, default=str)
        # 锁只包住"写入"这一步（不包住 LLM 调用），保证并发下行不串行
        with _lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        return path
    except Exception as e:      # 落盘失败绝不能影响对话主流程
        print(f"[trace_logger] 写入失败（已忽略）: {type(e).__name__}: {e}")
        return ""


def read_traces(session_id: str = "", date: str = "", limit: int = 50,
                lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> list[dict]:
    """读取轨迹记录：按 session_id 过滤，最新在前

    date 为空时，从今天往前回溯 lookback_days 天，直到凑够 limit 条。
    """
    days = [date] if date else list_dates()[:max(1, lookback_days)]
    if not days:
        days = [time.strftime("%Y%m%d")]

    out: list[dict] = []
    for day in days:
        path = today_file(day)
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    if session_id and rec.get("session_id") != session_id:
                        continue
                    out.append(rec)
        except Exception as e:
            print(f"[trace_logger] 读取失败 {path}: {e}")
    # 最新在前；同秒内按写入顺序保持（不做稳定排序，足够回溯使用）
    out.sort(key=lambda r: r.get("ts") or r.get("time") or "", reverse=True)
    return out[:limit] if limit > 0 else out


if __name__ == "__main__":
    # 自检：python trace_logger.py  → 写一条示例并读回
    rec = build_record(session_id="selftest", question="自检问题", csv_path="demo.csv",
                       mode="once",
                       events=[{"type": "thought", "text": "思考中"},
                               {"type": "action", "tool": "calculator", "args": {"expression": "1+1"}},
                               {"type": "observation", "tool": "calculator", "text": "2"}],
                       steps=[{"tool": "calculator", "latency_ms": 1, "summary": "2"}],
                       tokens={"prompt": 10, "completion": 2, "total": 12},
                       reply="答案是 2", latency_ms=120)
    print("写入:", write_trace(rec))
    print("读回:", json.dumps(read_traces(session_id="selftest", limit=1),
                              ensure_ascii=False)[:300])
