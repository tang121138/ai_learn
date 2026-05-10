"""测试 token 计数与上下文裁剪"""
import pytest
from backend.services.token_counter import (
    count_tokens, estimate_message_tokens, estimate_total_tokens, trim_messages,
)


def test_count_tokens_non_empty():
    assert count_tokens("Hello world") > 0
    assert count_tokens("你好世界") > 0


def test_count_tokens_empty():
    assert count_tokens("") == 0


def test_estimate_message_tokens():
    msg = {"role": "user", "content": "Hello"}
    tokens = estimate_message_tokens(msg)
    assert tokens > 0


def test_estimate_message_with_tool_calls():
    msg = {
        "role": "assistant",
        "content": "Let me check",
        "tool_calls": [{"id": "1", "type": "function", "function": {"name": "get_weather", "arguments": '{"city":"Beijing"}'}}],
    }
    tokens = estimate_message_tokens(msg)
    assert tokens > estimate_message_tokens({"role": "assistant", "content": "Let me check"})


def test_estimate_total_tokens(sample_messages):
    total = estimate_total_tokens(sample_messages)
    assert total > 0


def test_trim_messages_no_trim_needed(sample_messages):
    result = trim_messages(sample_messages)
    assert len(result) == len(sample_messages)


def test_trim_messages_preserves_system():
    """裁剪后系统提示词仍保留"""
    msgs = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
    ]
    result = trim_messages(msgs)
    assert result[0]["role"] == "system"


def test_trim_messages_does_not_crash_on_empty():
    result = trim_messages([])
    assert result == []


def test_trim_messages_handles_single_message():
    msgs = [{"role": "user", "content": "Hi"}]
    result = trim_messages(msgs)
    assert len(result) == 1
