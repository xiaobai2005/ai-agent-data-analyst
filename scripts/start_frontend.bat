@echo off
chcp 65001 >nul
REM ============ 一键启动前端（Streamlit）============
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] 首次运行：创建虚拟环境 .venv ...
    python -m venv .venv
)
call .venv\Scripts\activate.bat

if not exist ".venv\Scripts\streamlit.exe" (
    echo [2/3] 安装依赖（约 1-3 分钟）...
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
)

echo [3/3] 启动前端： http://localhost:8501
set API_URL=http://localhost:8000
streamlit run app.py --server.port 8501
