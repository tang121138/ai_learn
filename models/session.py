import uuid
import json
from database import get_connection


def create_session(user_id: str, title: str = "新会话") -> dict:
    """创建新会话"""
    session_id = str(uuid.uuid4())
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO sessions (id, user_id, title) VALUES (%s, %s, %s)",
                (session_id, user_id, title),
            )
        conn.commit()
        return {"id": session_id, "user_id": user_id, "title": title}
    finally:
        conn.close()


def get_user_sessions(user_id: str) -> list[dict]:
    """获取用户的所有会话列表"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, title, created_at, updated_at FROM sessions WHERE user_id=%s ORDER BY updated_at DESC",
                (user_id,),
            )
            return cursor.fetchall()
    finally:
        conn.close()


def update_session_title(session_id: str, title: str):
    """更新会话标题"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE sessions SET title=%s WHERE id=%s",
                (title, session_id),
            )
        conn.commit()
    finally:
        conn.close()


def delete_session(session_id: str):
    """删除会话及其所有消息"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM sessions WHERE id=%s", (session_id,))
        conn.commit()
    finally:
        conn.close()
