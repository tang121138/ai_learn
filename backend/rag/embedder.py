"""嵌入模型封装 — SentenceTransformer 懒加载"""
import asyncio
import hashlib
import json
from sentence_transformers import SentenceTransformer

from backend.rag.config import EMBEDDING_MODEL, EMBEDDING_DIMENSION
from backend.logger import get_logger

logger = get_logger("rag.embedder")


class Embedder:
    def __init__(self):
        self._model: SentenceTransformer | None = None

    def _ensure_model(self):
        if self._model is None:
            logger.info(f"加载嵌入模型: {EMBEDDING_MODEL}")
            self._model = SentenceTransformer(EMBEDDING_MODEL)

    def embed_query(self, text: str) -> list[float]:
        self._ensure_model()
        return self._model.encode(text, normalize_embeddings=True).tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self._ensure_model()
        return self._model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False,
        ).tolist()

    @property
    def dimension(self) -> int:
        return EMBEDDING_DIMENSION

    async def embed_query_cached(self, text: str) -> list[float]:
        """带 Redis 缓存的嵌入查询"""
        try:
            from backend.services.redis_client import redis_client
            if redis_client.enabled:
                cache_key = f"emb:{hashlib.md5(text.encode()).hexdigest()}"
                cached = await redis_client.get(cache_key)
                if cached:
                    return json.loads(cached)
                result = await asyncio.to_thread(self._ensure_model)
                result = await asyncio.to_thread(self.embed_query, text)
                await redis_client.setex(cache_key, 86400, json.dumps(result))
                return result
        except Exception:
            pass
        return await asyncio.to_thread(self.embed_query, text)
