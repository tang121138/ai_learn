from datetime import datetime, timezone, timedelta
from database import get_connection
from backend.logger import get_logger
from backend.config import DAILY_TEXT_LIMIT, DAILY_MULTIMODAL_LIMIT, DAILY_IMAGE_GEN_LIMIT

logger = get_logger("usage_tracker")


class UsageTracker:
    DAILY_LIMITS = {
        "text": DAILY_TEXT_LIMIT,
        "multimodal": DAILY_MULTIMODAL_LIMIT,
        "image_gen": DAILY_IMAGE_GEN_LIMIT,
    }

    def _get_today_start(self) -> str:
        now = datetime.now(timezone(timedelta(hours=8)))
        return now.strftime("%Y-%m-%d")

    def _get_today_count(self, user_id: str, api_type: str) -> int:
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

    def check_quota(self, user_id: str, api_type: str) -> bool:
        if api_type not in self.DAILY_LIMITS:
            return False
        return self._get_today_count(user_id, api_type) < self.DAILY_LIMITS[api_type]

    def log_usage(self, user_id: str, api_type: str, model_id: str, tokens: int = 0):
        if api_type not in self.DAILY_LIMITS:
            return
        logger.debug(f"记录用量: user={user_id[:8]} type={api_type} model={model_id} tokens={tokens}")
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
        return {
            "text": self.DAILY_LIMITS["text"] - self._get_today_count(user_id, "text"),
            "multimodal": self.DAILY_LIMITS["multimodal"] - self._get_today_count(user_id, "multimodal"),
            "image_gen": self.DAILY_LIMITS["image_gen"] - self._get_today_count(user_id, "image_gen"),
            "limits": dict(self.DAILY_LIMITS),
        }


usage_tracker = UsageTracker()
