"""Redis 客户端 — 异步连接池 + 优雅降级"""
import os
import json
import asyncio
from typing import Optional, Any

from backend.logger import get_logger

logger = get_logger("redis")

REDIS_DEFAULT_URL = "redis://localhost:6379/0"


class RedisClient:
    def __init__(self):
        self._redis: Any = None
        self._pool: Any = None
        self._enabled: bool = False

    async def initialize(self, url: str | None = None):
        redis_url = url or os.getenv("REDIS_URL", REDIS_DEFAULT_URL)
        try:
            from redis.asyncio import Redis, ConnectionPool
            self._pool = ConnectionPool.from_url(
                redis_url,
                max_connections=20,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
                retry_on_timeout=True,
            )
            self._redis = Redis(connection_pool=self._pool)
            await self._redis.ping()
            self._enabled = True
            logger.info(f"Redis 已连接: {redis_url}")
        except ImportError:
            logger.warning("redis-py 未安装，Redis 功能不可用")
        except Exception as e:
            logger.warning(f"Redis 不可用 ({e})，运行在降级模式")

    async def close(self):
        if self._redis:
            await self._redis.close()
        if self._pool:
            await self._pool.disconnect()
        self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ── 基础操作 ──

    async def get(self, key: str) -> str | None:
        try:
            return await self._redis.get(key) if self._enabled else None
        except Exception:
            return None

    async def setex(self, key: str, ttl: int, value: str) -> bool:
        try:
            return bool(await self._redis.setex(key, ttl, value)) if self._enabled else False
        except Exception:
            return False

    async def delete(self, *keys: str) -> int:
        try:
            return await self._redis.delete(*keys) if self._enabled else 0
        except Exception:
            return 0

    async def incr(self, key: str) -> int:
        try:
            return await self._redis.incr(key) if self._enabled else -1
        except Exception:
            return -1

    async def expire(self, key: str, ttl: int) -> bool:
        try:
            return bool(await self._redis.expire(key, ttl)) if self._enabled else False
        except Exception:
            return False

    async def get_int(self, key: str) -> int | None:
        val = await self.get(key)
        return int(val) if val is not None else None

    # ── 管道 ──

    async def pipeline(self):
        if self._enabled and self._redis:
            return self._redis.pipeline()
        return _NoopPipeline()


class _NoopPipeline:
    """空管道 — 保证降级模式不抛异常"""
    def __getattr__(self, _):
        return lambda *a, **kw: None

    async def execute(self):
        return []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


redis_client = RedisClient()
