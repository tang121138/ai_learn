import uuid
import hashlib
import pymysql
import bcrypt
from backend.logger import get_logger
from database import get_connection

logger = get_logger("user")


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, password_hash: str) -> bool:
    if password_hash.startswith("$2"):
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    # 兼容旧版 SHA-256 哈希
    legacy_hash = hashlib.sha256(password.encode()).hexdigest()
    return legacy_hash == password_hash


def create_user(username: str, password: str) -> dict | None:
    """注册新用户，返回用户信息或 None（用户名已存在）"""
    user_id = str(uuid.uuid4())
    password_hash = _hash_password(password)
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO users (id, username, password_hash) VALUES (%s, %s, %s)",
                (user_id, username, password_hash),
            )
        conn.commit()
        return {"id": user_id, "username": username}
    except pymysql.err.IntegrityError:
        return None
    finally:
        conn.close()


def authenticate_user(username: str, password: str) -> dict | None:
    """验证用户登录 — 支持 bcrypt 和旧版 SHA-256"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, username, password_hash, created_at FROM users WHERE username=%s",
                (username,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        if not _verify_password(password, row["password_hash"]):
            return None
        # 如果是旧版 SHA-256 哈希，自动升级为 bcrypt
        if not row["password_hash"].startswith("$2"):
            new_hash = _hash_password(password)
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE users SET password_hash=%s WHERE id=%s",
                    (new_hash, row["id"]),
                )
            conn.commit()
            logger.info(f"用户 {username} 密码已升级为 bcrypt")
        return {"id": row["id"], "username": row["username"], "created_at": row["created_at"]}
    finally:
        conn.close()


def get_user_by_id(user_id: str) -> dict | None:
    """根据 ID 获取用户信息"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, username, created_at FROM users WHERE id=%s",
                (user_id,),
            )
            return cursor.fetchone()
    finally:
        conn.close()
