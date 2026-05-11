"""用户 API Key 管理 — 每个用户独立配置自己的 ModelScope / DeepSeek Key"""
import uuid
from database import get_connection
from backend.utils.crypto import encrypt_value, decrypt_value

PROVIDERS = ["modelscope", "deepseek"]


def get_user_keys(user_id: str) -> dict:
    """获取用户所有 API Key，返回 {provider: {api_key, base_url}} — api_key 自动解密"""
    conn = get_connection()
    try:
        with conn.cursor() as c:
            c.execute(
                "SELECT provider, api_key, base_url FROM user_api_keys WHERE user_id=%s",
                (user_id,),
            )
            rows = c.fetchall()
        result = {}
        for r in rows:
            result[r["provider"]] = {
                "api_key": decrypt_value(r["api_key"]),
                "base_url": r["base_url"],
            }
        return result
    finally:
        conn.close()


def get_user_key(user_id: str, provider: str) -> dict | None:
    """获取用户在指定 provider 的 Key — api_key 自动解密"""
    conn = get_connection()
    try:
        with conn.cursor() as c:
            c.execute(
                "SELECT api_key, base_url FROM user_api_keys WHERE user_id=%s AND provider=%s",
                (user_id, provider),
            )
            row = c.fetchone()
        if row:
            return {"api_key": decrypt_value(row["api_key"]), "base_url": row["base_url"]}
        return None
    finally:
        conn.close()


def upsert_user_key(user_id: str, provider: str, api_key: str, base_url: str = "") -> bool:
    """保存或更新用户的 API Key — api_key 自动加密"""
    encrypted = encrypt_value(api_key)
    conn = get_connection()
    try:
        with conn.cursor() as c:
            c.execute(
                "INSERT INTO user_api_keys (id, user_id, provider, api_key, base_url) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE api_key=VALUES(api_key), base_url=VALUES(base_url)",
                (str(uuid.uuid4()), user_id, provider, encrypted, base_url),
            )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def delete_user_key(user_id: str, provider: str) -> bool:
    """删除用户的 API Key"""
    conn = get_connection()
    try:
        with conn.cursor() as c:
            c.execute(
                "DELETE FROM user_api_keys WHERE user_id=%s AND provider=%s",
                (user_id, provider),
            )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()
