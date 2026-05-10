import os
from openai import OpenAI

from backend.logger import get_logger
from backend.config import (
    MODELSCOPE_API_KEY,
    MODELSCOPE_BASE_URL,
    MODEL_CONFIGS,
    DEFAULT_MODEL,
    MULTIMODAL_MODEL,
    IMAGE_GEN_MODEL,
)

logger = get_logger("model_manager")


class ModelConfig:
    def __init__(self, **data):
        self.id: str = data["id"]
        self.name: str = data.get("name", data["id"])
        self.provider: str = data.get("provider", "modelscope")
        self.type: str = data.get("type", "text")
        self.context_window: int = data.get("context_window", 4096)
        self.multimodal: bool = data.get("multimodal", False)
        self.description: str = data.get("description", "")
        self.api_key_env: str = data.get("api_key_env", "")
        self.base_url_env: str = data.get("base_url_env", "")

    @property
    def api_key(self) -> str:
        if self.api_key_env:
            return os.getenv(self.api_key_env, "")
        return MODELSCOPE_API_KEY

    @property
    def base_url(self) -> str:
        if self.base_url_env:
            return os.getenv(self.base_url_env, MODELSCOPE_BASE_URL)
        return MODELSCOPE_BASE_URL

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "provider": self.provider,
            "type": self.type, "context_window": self.context_window,
            "multimodal": self.multimodal, "description": self.description,
        }


class ModelManager:
    def __init__(self):
        self._models: dict[str, ModelConfig] = {}
        self._clients: dict[str, OpenAI] = {}
        self._default_id: str = ""
        self._user_keys_cache: dict[str, dict[str, dict]] = {}  # user_id→{provider→{api_key,base_url}}

    def load_from_config(self):
        for cfg in MODEL_CONFIGS:
            mc = ModelConfig(**cfg)
            self._models[mc.id] = mc
        if DEFAULT_MODEL in self._models:
            self._default_id = DEFAULT_MODEL
        elif self._models:
            self._default_id = next(iter(self._models))
        logger.info(f"已加载 {len(self._models)} 个模型，默认: {self._default_id}")

    def set_user_keys(self, user_id: str, keys: dict[str, dict]):
        """注入当前用户的 API Key (from DB) — 每请求调用一次"""
        if keys:
            self._user_keys_cache[user_id] = keys

    def clear_user_keys(self, user_id: str):
        self._user_keys_cache.pop(user_id, None)

    def _get_key_for_provider(self, user_id: str | None, provider: str) -> tuple[str, str]:
        """返回 (api_key, base_url) — 优先用户 Key，回退全局 .env"""
        if user_id and user_id in self._user_keys_cache:
            uk = self._user_keys_cache[user_id].get(provider, {})
            if uk.get("api_key"):
                return uk["api_key"], uk.get("base_url", "") or MODELSCOPE_BASE_URL
        return "", ""

    def _build_client(self, mc: ModelConfig, user_id: str | None = None) -> OpenAI:
        # 优先用户自定义 Key
        user_key, user_url = self._get_key_for_provider(user_id, mc.provider)
        if user_key:
            api_key = user_key
            base_url = user_url or mc.base_url
        else:
            api_key = mc.api_key
            base_url = mc.base_url

        if not api_key:
            raise ValueError(f"模型 {mc.id} 需要 API Key: 请在设置中配置 {mc.provider} 的 Key")
        return OpenAI(api_key=api_key, base_url=base_url)

    def get_client(self, model_id: str | None = None, user_id: str | None = None) -> OpenAI:
        model_id = model_id or self._default_id
        mc = self._models.get(model_id)
        if not mc:
            raise ValueError(f"未知模型: {model_id}")
        user_key, _ = self._get_key_for_provider(user_id, mc.provider)
        cache_key = f"{mc.provider}|{user_id or 'default'}|{user_key[:8] if user_key else 'env'}"
        if cache_key not in self._clients:
            self._clients[cache_key] = self._build_client(mc, user_id)
        return self._clients[cache_key]

    def get_config(self, model_id: str | None) -> ModelConfig:
        if model_id and model_id in self._models:
            return self._models[model_id]
        return self._models[self._default_id]

    def get_multimodal_model(self) -> str:
        return MULTIMODAL_MODEL if MULTIMODAL_MODEL in self._models else self._default_id

    def get_image_gen_model(self) -> str:
        return IMAGE_GEN_MODEL if IMAGE_GEN_MODEL in self._models else "Tongyi-MAI/Z-Image-Turbo"

    def list_models(self) -> list[dict]:
        return [m.to_dict() for m in self._models.values()]

    def get_default_id(self) -> str:
        return self._default_id

    def has_model(self, model_id: str) -> bool:
        return model_id in self._models


model_manager = ModelManager()
model_manager.load_from_config()
