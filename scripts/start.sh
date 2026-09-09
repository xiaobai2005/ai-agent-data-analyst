#!/usr/bin/env bash
# ============ Linux / macOS 一键启动 ============
# 用法：
#   bash scripts/start.sh backend    启动后端 :8000
#   bash scripts/start.sh frontend   启动前端 :8501
#   bash scripts/start.sh all        同时启动（后台运行，日志见 logs/）
set -e
cd "$(dirname "$0")/.."

setup() {
  [ -d .venv ] || { echo "[1/3] 创建虚拟环境 .venv ..."; python3 -m venv .venv; }
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip -q install -r requirements.txt
  [ -f .env ] || { echo "[!] 未找到 .env，已从 .env.example 复制，请填入 API Key"; cp .env.example .env; }
}

case "$1" in
  backend)
    setup
    echo "[3/3] 后端启动： http://localhost:8000/docs"
    exec uvicorn api:app --reload --port 8000
    ;;
  frontend)
    setup
    echo "[3/3] 前端启动： http://localhost:8501"
    export API_URL=http://localhost:8000
    exec streamlit run app.py --server.port 8501
    ;;
  all)
    setup
    mkdir -p logs
    nohup uvicorn api:app --port 8000 > logs/backend.log 2>&1 &
    nohup env API_URL=http://localhost:8000 streamlit run app.py --server.port 8501 > logs/frontend.log 2>&1 &
    echo "后端 http://localhost:8000/docs   前端 http://localhost:8501"
    echo "日志：logs/backend.log / logs/frontend.log"
    ;;
  *)
    echo "用法: bash scripts/start.sh {backend|frontend|all}"
    exit 1
    ;;
esac
