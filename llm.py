# ============ 模型初始化（支持 .env 切换 provider / model） ============
# 默认沿用 agent-project 的 qwen3.7-max；如需切换到 deepseek，
# 在 .env 里设置：MODEL_PROVIDER=deepseek  MODEL=deepseek-v4-pro

import os

import dotenv

dotenv.load_dotenv()          # 读取 .env 里的密钥与模型配置

MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "openai")   # openai / deepseek
MODEL = os.getenv("MODEL", "qwen3.7-max")
BASE_URL = os.getenv("OPENAI_BASE_URL")                  # 兼容接口的自定义地址
API_KEY = os.getenv("OPENAI_API_KEY")
TEMPERATURE = 0                                          # 数据分析要准确，不发散

# 优先用 init_chat_model（支持多 provider）；不可用时回退到 ChatOpenAI
try:
    from langchain.chat_models import init_chat_model

    llm = init_chat_model(
        model=MODEL,
        model_provider=MODEL_PROVIDER,
        api_key=API_KEY,
        base_url=BASE_URL if BASE_URL else None,
        temperature=TEMPERATURE,
    )
except Exception:
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=MODEL,
        temperature=TEMPERATURE,
        api_key=API_KEY,
        base_url=BASE_URL if BASE_URL else None,
    )
