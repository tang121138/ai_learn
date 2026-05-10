import json
import sys
import tiktoken
from openai import OpenAI
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from tools import get_tools, get_function_map, list_tools
from models.message import save_message, load_session_history
from models.session import update_session_title, get_user_sessions


if not DEEPSEEK_API_KEY:
    print("错误: 请在 .env 文件中设置 DEEPSEEK_API_KEY")
    sys.exit(1)

client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

# 配置
MAX_CONTEXT_TOKENS = 8000    # 上下文窗口上限（预估）
RESERVE_TOKENS = 2000        # 为回复保留的 token 数
DEFAULT_SYSTEM_PROMPT = "你是一个ai助手，如果有人询问你是什么，请回答你是ai助手-1号机测试版"

# 特殊命令
COMMANDS = {
    "/new": "创建新会话",
    "/sessions": "查看会话列表",
    "/tools": "查看可用工具",
    "/stream": "切换流式输出",
    "/help": "查看命令帮助",
}

# 尝试加载 tokenizer，失败则使用估算
try:
    _enc = tiktoken.get_encoding("cl100k_base")
    def count_tokens(text: str) -> int:
        return len(_enc.encode(text))
except Exception:
    def count_tokens(text: str) -> int:
        """粗略估算 token 数：中文约 2 字符/token，英文约 4 字符/token"""
        return len(text) // 2


def _estimate_message_tokens(msg: dict) -> int:
    """估算单条消息的 token 数"""
    total = 4  # 消息格式开销
    for key in ("content", "role"):
        if key in msg and msg[key]:
            total += count_tokens(str(msg[key]))
    if msg.get("tool_calls"):
        total += count_tokens(json.dumps(msg["tool_calls"], ensure_ascii=False))
    return total


def _estimate_total_tokens(messages: list[dict]) -> int:
    """估算消息列表的总 token 数"""
    return sum(_estimate_message_tokens(m) for m in messages)


def _trim_messages(messages: list[dict]) -> list[dict]:
    """裁剪消息历史，保留 system prompt + 最近的对话"""
    total = _estimate_total_tokens(messages)
    threshold = MAX_CONTEXT_TOKENS - RESERVE_TOKENS

    if total <= threshold:
        return messages

    # 保留 system prompt 和最后 N 条消息
    system_msgs = [m for m in messages if m["role"] == "system"]
    other_msgs = [m for m in messages if m["role"] != "system"]

    # 从后往前保留，直到接近阈值
    kept = list(system_msgs)
    kept_tokens = _estimate_total_tokens(kept)

    for msg in reversed(other_msgs):
        msg_tokens = _estimate_message_tokens(msg)
        if kept_tokens + msg_tokens > threshold:
            break
        kept.insert(len(system_msgs), msg)
        kept_tokens += msg_tokens

    if len(kept) < len(messages):
        print(f"[已裁剪对话历史: {len(messages)} → {len(kept)} 条消息]")

    return kept


def _generate_title(user_input: str) -> str:
    """根据用户的第一句话生成会话标题"""
    if len(user_input) > 20:
        return user_input[:20] + "..."
    return user_input[:20]


def agentloop(user: dict, session: dict):
    """Agent 主循环 — 在指定会话中与 AI 对话"""
    use_streaming = False  # 默认非流式

    print(f"\n当前会话: {session['title']} (ID: {session['id'][:8]}...)")
    print(f"令牌使用: 0 / {MAX_CONTEXT_TOKENS}")
    print("输入 /help 查看可用命令")
    print("输入 'exit' 退出循环\n")
    print("-" * 50)

    # 加载历史消息
    messages = load_session_history(session["id"])
    if not messages:
        messages = [{
            "role": "system",
            "content": DEFAULT_SYSTEM_PROMPT
        }]
        save_message(session["id"], "system", messages[0]["content"])

    messages = _trim_messages(messages)
    tools = get_tools()
    function_map = get_function_map()
    is_first_message = (len([m for m in messages if m["role"] != "system"]) == 0)

    while True:
        user_input = input("你: ").strip()
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q"):
            print("返回主菜单")
            return "menu"

        # 处理特殊命令
        if user_input.startswith("/"):
            result = _handle_command(user_input, user["id"], use_streaming)
            if result == "menu":
                return "menu"
            if isinstance(result, bool) and result:
                continue
            if isinstance(result, tuple):  # /stream 返回 (True, new_value)
                use_streaming = result[1]
                continue
            # 未知命令，当作普通消息发给 AI
            pass

        # 第一条消息用作会话标题
        if is_first_message:
            title = _generate_title(user_input)
            update_session_title(session["id"], title)
            session["title"] = title
            is_first_message = False

        # 保存用户消息
        save_message(session["id"], "user", user_input)
        messages.append({"role": "user", "content": user_input})

        # Token 裁剪
        messages = _trim_messages(messages)
        token_usage = _estimate_total_tokens(messages)
        print(f"[令牌: {token_usage} / {MAX_CONTEXT_TOKENS}]")

        while True:
            if not use_streaming:
                print("思考中...", end="", flush=True)
            try:
                response = client.chat.completions.create(
                    model=DEEPSEEK_MODEL,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    stream=use_streaming,
                )
                if not use_streaming:
                    print("\r", end="")
            except Exception as e:
                print(f"\r错误: {e}")
                break

            if use_streaming:
                # 流式处理
                assistant_msg = _handle_streaming_response(
                    response, session["id"]
                )
            else:
                assistant_msg = response.choices[0].message
                # 保存 assistant 消息
                save_message(
                    session["id"],
                    "assistant",
                    assistant_msg.content,
                    assistant_msg.tool_calls,
                )

            msg_dict = assistant_msg.model_dump()
            messages.append(msg_dict)

            if assistant_msg.tool_calls:
                for tool_call in assistant_msg.tool_calls:
                    func_name = tool_call.function.name
                    func_args = json.loads(tool_call.function.arguments)

                    print(f"🔨 调用工具: {func_name}({func_args})")

                    if func_name in function_map:
                        try:
                            result = function_map[func_name](**func_args)
                        except Exception as e:
                            result = f"工具执行错误: {str(e)}"
                    else:
                        result = f"未知工具: {func_name}"

                    # 保存工具结果
                    save_message(session["id"], "tool", result)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    })
                continue
            else:
                if not use_streaming:
                    reply = assistant_msg.content
                    print(f"Agent: {reply}")
                break

        print("-" * 50)


def _handle_streaming_response(stream, session_id: str):
    """处理流式响应，实时打印并收集完整消息"""
    collected_content = ""
    collected_tool_calls = []

    print("Agent: ", end="", flush=True)

    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta

        # 处理文本内容
        if delta.content:
            print(delta.content, end="", flush=True)
            collected_content += delta.content

        # 处理工具调用（流式工具调用需要拼接）
        if delta.tool_calls:
            for tc_delta in delta.tool_calls:
                idx = tc_delta.index
                # 确保列表足够长
                while len(collected_tool_calls) <= idx:
                    collected_tool_calls.append({
                        "id": "",
                        "function": {"name": "", "arguments": ""}
                    })
                if tc_delta.id:
                    collected_tool_calls[idx]["id"] = tc_delta.id
                if tc_delta.function:
                    if tc_delta.function.name:
                        collected_tool_calls[idx]["function"]["name"] = tc_delta.function.name
                    if tc_delta.function.arguments:
                        collected_tool_calls[idx]["function"]["arguments"] += tc_delta.function.arguments

    print()  # 换行

    # 构造完整的 assistant message
    from types import SimpleNamespace
    tool_calls_obj = None
    if collected_tool_calls:
        tool_calls_obj = []
        for tc in collected_tool_calls:
            tool_calls_obj.append(SimpleNamespace(
                id=tc["id"],
                function=SimpleNamespace(
                    name=tc["function"]["name"],
                    arguments=tc["function"]["arguments"],
                ),
            ))

    msg = SimpleNamespace(
        content=collected_content or None,
        tool_calls=tool_calls_obj,
        model_dump=lambda: {
            "role": "assistant",
            "content": collected_content or None,
            "tool_calls": collected_tool_calls if collected_tool_calls else None,
        }
    )

    # 保存完整消息
    save_message(session_id, "assistant", collected_content or None,
                 collected_tool_calls if collected_tool_calls else None)

    return msg


def _handle_command(cmd: str, user_id: str, use_streaming: bool) -> bool | str | tuple:
    """处理特殊命令

    Returns:
        True: 已处理
        'menu': 返回主菜单
        (True, bool): /stream 切换，返回新的 streaming 状态
        None: 未处理
    """
    parts = cmd.strip().split()
    command = parts[0].lower()

    if command == "/help":
        print("\n可用命令:")
        for cmd, desc in COMMANDS.items():
            print(f"  {cmd} — {desc}")
        stream_status = "开启" if use_streaming else "关闭"
        print(f"\n当前流式输出: {stream_status}")
        print(f"令牌上限: {MAX_CONTEXT_TOKENS}")
        print()
        return True

    if command == "/sessions":
        sessions = get_user_sessions(user_id)
        if sessions:
            print(f"\n你的会话列表 (共 {len(sessions)} 个):")
            for s in sessions:
                print(f"  [{s['id'][:8]}...] {s['title']} ({s['updated_at']})")
        else:
            print("\n暂无会话记录")
        print()
        return True

    if command == "/new":
        return "menu"

    if command == "/tools":
        print(f"\n{list_tools()}")
        print()
        return True

    if command == "/stream":
        use_streaming = not use_streaming
        status = "开启" if use_streaming else "关闭"
        print(f"\n流式输出已{status}")
        print()
        return (True, use_streaming)

    print(f"未知命令: {command}，输入 /help 查看可用命令")
    return True
