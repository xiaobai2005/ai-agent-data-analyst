@echo off
chcp 65001 >nul
REM ============ 一键启动后端（FastAPI）============
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] 首次运行：创建虚拟环境 .venv ...
    python -m venv .venv
)
call .venv\Scripts\activate.bat

if not exist ".venv\Scripts\uvicorn.exe" (
    echo [2/3] 安装依赖（约 1-3 分钟）...
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
)

if not exist ".env" (
    echo [!] 未找到 .env，将从 .env.example 复制，请填入你的 API Key
    copy .env.example .env >nul
)

echo [3/3] 启动后端： http://localhost:8000/docs
uvicorn api:app --reload --port 8000
