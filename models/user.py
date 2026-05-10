import uuid
import hashlib
import pymysql
from database import get_connection


def _hash_password(password: str) -> str:
    """密码哈希"""
    return hashlib.sha256(password.encode()).hexdigest()


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
    """验证用户登录，返回用户信息或 None"""
    password_hash = _hash_password(password)
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, username, created_at FROM users WHERE username=%s AND password_hash=%s",
                (username, password_hash),
            )
            return cursor.fetchone()
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
