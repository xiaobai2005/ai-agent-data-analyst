# 05 · API 文档（FastAPI）

启动后端后访问 **http://localhost:8000/docs** 可查看交互式 Swagger 文档。
本文补充请求示例与 SSE 事件格式。

## 1. 接口总览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查（返回已注册工具数） |
| POST | `/upload` | CSV 上传（multipart/form-data） |
| POST | `/chat` | 对话（一次性返回结果） |
| POST | `/chat/stream` | 对话（**SSE 流式**推送推理过程） |
| GET | `/tools` | 已注册工具列表（含风险等级） |
| GET | `/logs/{session_id}` | 指定会话的执行日志 |
| POST | `/confirm` | HITL 高风险操作二次确认 |
| GET | `/reports` | 已生成的 Markdown 报告列表 |
| GET | `/reports/{filename}` | 下载指定报告 |

## 2. 请求 / 响应示例

### GET /health

```bash
curl http://localhost:8000/health
# {"status":"ok","tools":11}
```

### POST /upload

```bash
curl -F "file=@demo.csv" http://localhost:8000/upload
# {"path":"uploads/demo.csv","filename":"demo.csv"}
```

### GET /tools

```bash
curl http://localhost:8000/tools
# {"count":11,"tools":[{"name":"profile_csv","description":"...","risk":"low"}, ...]}
```

### POST /chat

```bash
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d '{
  "session_id": "s1",
  "message": "按地区统计销量总和",
  "csv_path": "demo.csv"
}'
```

```json
{
  "reply": "各地区销量总和：上海 83 / 北京 81 / 广州 54 ...",
  "images": ["http://localhost:8000/charts/chart_bar_region_a1b2c3d4.png"],
  "steps": [
    {"tool": "stats_group_agg",
     "args": "{\"csv_path\": \"demo.csv\", \"group_by\": \"region\", \"column\": \"quantity\"}",
     "latency_ms": 3,
     "summary": "   sum   mean\nregion ..."}
  ],
  "tokens": {"prompt": 5076, "completion": 334, "total": 5410},
  "needs_confirm": false,
  "confirm_payload": null
}
```

### GET /logs/{session_id}

```bash
curl http://localhost:8000/logs/s1
# {"session_id":"s1","logs":[{"time":"...","user":"...","reply":"...","images":[]}]}
```

### POST /confirm（HITL）

```bash
curl -X POST http://localhost:8000/confirm -H "Content-Type: application/json" \
     -d '{"session_id":"s1"}'
# {"ok":true,"msg":"已删除文件: uploads/demo.csv"}
```

## 3. SSE 流式接口 `POST /chat/stream`

请求体与 `/chat` 相同，响应为 `text/event-stream`，每帧形如 `data: {json}\n\n`，
结束时发送 `data: [DONE]\n\n`。

### 事件类型

| type | 字段 | 含义 |
|---|---|---|
| `thought` | `text` | 模型的思考内容 |
| `action` | `tool`, `args` | 准备调用的工具与参数 |
| `observation` | `tool`, `text` | 工具返回的结果（截断 500 字符） |
| `final` | `reply`, `images`, `steps`, `tokens`, `needs_confirm` | 最终回答与统计 |
| `error` | `text` | 执行异常 |

### Python 消费示例

```python
import json, requests

with requests.post("http://localhost:8000/chat/stream",
                   json={"session_id": "s1", "message": "按地区画柱状图",
                         "csv_path": "demo.csv"},
                   stream=True, timeout=300) as r:
    for line in r.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        ev = json.loads(data)
        print(ev["type"], str(ev.get("text") or ev.get("tool") or "")[:80])
```

### 浏览器消费示例（fetch + ReadableStream）

```javascript
const res = await fetch("http://localhost:8000/chat/stream", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ session_id: "s1", message: "按地区画柱状图", csv_path: "demo.csv" }),
});
const reader = res.body.getReader();
const decoder = new TextDecoder("utf-8");
let buf = "";
while (true) {
  const { value, done } = await reader.read();
  if (done) break;
  buf += decoder.decode(value, { stream: true });
  const frames = buf.split("\n\n");
  buf = frames.pop();
  for (const f of frames) {
    const line = f.trim();
    if (!line.startsWith("data:")) continue;
    const payload = line.slice(5).trim();
    if (payload === "[DONE]") { console.log("结束"); continue; }
    const ev = JSON.parse(payload);
    console.log(ev.type, ev);
  }
}
```

> 注：浏览器原生 `EventSource` 只支持 GET，SSE 的 POST 场景请用上面的 `fetch` 方式。

## 4. 错误约定

- HTTP 200 + `reply` 内含错误文本：Agent/工具内部异常（后端统一兜底，保证前端不崩）
- HTTP 422：请求体字段缺失或类型错误（Pydantic 校验）
- HTTP 500：未捕获的服务端异常（详见后端日志）

## 5. 前端对接要点

- 图表 URL：后端会把 Markdown 中的 `charts/xxx.png` 重写为 `<base_url>/charts/xxx.png`，
  前端无需再拼域名；`images` 字段同样是绝对 URL
- 前端通过环境变量 `API_URL` 指定后端地址（云端部署必填）
- 会话隔离靠 `session_id`，多轮追问需传同一个 `session_id`
