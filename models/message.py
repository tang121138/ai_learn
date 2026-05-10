import uuid
import json
from database import get_connection


def _serialize_tool_calls(tool_calls) -> list:
    result = []
    for tc in tool_calls:
        if hasattr(tc, 'model_dump'):
            result.append(tc.model_dump())
        elif isinstance(tc, dict):
            result.append(tc)
        else:
            result.append({"raw": str(tc)})
    return result


def _serialize_content(content) -> str:
    if content is None:
        return None
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def _deserialize_content(content: str):
    if content is None:
        return None
    if isinstance(content, (list, dict)):
        return content
    stripped = content.strip()
    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            return json.loads(stripped)
        except (json.JSONDecodeError, TypeError):
            pass
    return content


def save_message(session_id: str, role: str, content: str = None,
                 tool_calls: list | None = None):
    save_message_raw(session_id, role, content, tool_calls)


def save_message_raw(session_id: str, role: str, content=None,
                     tool_calls: list | None = None,
                     reasoning_content: str | None = None,
                     branch: int = 1, turn_index: int | None = None,
                     parent_id: str | None = None,
                     message_id: str | None = None) -> str:
    """保存消息，返回 message_id。parent_id 为树形分支结构的父节点 ID"""
    if message_id is None:
        message_id = str(uuid.uuid4())
    content_str = _serialize_content(content)
    if tool_calls:
        tool_calls_json = json.dumps(_serialize_tool_calls(tool_calls), ensure_ascii=False)
    else:
        tool_calls_json = None
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO messages (id, session_id, role, content, tool_calls, reasoning_content, branch, turn_index, parent_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (message_id, session_id, role, content_str, tool_calls_json, reasoning_content, branch, turn_index, parent_id),
            )
        conn.commit()
    finally:
        conn.close()
    return message_id


def load_session_history(session_id: str) -> list[dict]:
    return load_session_history_raw(session_id)


def load_session_history_raw(session_id: str) -> list[dict]:
    """加载历史，含 id/parent_id 用于树形分支结构"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, role, content, tool_calls, reasoning_content, branch, turn_index, parent_id FROM messages "
                "WHERE session_id=%s ORDER BY created_at ASC",
                (session_id,),
            )
            rows = cursor.fetchall()

        messages = []
        for row in rows:
            content = _deserialize_content(row["content"])
            reasoning = row.get("reasoning_content") or ""
            msg_id = row["id"]
            pid = row.get("parent_id")
            branch = row.get("branch", 1)
            turn_idx = row.get("turn_index")
            base = {"id": msg_id, "parent_id": pid, "branch": branch, "turn_index": turn_idx}

            if row["role"] == "tool":
                messages.append({**base, "role": "tool", "content": content})
            elif row["tool_calls"]:
                msg = {**base, "role": row["role"], "content": content,
                       "tool_calls": json.loads(row["tool_calls"])}
                if reasoning:
                    msg["reasoning_content"] = reasoning
                messages.append(msg)
            else:
                msg = {**base, "role": row["role"], "content": content}
                if reasoning and row["role"] == "assistant":
                    msg["reasoning_content"] = reasoning
                messages.append(msg)
        return messages
    finally:
        conn.close()


def build_context(session_id: str, leaf_id: str) -> list[dict]:
    """从叶节点沿 parent_id 链上溯到根，返回有序上下文 (根→叶)"""
    all_msgs = load_session_history_raw(session_id)
    msg_map = {m["id"]: m for m in all_msgs}
    chain = []
    current = leaf_id
    while current:
        msg = msg_map.get(current)
        if not msg:
            break
        chain.append(msg)
        current = msg.get("parent_id")
    chain.reverse()
    return chain


def message_to_api_format(msg: dict) -> dict:
    result = {"role": msg["role"]}
    content = msg.get("content")
    if isinstance(content, (list, dict)):
        result["content"] = json.dumps(content, ensure_ascii=False)
    else:
        result["content"] = content
    if msg.get("tool_calls"):
        result["tool_calls"] = msg["tool_calls"]
    if msg.get("tool_call_id"):
        result["tool_call_id"] = msg["tool_call_id"]
    return result
