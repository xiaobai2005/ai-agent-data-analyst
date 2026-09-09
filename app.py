# ============ 智能数据分析助手 · Streamlit 前端 ============
# 交互与后端接口保持不变：多会话 / 推理轨迹 / Token 用量 / HITL 二次确认
# 视觉：绘图纸工作台 —— 网格底纹 + 墨蓝正文 + 技术笔青 + IBM Plex 字体族

import html
import json
import os
import re
import time
import uuid

import requests
import streamlit as st

# 后端地址可用环境变量覆盖，方便部署到云端 / 容器（例：API_URL=http://1.2.3.4:8000）
API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="智能数据分析助手",
    page_icon="📐",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------- 全局样式：绘图纸（graph paper）工作台 ----------------
CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Sans+SC:wght@400;500;600&display=swap');

:root{
  --paper:      #E7E9E5;   /* 绘图纸底 */
  --paper-2:    #F3F4F1;   /* 卡面 / 面板 */
  --paper-3:    #FBFCFA;   /* 图版 / 输入面 */
  --ink:        #16222C;   /* 主墨色 */
  --ink-2:      #5A6A72;   /* 次级文字 */
  --ink-3:      #8A969C;   /* 标签 / 弱化 */
  --rule:       rgba(22,34,44,.14);
  --rule-2:     rgba(22,34,44,.28);
  --signal:     #0B7C74;   /* 技术笔青 */
  --signal-2:   #095F59;
  --signal-bg:  rgba(11,124,116,.10);
  --alert:      #A93A25;   /* 红笔批注 */
  --amber:      #B07A15;
  --mono: 'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  --sans: 'IBM Plex Sans','IBM Plex Sans SC', -apple-system, 'Segoe UI', 'Microsoft YaHei', sans-serif;
}

/* --- 网格底：细格 16px + 粗格 80px --- */
[data-testid="stAppViewContainer"]{
  background-color: var(--paper);
  background-image:
    linear-gradient(rgba(22,34,44,.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(22,34,44,.045) 1px, transparent 1px),
    linear-gradient(rgba(22,34,44,.085) 1px, transparent 1px),
    linear-gradient(90deg, rgba(22,34,44,.085) 1px, transparent 1px);
  background-size: 16px 16px, 16px 16px, 80px 80px, 80px 80px;
  color: var(--ink);
  font-family: var(--sans);
}
[data-testid="stSidebar"]{
  background-color: #DFE2DD;
  background-image:
    linear-gradient(rgba(22,34,44,.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(22,34,44,.05) 1px, transparent 1px);
  background-size: 16px 16px, 16px 16px;
  border-right: 1px solid var(--rule-2);
}
[data-testid="stHeader"]{ background: transparent; }
#MainMenu{ visibility: hidden; }
footer{ visibility: hidden; }
.block-container{ padding-top: 2.4rem; padding-bottom: 7rem; max-width: 1480px; }

/* --- 基础排版 --- */
[data-testid="stAppViewContainer"] p,
[data-testid="stAppViewContainer"] li,
[data-testid="stAppViewContainer"] span{ color: var(--ink); }
h1,h2,h3,h4{ font-family: var(--sans) !important; color: var(--ink) !important; letter-spacing: -.01em; }

/* --- 面板 / 卡片 --- */
.panel{
  background: var(--paper-2);
  border: 1px solid var(--rule);
  border-radius: 2px;
  padding: 14px 16px;
  margin-bottom: 14px;
  box-shadow: 0 1px 0 rgba(22,34,44,.05);
}
.panel-title{
  font-family: var(--mono); font-size: 11px; font-weight: 600;
  letter-spacing: .18em; text-transform: uppercase; color: var(--ink-2);
  padding-bottom: 8px; margin-bottom: 12px; border-bottom: 1px solid var(--rule);
  display: flex; justify-content: space-between; align-items: baseline; gap: 8px;
}
.panel-title .cnt{ color: var(--signal); font-weight: 500; letter-spacing: .1em; }

/* --- 品牌 / 页头 --- */
.eyebrow{
  font-family: var(--mono); font-size: 10.5px; font-weight: 500;
  letter-spacing: .22em; text-transform: uppercase; color: var(--ink-2);
}
.brand-title{
  font-size: 21px; font-weight: 600; letter-spacing: -.015em;
  color: var(--ink); margin: 6px 0 2px;
}
.brand-title::after{
  content: ""; display: block; width: 34px; height: 3px;
  background: var(--signal); margin-top: 8px; border-radius: 1px;
}
.muted{ color: var(--ink-2); font-size: 13px; line-height: 1.6; }
.page-head{
  display: flex; justify-content: space-between; align-items: flex-end;
  gap: 20px; flex-wrap: wrap;
  border-bottom: 1px solid var(--rule-2); padding-bottom: 14px; margin-bottom: 20px;
}
.page-title{ font-size: 30px; font-weight: 600; letter-spacing: -.02em; margin: 8px 0 4px; }
.head-meta{ display: flex; gap: 18px; align-items: center; flex-wrap: wrap; }
.head-meta .item{
  font-family: var(--mono); font-size: 11px; letter-spacing: .08em;
  color: var(--ink-2); text-transform: uppercase;
}
.head-meta .item b{ color: var(--ink); font-weight: 500; }
.status-dot{
  display: inline-block; width: 7px; height: 7px; border-radius: 50%;
  background: var(--signal); margin-right: 6px; vertical-align: 1px;
}
@media (prefers-reduced-motion: no-preference){
  .status-dot{ animation: pulse 2s ease-in-out infinite; }
  @keyframes pulse{ 0%,100%{opacity:1} 50%{opacity:.35} }
}

/* --- 聊天消息：直接改 Streamlit 自带气泡（跨元素包裹 div 在 Streamlit 不生效） --- */
[data-testid="stChatMessage"]{
  background: var(--paper-2);
  border: 1px solid var(--rule);
  border-left: 3px solid var(--signal);
  border-radius: 2px; padding: 12px 18px 16px; margin-bottom: 16px;
  box-shadow: 0 1px 0 rgba(22,34,44,.05);
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]){
  background: var(--paper-3);
  border-left-color: var(--ink);
}
[data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessageAvatarAssistant"]{
  background: var(--signal-bg); border-radius: 2px; color: var(--signal);
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageAvatarUser"]{
  background: rgba(22,34,44,.08); color: var(--ink);
}
[data-testid="stAppViewContainer"] img{
  background: var(--paper-3); border: 1px solid var(--rule);
  border-radius: 2px; padding: 6px; max-width: 100%;
}
.user-text{ font-size: 15px; line-height: 1.65; white-space: pre-wrap; }
.msg-meta{
  font-family: var(--mono); font-size: 10.5px; letter-spacing: .14em;
  text-transform: uppercase; color: var(--ink-3); margin-bottom: 8px;
  display: flex; gap: 12px; flex-wrap: wrap;
}
.msg-meta b{ color: var(--signal); font-weight: 500; }
.fig-cap{
  font-family: var(--mono); font-size: 10.5px; letter-spacing: .1em;
  color: var(--ink-3); text-transform: uppercase;
  padding-top: 6px; margin-bottom: 10px;
}

/* --- 用量量表 --- */
.readout{ display: flex; align-items: baseline; gap: 8px; margin: 4px 0 10px; }
.readout .num{
  font-family: var(--mono); font-size: 30px; font-weight: 500;
  letter-spacing: -.02em; color: var(--ink); font-variant-numeric: tabular-nums;
}
.readout .unit{ font-family: var(--mono); font-size: 10.5px; color: var(--ink-3); letter-spacing: .1em; }
.stat-row{
  display: flex; justify-content: space-between; align-items: baseline;
  font-family: var(--mono); font-size: 11.5px; letter-spacing: .06em; padding: 3px 0;
}
.stat-row .k{ color: var(--ink-2); text-transform: uppercase; }
.stat-row .v{ color: var(--ink); font-variant-numeric: tabular-nums; }
.meter-track{
  display: flex; height: 8px; background: rgba(22,34,44,.08);
  border-radius: 1px; overflow: hidden; margin: 10px 0 4px;
}
.meter-fill{ flex: 0 0 auto; height: 100%; }
.meter-fill.prompt{ background: var(--signal); }
.meter-fill.compl{ background: var(--amber); }
.meter-legend{
  display: flex; gap: 14px; font-family: var(--mono); font-size: 10px;
  letter-spacing: .08em; color: var(--ink-3);
}
.meter-legend i{ display: inline-block; width: 8px; height: 8px; margin-right: 5px; vertical-align: 0; }

/* --- 护栏清单 / 工具箱 --- */
.checks{ list-style: none; margin: 0; padding: 0; }
.checks li{
  font-size: 13px; color: var(--ink); line-height: 1.55;
  padding: 5px 0 5px 20px; position: relative;
}
.checks li::before{
  content: "✓"; position: absolute; left: 0; top: 5px;
  font-family: var(--mono); color: var(--signal); font-size: 12px;
}
.chips{ display: flex; flex-wrap: wrap; gap: 6px; }
.chip{
  font-family: var(--mono); font-size: 11px; letter-spacing: .04em;
  background: var(--paper-3); border: 1px solid var(--rule);
  border-radius: 2px; padding: 3px 8px; color: var(--ink);
}
.chip:hover{ border-color: var(--signal); color: var(--signal-2); }

/* --- 空态 / 建议 --- */
.suggest-head{
  font-family: var(--mono); font-size: 10.5px; letter-spacing: .18em;
  text-transform: uppercase; color: var(--ink-2); margin-bottom: 10px;
}
.suggest-lead{ font-size: 15px; line-height: 1.7; color: var(--ink); margin-bottom: 4px; }

/* --- 禁止脚本重跑时主区淡出（消除"变虚再响应"的割裂感） --- */
/* streamlit 每次 rerun / widget 交互都会整页重跑，期间主容器会被加 scriptRunning 类并半透明，
   请求耗时越长"变虚"越久；这里强制保持不透明，只保留 spinner / 右上角 RUNNING 指示器作为反馈。 */
.stAppViewContainer.stAppViewContainer--scriptRunning,
.stAppViewContainer.stAppViewContainer--scriptRunning .stMain,
.stAppViewContainer.stAppViewContainer--scriptRunning [data-testid="stMain"],
[data-testid="stMain"],
[data-testid="stAppViewContainer"] > [data-testid="stMain"]{
  opacity: 1 !important;
  filter: none !important;
  transition: none !important;
}
[data-testid="stAppViewContainer"]{
  opacity: 1 !important;
  transition: none !important;
}

/* --- 按钮 / 输入 / 展开器 --- */
[data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-primary"]{
  border-radius: 2px !important;
  font-family: var(--sans) !important;
  font-weight: 500 !important;
  letter-spacing: .01em !important;
  transition: background .15s ease, border-color .15s ease, color .15s ease !important;
}
[data-testid="stBaseButton-secondary"]{
  background: var(--paper-3) !important;
  border: 1px solid var(--rule-2) !important;
  color: var(--ink) !important;
}
[data-testid="stBaseButton-secondary"]:hover{
  border-color: var(--signal) !important; color: var(--signal-2) !important;
  background: var(--signal-bg) !important;
}
[data-testid="stBaseButton-primary"]{
  background: var(--signal) !important;
  border: 1px solid var(--signal) !important;
  color: #F7FBFB !important;
}
[data-testid="stBaseButton-primary"]:hover{ background: var(--signal-2) !important; border-color: var(--signal-2) !important; }
/* 底部提问框：st.chat_input 写在最外层 → 进入原生底栏 stBottom（position:sticky; bottom:0）。
   绝不复写 position / bottom，只修正 left 与 max-width 让其和正文区左右对齐。 */
[data-testid="stBottom"]{ left: 0; }
[data-testid="stBottom"] > div{ background-color: var(--paper) !important; }
[data-testid="stBottomBlockContainer"]{
  max-width: 1480px !important;
  margin-left: auto !important;
  margin-right: auto !important;
}
/* stChatInput 只占 3/4 宽且左对齐，从而与正文区的 chat_col（columns[3,1]）对齐；
   框随 stBottomBlockContainer 居中，侧边栏开合时自动跟随，无需 JS。 */
[data-testid="stChatInput"]{
  max-width: 75% !important;
  margin-left: 0 !important;
  margin-right: auto !important;
  width: 100% !important;
}

[data-testid="stChatInput"] textarea{
  background: var(--paper-3) !important;
  border: 1px solid var(--rule-2) !important;
  border-radius: 2px !important;
  font-family: var(--sans) !important;
  color: var(--ink) !important;
  padding: 8px 12px !important;
  min-height: 38px !important;
  max-height: 160px !important;
  line-height: 1.4 !important;
}
[data-testid="stChatInput"] textarea:focus{
  border-color: var(--signal) !important;
  box-shadow: 0 0 0 1px var(--signal) !important;
}
/* --- 收紧 main 底部 streamlit 自动加的 padding-bottom ---
   streamlit 1.x 的 padding-bottom 加在多层（section.main / .block-container /
   [data-testid="stMain"]），默认约 6rem + 一些安全距离，叠加后留白 200px+；
   这里用多选择器一起压到 1rem（约 16px），并给最后一条消息加 margin-bottom 避免遮挡。 */
/* 底部留白：保留 .block-container 的 padding-bottom（约 7rem），
   让最后一条消息不被原生钉底输入框遮挡；不再压成 0。 */
.block-container {
  padding-bottom: 7rem !important;
}

[data-testid="stChatMessage"]:last-child {
  margin-bottom: 0 !important;
}
[data-testid="stExpander"]{
  background: var(--paper-3); border: 1px solid var(--rule);
  border-radius: 2px; box-shadow: none;
}
[data-testid="stCode"]{ background: var(--paper-3) !important; border: 1px solid var(--rule); border-radius: 2px; }
[data-testid="stCode"] code, [data-testid="stCode"] pre{ font-family: var(--mono) !important; color: var(--ink) !important; }
[data-testid="stNotification"]{
  background: var(--paper-2) !important; border: 1px solid var(--rule) !important;
  border-left: 3px solid var(--signal) !important; border-radius: 2px !important;
  color: var(--ink) !important;
}
[data-testid="stFileUploader"] section{
  background: var(--paper-3) !important;
  border: 1px dashed var(--rule-2) !important; border-radius: 2px !important;
}
.alert-card{
  background: rgba(169,58,37,.06); border: 1px solid rgba(169,58,37,.35);
  border-left: 3px solid var(--alert); border-radius: 2px; padding: 12px 16px; margin: 4px 0 14px;
}
.alert-card .eyebrow{ color: var(--alert); }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ---------------- 会话状态初始化 ----------------
def _new_id() -> str:
    return str(uuid.uuid4())


def ensure_state():
    if "session_order" not in st.session_state:
        sid = _new_id()
        st.session_state.session_order = [sid]
        st.session_state.session_titles = {sid: "新对话"}
        st.session_state.current_session_id = sid
        st.session_state.messages = {sid: []}
        st.session_state.csv_paths = {sid: None}  # 新会话不预设数据文件
        st.session_state.token_totals = {sid: {"prompt": 0, "completion": 0, "total": 0}}


def ensure_session(sid: str):
    """切换会话时确保该会话所需的状态键都存在"""
    st.session_state.messages.setdefault(sid, [])
    # 切换会话时不强制填充默认文件，保持"未加载"语义
    st.session_state.csv_paths.setdefault(sid, None)
    st.session_state.token_totals.setdefault(sid, {"prompt": 0, "completion": 0, "total": 0})
    st.session_state.session_titles.setdefault(sid, "新对话")


ensure_state()
cur = st.session_state.current_session_id
ensure_session(cur)


# ---------------- 后端健康检查 ----------------
try:
    requests.get(f"{API_URL}/health", timeout=2)
    backend_ok = True
except requests.exceptions.ConnectionError:
    backend_ok = False

TOKEN_CAP = 100_000
SUGGESTIONS = [
    "这个文件有哪些列？",
    "按地区统计销量总和",
    "按地区画饼图",
    "计算每日销量的环比",
]


# ---------------- 侧边栏：工单抽屉 ----------------
with st.sidebar:
    st.markdown(
        '<div class="eyebrow">AI AGENT · DATA WORKBENCH</div>'
        '<div class="brand-title">数据分析助手</div>'
        '<div class="muted">LangChain Agent · FastAPI · Streamlit</div>',
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    if st.button("＋ 新建分析", use_container_width=True, type="primary"):
        sid = _new_id()
        st.session_state.session_order.insert(0, sid)
        st.session_state.session_titles[sid] = "新对话"
        st.session_state.messages[sid] = []
        st.session_state.csv_paths[sid] = None   # 新建会话不预设文件
        st.session_state.token_totals[sid] = {"prompt": 0, "completion": 0, "total": 0}
        st.session_state.current_session_id = sid
        st.rerun()

    st.markdown(
        f'<div class="panel-title" style="margin-top:18px">会话档案'
        f'<span class="cnt">{len(st.session_state.session_order):02d}</span></div>',
        unsafe_allow_html=True,
    )
    for idx, sid in enumerate(list(st.session_state.session_order), 1):
        title = st.session_state.session_titles.get(sid, "新对话")
        is_cur = (sid == st.session_state.current_session_id)
        label = f"{'▣' if is_cur else '▢'} {idx:02d} · {title}"
        if st.button(label, key="sess_" + sid, use_container_width=True,
                     type=("primary" if is_cur else "secondary")):
            st.session_state.current_session_id = sid
            st.rerun()

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    st.markdown('<div class="panel-title">数据文件</div>', unsafe_allow_html=True)
    uploaded = st.file_uploader("上传 CSV", type="csv", label_visibility="collapsed")
    if uploaded is not None:
        os.makedirs("uploads", exist_ok=True)
        path = os.path.join("uploads", uploaded.name)
        with open(path, "wb") as f:
            f.write(uploaded.getbuffer())
        st.session_state.csv_paths[cur] = path
        st.success(f"已载入 {uploaded.name}")

    # 显式提供示例数据：让"加载 demo.csv"成为用户的主动动作，避免自动加载造成误解
    if st.button("使用示例数据 (demo.csv)", key="use_demo", use_container_width=True):
        st.session_state.csv_paths[cur] = "demo.csv"
        st.rerun()

    cur_path = st.session_state.csv_paths.get(cur)
    if cur_path:
        csv_name = os.path.basename(cur_path)
        cur_html = html.escape(csv_name)
    else:
        csv_name = "未加载"
        cur_html = '<span style="color:var(--alert)">未加载</span>'
    st.markdown(
        f'<div class="stat-row"><span class="k">CURRENT</span>'
        f'<span class="v">{cur_html}</span></div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="panel-title" style="margin-top:18px">推理过程</div>',
                unsafe_allow_html=True)
    st.toggle("SSE 流式输出（实时显示 思考 / 工具调用 / 结果）", key="use_sse", value=False)

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    if st.button("清空当前对话", use_container_width=True):
        st.session_state.messages[cur] = []
        st.session_state.session_titles[cur] = "新对话"
        st.rerun()


# ---------------- 页头 ----------------
cur_path = st.session_state.csv_paths.get(cur)
cur_csv = os.path.basename(cur_path) if cur_path else "未加载"
sess_no = st.session_state.session_order.index(cur) + 1
status_html = (
    '<span class="status-dot"></span>后端在线' if backend_ok else "后端离线"
)
data_html = (
    f'数据 <b>{html.escape(cur_csv)}</b>' if cur_path
    else f'数据 <b style="color:var(--alert)">未加载</b>'
)
st.markdown(
    f'<div class="page-head">'
    f'  <div>'
    f'    <div class="eyebrow">AI AGENT · 智能任务编排</div>'
    f'    <div class="page-title">智能数据分析助手</div>'
    f'    <div class="muted">上传 CSV，用自然语言提问，Agent 自主完成分析、画图并生成报告</div>'
    f'  </div>'
    f'  <div class="head-meta">'
    f'    <span class="item">{data_html}</span>'
    f'    <span class="item">会话 <b>#{sess_no:02d}</b></span>'
    f'    <span class="item">{status_html}</span>'
    f'  </div>'
    f'</div>',
    unsafe_allow_html=True,
)

if not backend_ok:
    st.markdown(
        '<div class="alert-card"><div class="eyebrow">连接失败</div>'
        '<div class="muted">后端未启动。请先在项目目录运行：'
        '<code>uvicorn api:app --port 8000</code></div></div>',
        unsafe_allow_html=True,
    )
    st.stop()

chat_col, dash_col = st.columns([3, 1], gap="large")


def fmt(n: int) -> str:
    return f"{int(n):,}"


def render_timeline(steps: list):
    """执行轨迹：逐条展示工具调用（工具名 / 入参 / 耗时 / 结果摘要）"""
    with st.expander(f"执行轨迹 · {len(steps)} 步", expanded=False):
        for i, s in enumerate(steps, 1):
            st.markdown(
                f'<div class="msg-meta"><b>{i:02d}</b> '
                f'<span>{html.escape(str(s.get("tool", "?")))}</span>'
                f'<span>{s.get("latency_ms", 0)} ms</span></div>',
                unsafe_allow_html=True,
            )
            st.code(str(s.get("args", "")), language="json")
            st.caption(str(s.get("summary", ""))[:400])


def render_assistant(msg: dict):
    steps = msg.get("steps", [])
    tokens = msg.get("tokens") or {}
    total = int(tokens.get("total", 0) or 0)
    latency = msg.get("latency_s", 0)
    meta = [f'分析回执 · {len(steps)} 步']
    if latency:
        meta.append(f"{latency:.1f}s")
    if total:
        meta.append(f"{fmt(total)} tokens")
    st.markdown(
        f'<div class="msg-meta"><b>{html.escape(meta[0])}</b>'
        + "".join(f"<span>{html.escape(m)}</span>" for m in meta[1:])
        + "</div>",
        unsafe_allow_html=True,
    )
    st.markdown(msg.get("content", ""))

    # 兜底：正文里未出现的图表，仍在末尾展示一次，避免漏图
    shown = {os.path.basename(p) for p in
             re.findall(r"/charts/([^)\s?#]+)", msg.get("content", ""))}
    fig_no = 0
    for img_url in msg.get("images", []):
        name = os.path.basename(img_url.rstrip("/"))
        if name in shown:
            continue
        fig_no += 1
        st.image(f"{API_URL}{img_url}")
        st.markdown(
            f'<div class="fig-cap">图 {fig_no} · {html.escape(name)}</div>',
            unsafe_allow_html=True,
        )

    if steps:
        render_timeline(steps)


def enqueue_query(text: str):
    """把用户提问立刻入队 + rerun，让消息实时显示。
    真正的请求由 process_pending() 在下一轮历史渲染完成后再发起。"""
    msgs = st.session_state.messages.setdefault(cur, [])
    if len(msgs) == 0:
        st.session_state.session_titles[cur] = text[:20]
    msgs.append({"role": "user", "content": text, "images": [], "steps": []})
    st.session_state["pending_request"] = text
    st.rerun()


def _stream_render(payload: dict):
    """SSE 流式：实时渲染 思考 / 工具调用 / 观察结果，最后渲染最终回答与图表"""
    status_ph = st.empty()
    answer_ph = st.empty()
    lines: list[str] = []
    final = None
    try:
        with requests.post(f"{API_URL}/chat/stream", json=payload,
                           stream=True, timeout=300) as r:
            for raw in r.iter_lines(decode_unicode=True):
                if not raw or not raw.startswith("data:"):
                    continue
                data = raw[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    ev = json.loads(data)
                except Exception:
                    continue
                t = ev.get("type")
                if t == "thought":
                    lines.append("思考  " + str(ev.get("text", ""))[:300])
                elif t == "action":
                    args = json.dumps(ev.get("args", {}), ensure_ascii=False)
                    lines.append(f"调用  {ev.get('tool')}({args})")
                elif t == "observation":
                    lines.append("结果  " + str(ev.get("text", ""))[:200])
                elif t == "error":
                    lines.append("异常  " + str(ev.get("text", "")))
                elif t == "final":
                    final = ev
                status_ph.code("\n".join(lines[-15:]) or "连接中…")
    except Exception as e:
        answer_ph.error(f"流式请求失败: {e}")
        return None

    status_ph.empty()
    if final:
        answer_ph.markdown(final.get("reply", ""))
        for img_url in final.get("images", []) or []:
            st.image(f"{API_URL}{img_url}")
    return final


def process_pending():
    """处理上一轮用户入队的请求：追加"思考中"占位 → 发请求 → 替换占位 → rerun。"""
    pending_text = st.session_state.pop("pending_request", None)
    if not pending_text:
        return
    msgs = st.session_state.messages.setdefault(cur, [])
    pending_idx = len(msgs)
    msgs.append({
        "role": "assistant",
        "content": "Agent 分析中…",
        "images": [], "steps": [], "tokens": {}, "latency_s": 0,
    })

    payload = {
        "session_id": cur,
        "message": pending_text,
        "csv_path": st.session_state.csv_paths.get(cur) or "",
    }

    # ---------- 分支一：SSE 流式（实时展示推理过程）----------
    if st.session_state.get("use_sse"):
        t0 = time.time()
        with st.chat_message("assistant"):
            final = _stream_render(payload)
        latency = time.time() - t0
        if final is None:                      # 流式失败 → 回退一次性请求
            st.session_state["pending_request"] = pending_text
            st.session_state["use_sse"] = False
            msgs.pop(pending_idx)
            st.rerun()
        resp = {
            "reply": final.get("reply", ""),
            "images": final.get("images", []) or [],
            "steps": final.get("steps", []) or [],
            "tokens": final.get("tokens") or {},
            "needs_confirm": final.get("needs_confirm", False),
        }
    else:
        # 把"思考中"占位也立即渲染出来，让用户看到 Agent 已开工
        with st.chat_message("assistant"):
            render_assistant(msgs[pending_idx])
        t0 = time.time()
        with st.spinner("Agent 分析中…"):
            try:
                r = requests.post(f"{API_URL}/chat", json=payload, timeout=180)
                try:
                    resp = r.json()
                except Exception:
                    resp = {
                        "reply": f"后端返回异常（HTTP {r.status_code}）：{r.text[:200]}",
                        "images": [], "steps": [], "tokens": {},
                    }
            except Exception as e:
                resp = {"reply": f"请求后端失败: {e}",
                        "images": [], "steps": [], "tokens": {}}
        latency = time.time() - t0

    if resp.get("needs_confirm"):
        msgs[pending_idx] = {
            "role": "assistant",
            "content": resp.get("reply", "检测到高风险操作"),
            "images": [], "steps": [], "tokens": {}, "latency_s": latency,
        }
        st.session_state["pending_confirm"] = resp.get("reply", "检测到高风险操作")
    else:
        msgs[pending_idx] = {
            "role": "assistant",
            "content": resp.get("reply", ""),
            "images": resp.get("images", []),
            "steps": resp.get("steps", []),
            "tokens": resp.get("tokens") or {},
            "latency_s": latency,
        }
        t = resp.get("tokens") or {}
        tot = st.session_state.token_totals.setdefault(
            cur, {"prompt": 0, "completion": 0, "total": 0})
        for k in ("prompt", "completion", "total"):
            tot[k] = tot.get(k, 0) + int(t.get(k, 0) or 0)

    st.rerun()


# ---------------- 提问框：在 main area 流中（且位于函数定义之后）调用 ----------------
# 嵌套在 columns 内会被困在列里；放在脚本最末尾又会因渲染顺序最后才出现，体感"延迟"。
user_input = st.chat_input("描述你的分析需求，例如：按地区统计销量总和…")
if user_input:
    enqueue_query(user_input)


# ---------------- 底部提问框布局说明 ----------------
# st.chat_input 已写在最外层（main 流中），Streamlit 1.63 会把它放进原生底栏
# stBottom（position:sticky; bottom:0）。对齐与最大宽度只通过上方 CUSTOM_CSS 里的
# [data-testid="stBottomBlockContainer"] 修正，不复写 position / bottom。
# （早期用 JS 注入 __ciFixCSS 强改 left/right/width 的方案已移除。）


# ---------------- 占位（保留结构，无副作用） ----------------
pass


with chat_col:
    msgs = st.session_state.messages.get(cur, [])

    # 空态：给出可直接点击的分析起手式
    if not msgs:
        st.markdown(
            '<div class="panel">'
            '<div class="panel-title">开始分析<span class="cnt">选一个问题</span></div>'
            '<div class="suggest-lead">描述你想从数据里得到的答案，'
            'Agent 会自己选择工具、跑完统计并把图贴回来。</div>'
            '<div class="muted">下面是几个可以直接点击的起手式：</div>'
            "</div>",
            unsafe_allow_html=True,
        )
        s1, s2 = st.columns(2)
        boxes = [s1, s2, s1, s2]
        for i, q in enumerate(SUGGESTIONS):
            with boxes[i]:
                if st.button(q, key=f"sug_{i}", use_container_width=True):
                    enqueue_query(q)

    for msg in msgs:
        with st.chat_message(msg["role"]):
            if msg["role"] == "user":
                st.markdown('<div class="msg-meta">提问</div>', unsafe_allow_html=True)
                st.markdown(
                    f'<div class="user-text">{html.escape(msg.get("content", ""))}</div>',
                    unsafe_allow_html=True,
                )
            else:
                render_assistant(msg)

    # HITL：高风险操作二次确认
    if st.session_state.get("pending_confirm"):
        st.markdown(
            '<div class="alert-card"><div class="eyebrow">需要确认 · HITL</div>'
            f'<div style="margin-top:6px">{html.escape(str(st.session_state["pending_confirm"]))}</div>'
            "</div>",
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns([1, 1])
        if c1.button("确认执行", type="primary", use_container_width=True):
            try:
                r = requests.post(f"{API_URL}/confirm",
                                  json={"session_id": cur}, timeout=30).json()
                st.session_state.messages[cur].append(
                    {"role": "assistant", "content": "已确认执行：" + str(r.get("msg", "")),
                     "images": [], "steps": [], "tokens": {}})
            except Exception as e:
                st.error(f"确认请求失败: {e}")
            st.session_state["pending_confirm"] = None
            st.rerun()
        if c2.button("取消", use_container_width=True):
            st.session_state["pending_confirm"] = None
            st.rerun()

    # 处理上一轮入队的请求：发请求 → 替换占位 → rerun
    # 放在 chat_col 内、HITL 之后，让"思考中"消息与历史相邻显示
    process_pending()


# ---------------- 右栏：用量 / 护栏 / 工具箱 ----------------
with dash_col:
    tot = st.session_state.token_totals.get(cur, {"prompt": 0, "completion": 0, "total": 0})
    prompt_t = int(tot.get("prompt", 0))
    compl_t = int(tot.get("completion", 0))
    total_t = prompt_t + compl_t
    pw = min(prompt_t / TOKEN_CAP * 100, 100)
    cw = min(compl_t / TOKEN_CAP * 100, 100)

    st.markdown(
        '<div class="panel">'
        '<div class="panel-title">用量 · TOKENS</div>'
        f'<div class="readout"><span class="num">{fmt(total_t)}</span>'
        '<span class="unit">本会话累计</span></div>'
        f'<div class="stat-row"><span class="k">Prompt</span><span class="v">{fmt(prompt_t)}</span></div>'
        f'<div class="stat-row"><span class="k">Completion</span><span class="v">{fmt(compl_t)}</span></div>'
        '<div class="meter-track">'
        f'<span class="meter-fill prompt" style="width:{pw:.2f}%"></span>'
        f'<span class="meter-fill compl" style="width:{cw:.2f}%"></span>'
        "</div>"
        '<div class="meter-legend">'
        '<span><i style="background:#0B7C74"></i>Prompt</span>'
        '<span><i style="background:#B07A15"></i>Completion</span>'
        f'<span>上限 {fmt(TOKEN_CAP)}</span>'
        "</div></div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="panel">'
        '<div class="panel-title">安全护栏 · GUARDRAILS</div>'
        '<ul class="checks">'
        "<li>SQL 仅放行只读 SELECT</li>"
        "<li>拦截 DROP / DELETE / UPDATE 等关键字</li>"
        "<li>禁止绝对路径与目录穿越</li>"
        "<li>删除类操作需二次确认</li>"
        "</ul></div>",
        unsafe_allow_html=True,
    )

    try:
        tools = requests.get(f"{API_URL}/tools", timeout=5).json().get("tools", [])
    except Exception:
        tools = []
    chips = "".join(
        f'<span class="chip" title="{html.escape(str(t.get("description", "")))}">'
        f'{html.escape(str(t.get("name", "")))}</span>'
        for t in tools
    ) or '<span class="muted">（后端未返回工具列表）</span>'
    st.markdown(
        '<div class="panel">'
        f'<div class="panel-title">工具箱 · TOOLBOX<span class="cnt">{len(tools):02d}</span></div>'
        f'<div class="chips">{chips}</div></div>',
        unsafe_allow_html=True,
    )
