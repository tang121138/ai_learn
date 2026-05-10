import tiktoken
from backend.logger import get_logger

logger = get_logger("token_counter")

MAX_CONTEXT_TOKENS = 8000
RESERVE_TOKENS = 2000

try:
    _enc = tiktoken.get_encoding("cl100k_base")

    def count_tokens(text: str) -> int:
        return len(_enc.encode(text))
except Exception:

    def count_tokens(text: str) -> int:
        return len(text) // 2


def estimate_message_tokens(msg: dict) -> int:
    total = 4
    for key in ("content", "role"):
        if key in msg and msg[key]:
            val = msg[key]
            if isinstance(val, str):
                total += count_tokens(val)
            elif isinstance(val, list):
                total += count_tokens(str(val))
    if msg.get("tool_calls"):
        import json
        total += count_tokens(json.dumps(msg["tool_calls"], ensure_ascii=False))
    return total


def estimate_total_tokens(messages: list[dict]) -> int:
    return sum(estimate_message_tokens(m) for m in messages)


def trim_messages(messages: list[dict]) -> list[dict]:
    total = estimate_total_tokens(messages)
    threshold = MAX_CONTEXT_TOKENS - RESERVE_TOKENS
    if total <= threshold:
        return messages

    system_msgs = [m for m in messages if m["role"] == "system"]
    other_msgs = [m for m in messages if m["role"] != "system"]

    kept = list(system_msgs)
    kept_tokens = estimate_total_tokens(kept)

    for msg in reversed(other_msgs):
        msg_tokens = estimate_message_tokens(msg)
        if kept_tokens + msg_tokens > threshold:
            break
        kept.insert(len(system_msgs), msg)
        kept_tokens += msg_tokens

    # 修复: 确保被保留的消息中 tool_calls 和 tool_result 配对完整
    # 移除开头孤立的 tool 消息（对应的 assistant tool_calls 已被裁剪）
    while kept and kept[0].get("role") == "tool":
        kept.pop(0)
    # 移除末尾孤立的 assistant tool_calls（对应的 tool 消息已被裁剪）
    # 向前搜索：如果最新保留的消息有 tool_calls 但没有后续 tool 消息，移除它
    for i in range(len(kept) - 1, -1, -1):
        if kept[i].get("tool_calls"):
            # 检查后面是否有 tool 消息
            has_tool_response = any(
                m.get("role") == "tool" and m.get("tool_call_id")
                for m in kept[i + 1:]
            )
            if not has_tool_response:
                # 裁剪掉这个孤立的 assistant tool_calls 及其后续
                kept = kept[:i]
                break

    if len(kept) < len(messages):
        logger.warning(f"已裁剪对话历史: {len(messages)} → {len(kept)} 条消息")

    return kept
