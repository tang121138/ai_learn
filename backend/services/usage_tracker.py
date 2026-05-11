from datetime import datetime, timezone, timedelta
from database import get_connection
from backend.logger import get_logger, audit_quota_check
from backend.config import DAILY_TEXT_LIMIT, DAILY_MULTIMODAL_LIMIT, DAILY_IMAGE_GEN_LIMIT
from backend.services.redis_client import redis_client

logger = get_logger("usage_tracker")


class UsageTracker:
    DAILY_LIMITS = {
        "text": DAILY_TEXT_LIMIT,
        "multimodal": DAILY_MULTIMODAL_LIMIT,
        "image_gen": DAILY_IMAGE_GEN_LIMIT,
    }

    def _get_today_start(self) -> str:
        return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")

    def _redis_key(self, user_id: str, api_type: str) -> str:
        today = self._get_today_start()
        return f"usage:{user_id}:{api_type}:{today}"

    # ── MySQL 回退路径 ──

    def _get_today_count_db(self, user_id: str, api_type: str) -> int:
        today = self._get_today_start()
        conn = get_connection()
        try:
            with conn.cursor() as c:
                c.execute(
                    "SELECT COUNT(*) as cnt FROM usage_logs WHERE user_id=%s AND api_type=%s AND created_at>=%s",
                    (user_id, api_type, today),
                )
                row = c.fetchone()
                return row["cnt"] if row else 0
        finally:
            conn.close()

    # ── 公共接口 ──

    def check_quota(self, user_id: str, api_type: str) -> bool:
        if api_type not in self.DAILY_LIMITS:
            return False

        if redis_client.enabled:
            # 异步调用以同步方式运行（FastAPI async context）
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 在 async context 中使用同步回退
                    key = self._redis_key(user_id, api_type)
                    return self._sync_check_redis(key, api_type)
            except RuntimeError:
                pass
            key = self._redis_key(user_id, api_type)
            return self._sync_check_redis(key, api_type)

        return self._get_today_count_db(user_id, api_type) < self.DAILY_LIMITS[api_type]

    async def check_quota_async(self, user_id: str, api_type: str) -> bool:
        """异步版本 — 优先 Redis，回退 MySQL"""
        if api_type not in self.DAILY_LIMITS:
            return False

        if redis_client.enabled:
            key = self._redis_key(user_id, api_type)
            count = await redis_client.get_int(key) or 0
            return count < self.DAILY_LIMITS[api_type]

        return self._get_today_count_db(user_id, api_type) < self.DAILY_LIMITS[api_type]

    def log_usage(self, user_id: str, api_type: str, model_id: str, tokens: int = 0):
        if api_type not in self.DAILY_LIMITS:
            return

        if redis_client.enabled:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._log_redis(user_id, api_type))
                else:
                    self._sync_log_redis(user_id, api_type)
            except RuntimeError:
                self._sync_log_redis(user_id, api_type)
        else:
            self._log_to_db(user_id, api_type, model_id, tokens)

    def _sync_check_redis(self, key: str, api_type: str) -> bool:
        """同步 Redis get（在 sync context 中使用）"""
        import asyncio
        try:
            # Python 3.10+ asyncio.run 可用在非 async context
            count = asyncio.run(redis_client.get_int(key)) or 0
        except RuntimeError:
            return self._get_today_count_db("", api_type) < self.DAILY_LIMITS[api_type]
        return count < self.DAILY_LIMITS[api_type]

    def _sync_log_redis(self, user_id: str, api_type: str):
        try:
            asyncio.run(self._log_redis(user_id, api_type))
        except RuntimeError:
            pass

    async def _log_redis(self, user_id: str, api_type: str):
        key = self._redis_key(user_id, api_type)
        pipe = await redis_client.pipeline()
        pipe.incr(key)
        pipe.expire(key, 86400 * 2)
        await pipe.execute()

    def _log_to_db(self, user_id: str, api_type: str, model_id: str, tokens: int):
        logger.debug(f"记录用量(DB): user={user_id[:8]} type={api_type} model={model_id}")
        conn = get_connection()
        try:
            with conn.cursor() as c:
                c.execute(
                    "INSERT INTO usage_logs (user_id, api_type, model_id, tokens_used) VALUES (%s,%s,%s,%s)",
                    (user_id, api_type, model_id, tokens),
                )
            conn.commit()
        finally:
            conn.close()

    def get_remaining(self, user_id: str) -> dict:
        # 从 Redis 读当前计数
        result = {}
        for api_type in self.DAILY_LIMITS:
            key = self._redis_key(user_id, api_type)
            count = 0
            if redis_client.enabled:
                import asyncio
                try:
                    count = asyncio.run(redis_client.get_int(key)) or 0
                except RuntimeError:
                    count = self._get_today_count_db(user_id, api_type)
            else:
                count = self._get_today_count_db(user_id, api_type)
            result[api_type] = self.DAILY_LIMITS[api_type] - count

        result["limits"] = dict(self.DAILY_LIMITS)
        return result


usage_tracker = UsageTracker()
