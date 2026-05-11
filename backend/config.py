import os
import json
from dotenv import load_dotenv

load_dotenv()

# JWT
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET 未配置! 请在 .env 中设置 JWT_SECRET=<随机安全密钥>"
    )

# ModelScope API Inference
MODELSCOPE_API_KEY = os.getenv("MODELSCOPE_API_KEY", "")
MODELSCOPE_BASE_URL = os.getenv("MODELSCOPE_BASE_URL", "https://api-inference.modelscope.cn/v1")

# 默认模型配置
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "Qwen/Qwen3-30B-A3B")
MULTIMODAL_MODEL = os.getenv("MULTIMODAL_MODEL", "Qwen/Qwen3.5-397B-A17B")
IMAGE_GEN_MODEL = os.getenv("IMAGE_GEN_MODEL", "Tongyi-MAI/Z-Image-Turbo")


def _load_model_configs() -> list[dict]:
    """加载模型配置: JSON 文件 > 环境变量 > 硬编码默认值"""
    # 1. 尝试从 JSON 文件加载
    json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                             "configs", "models.json")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            configs = json.load(f)
        if isinstance(configs, list) and len(configs) > 0:
            return configs
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # 2. 尝试从环境变量加载
    env_json = os.getenv("MODEL_CONFIGS", "")
    if env_json:
        try:
            configs = json.loads(env_json)
            if isinstance(configs, list) and len(configs) > 0:
                return configs
        except json.JSONDecodeError:
            pass

    # 3. 硬编码默认值
    return [
        {
            "id": "Qwen/Qwen3-30B-A3B",
            "name": "Qwen3 30B",
            "provider": "modelscope",
            "type": "text",
            "context_window": 32768,
            "multimodal": False,
            "description": "通义千问3 文本模型 (30B MoE, 3B激活)",
        },
        {
            "id": "deepseek-v4-flash",
            "name": "DeepSeek V4 Flash",
            "provider": "deepseek",
            "type": "text",
            "context_window": 65536,
            "multimodal": False,
            "api_key_env": "DEEPSEEK_API_KEY",
            "base_url_env": "DEEPSEEK_BASE_URL",
            "description": "DeepSeek V4 Flash 快速模型",
        },
        {
            "id": "Qwen/Qwen3.5-397B-A17B",
            "name": "Qwen3.5 397B (多模态)",
            "provider": "modelscope",
            "type": "multimodal",
            "context_window": 131072,
            "multimodal": True,
            "description": "通义千问3.5 多模态模型 (397B MoE, 17B激活)，支持图像分析",
        },
        {
            "id": "Tongyi-MAI/Z-Image-Turbo",
            "name": "Z-Image-Turbo (生图)",
            "provider": "modelscope",
            "type": "image_gen",
            "context_window": 0,
            "multimodal": False,
            "description": "高效文生图模型 (6B参数)",
        },
    ]


MODEL_CONFIGS = _load_model_configs()

# 免费额度限制
DAILY_TEXT_LIMIT = int(os.getenv("DAILY_TEXT_LIMIT", "1800"))
DAILY_MULTIMODAL_LIMIT = int(os.getenv("DAILY_MULTIMODAL_LIMIT", "100"))
DAILY_IMAGE_GEN_LIMIT = int(os.getenv("DAILY_IMAGE_GEN_LIMIT", "100"))

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
