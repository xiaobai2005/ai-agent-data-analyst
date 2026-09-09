# ============ 容器化部署（后端 + 前端共用同一镜像）============
# 构建：docker build -t agent-platform:1.0 .
# 运行：docker compose up -d    （后端 :8000，前端 :8501）

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MPLBACKEND=Agg

# 中文字体：否则 matplotlib 生成的图表中文会显示成方块
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN mkdir -p charts reports uploads data

EXPOSE 8000 8501

# 单容器同时跑前后端的简易入口（docker run 时使用；compose 会分别覆盖 command）
CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port 8000 & \
     API_URL=http://localhost:8000 streamlit run app.py --server.port 8501 --server.address 0.0.0.0"]
