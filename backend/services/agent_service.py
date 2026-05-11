import json
import re
import time
import traceback
import asyncio

from backend.logger import get_logger, get_trace, audit_chat_completion, audit_tool_exec, audit_quota_check
from backend.config import MODELSCOPE_API_KEY
from backend.services.model_manager import model_manager
from backend.services.token_counter import trim_messages, estimate_total_tokens
from backend.services.usage_tracker import usage_tracker
from backend.services.tool_queue import tool_queue, PROGRESS_INTERVAL
from backend.services.mcp_client import mcp_manager
from models.message import save_message_raw, load_session_history_raw, build_context, message_to_api_format
from models.session import update_session_title
from tools import get_tools, get_function_map, store_session_images, clear_session_images

logger = get_logger("service")


class ToolExecutor:
    """工具执行器 — 重试 + 错误分类 + 降级建议"""

    MAX_RETRIES = 1

    def __init__(self, function_map: dict):
        self.function_map = function_map

    def execute(self, func_name: str, args: dict) -> dict:
        last_error = ""
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                fn = self.function_map.get(func_name)
                if fn is None:
                    return {"success": False, "result": f"未知工具: {func_name}",
                            "suggestion": _get_tool_suggestion(func_name)}
                result = fn(**args)
                if attempt > 0:
                    logger.info(f"工具 {func_name} 重试成功 (第{attempt}次)")
                return {"success": True, "result": str(result)}
            except Exception as e:
                last_error = str(e)
                if attempt < self.MAX_RETRIES:
                    logger.warning(f"工具 {func_name} 失败 (第{attempt+1}次), 重试中: {e}")
                else:
                    logger.error(f"工具 {func_name} 最终失败: {e}")
        return {"success": False, "result": f"工具错误: {last_error}",
                "suggestion": "该工具暂时不可用，可以尝试换一种方式提问"}


def _get_tool_suggestion(func_name: str) -> str:
    """给未知工具的降级建议"""
    suggestions = {
        "analyze_image": "图片分析功能需要上传图片，请先上传图片",
        "generate_image": "请直接描述您想生成的图片内容",
        "get_weather": "可以尝试手动描述天气查询需求",
    }
    return suggestions.get(func_name, "请尝试其他工具或直接提问")


def _get_quota_degradation(api_type: str) -> str | None:
    """返回额度超限时的降级建议"""
    degradations = {
        "text": "文本额度已用完，可以切换到 DeepSeek V4 Flash (独立额度)",
        "multimodal": "多模态额度已用完，可以先上传图片为附件再提问",
        "image_gen": "生图额度已用完，明天 00:00 自动重置",
    }
    return degradations.get(api_type)


_system_prompt_cache: str | None = None
_system_prompt_mtime: float = 0


def _load_system_prompt() -> str:
    """从配置文件或环境变量加载系统提示词 (带 mtime 缓存)"""
    import os
    global _system_prompt_cache, _system_prompt_mtime
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                               "configs", "system_prompt.txt")
    try:
        mtime = os.path.getmtime(config_path)
        if _system_prompt_cache is not None and mtime <= _system_prompt_mtime:
            return _system_prompt_cache
        with open(config_path, "r", encoding="utf-8") as f:
            _system_prompt_cache = f.read().strip()
        _system_prompt_mtime = mtime
        return _system_prompt_cache
    except FileNotFoundError:
        pass
    return os.getenv("SYSTEM_PROMPT", SYSTEM_PROMPT)


SYSTEM_PROMPT = """你是AI助手-1号机，基于魔搭ModelScope平台构建。你拥有多种工具能力：

1. 当用户发送图片时，调用 analyze_image(image_index=0, question="...") 来分析图片内容
2. 当用户要求画图、生成图片时，调用 generate_image(prompt="...") 来创作图片
3. 其他工具: 天气查询、数学计算、文件操作、日期时间、HTTP请求、系统信息

请主动使用工具来完成任务。看到图片提示时务必调用 analyze_image。"""


def _restore_session_images(session_id: str, messages: list[dict]):
    """从已加载的历史消息中提取图片 URL，恢复 _session_images 缓存"""
    from tools.multimodal import get_session_images, _session_images
    if get_session_images(session_id):
        return  # 已有缓存，不覆盖
    urls = []
    for msg in messages:
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    url = part.get("image_url", {}).get("url", "")
                    if url:
                        urls.append(url)
    if urls:
        _session_images[session_id] = urls
        logger.info(f"从历史恢复 {len(urls)} 张图片缓存 session={session_id[:8]}")


def _generate_title(user_input: str) -> str:
    text = user_input if isinstance(user_input, str) else str(user_input)
    if len(text) > 20:
        return text[:20] + "..."
    return text[:20]


class AgentService:
    def __init__(self):
        self.tools = get_tools()
        self.function_map = get_function_map()

        # 合并 MCP 外部工具
        mcp_tool_defs = mcp_manager.get_tool_defs()
        if mcp_tool_defs:
            self.tools = self.tools + mcp_tool_defs
            self.function_map = {**self.function_map, **mcp_manager.get_function_map()}
            logger.info(f"已合并 {len(mcp_tool_defs)} 个 MCP 外部工具 (总计 {len(self.tools)} 个)")

        self.executor = ToolExecutor(self.function_map)
        tool_queue.set_function_map(self.function_map)
        tool_queue.set_tool_configs(self.tools)

    def _extract_content(self, content) -> tuple[str, list[str]]:
        """提取纯文本和图片列表（data URI）"""
        if isinstance(content, str):
            return content, []
        text_parts = []
        image_uris = []
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "image_url":
                        url = part.get("image_url", {}).get("url", "")
                        if url:
                            image_uris.append(url)
                    elif part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
        return " ".join(text_parts), image_uris

    def _to_llm_format(self, msg: dict) -> dict:
        """把存储格式转为 LLM 可接受的纯文本格式"""
        result = {"role": msg["role"]}
        content = msg.get("content")

        if msg["role"] == "tool":
            result["content"] = content
            result["tool_call_id"] = msg.get("tool_call_id", "")
            return result

        if msg["role"] == "user":
            if isinstance(content, list):
                text, img_uris = self._extract_content(content)
                img_count = len([p for p in content if isinstance(p, dict) and p.get("type") == "image_url"])
                if img_count > 0:
                    result["content"] = f"[用户附带了{img_count}张图片] {text or ''}"
                else:
                    result["content"] = text or ""
            else:
                result["content"] = content or ""
        else:
            result["content"] = content or ""

        if msg.get("tool_calls"):
            result["tool_calls"] = msg["tool_calls"]
        if msg.get("reasoning_content"):
            result["reasoning_content"] = msg["reasoning_content"]
        return result

    async def process_streaming(self, session_id: str, user_id: str, model_id: str,
                                  user_content, parent_id: str | None = None):
        """流式处理。parent_id 为树形结构的父节点 ID"""
        ctx = get_trace()
        ctx.trace_id = ctx.trace_id or ""
        logger.info(f"收到请求 session={session_id[:8]} model={model_id} parent={parent_id}")

        if not MODELSCOPE_API_KEY:
            yield {"type": "error", "content": "MODELSCOPE_API_KEY 未配置"}
            return

        if not usage_tracker.check_quota(user_id, "text"):
            remaining = usage_tracker.get_remaining(user_id)
            audit_quota_check("text", remaining["text"])
            suggestion = _get_quota_degradation("text") or ""
            yield {"type": "error", "content": f"今日文本调用次数已用完。{suggestion}"}
            return

        client = model_manager.get_async_client(model_id, user_id=user_id)
        model_config = model_manager.get_config(model_id)
        actual_model = model_config.id

        text_content, image_uris = self._extract_content(user_content)
        logger.debug(f"[步骤1/6] 内容提取: text_len={len(text_content)} images={len(image_uris)}")

        if image_uris:
            logger.info(f"检测到 {len(image_uris)} 张图片")
            clear_session_images(session_id)
            store_session_images(session_id, image_uris)
            saved_content = self._replace_image_uris(user_content, session_id)
        else:
            saved_content = user_content

        if image_uris:
            img_hints = ", ".join([f"图片{idx}" for idx in range(len(image_uris))])
            llm_text = f"[用户发送了{len(image_uris)}张图片({img_hints})，请用 analyze_image 工具逐一分析]\n{text_content or '请分析图片'}"
        else:
            llm_text = text_content

        is_regenerate = False
        if parent_id:
            raw_history = build_context(session_id, parent_id)
            parent_msg = raw_history[-1] if raw_history else None
            if parent_msg and parent_msg.get("role") == "user":
                is_regenerate = True
        else:
            raw_history = load_session_history_raw(session_id)
        # 从 DB 历史中恢复图片缓存 (解决重启/crash 后缓存丢失)
        _restore_session_images(session_id, raw_history)
        logger.debug(f"[步骤2/6] 上下文加载: {len(raw_history)} 条消息, regenerate={is_regenerate}")
        is_first = len([m for m in raw_history if m["role"] != "system"]) == 0
        messages_api = [self._to_llm_format(m) for m in raw_history]
        if not messages_api:
            system_prompt = _load_system_prompt()
            messages_api = [{"role": "system", "content": system_prompt}]

        if is_regenerate:
            user_msg_id = parent_id
        else:
            user_msg_id = save_message_raw(session_id, "user", saved_content, parent_id=parent_id)
            messages_api.append({"role": "user", "content": llm_text})

        if is_first and not is_regenerate:
            update_session_title(session_id, _generate_title(text_content or "图片消息"))

        messages_api = trim_messages(messages_api)
        token_usage = estimate_total_tokens(messages_api)
        usage_tracker.log_usage(user_id, "text", actual_model, tokens=token_usage)
        logger.debug(f"[步骤3/6] Token管理: estimated={token_usage} trimmed={len(messages_api)}msgs")

        # ── RAG: 从知识库检索相关内容注入系统提示 ──
        try:
            from backend.rag.rag_service import rag_service
            from backend.rag.config import SIMILARITY_THRESHOLD as RAG_THRESHOLD
            query_text = text_content or llm_text
            rag_results = await rag_service.search(query_text, user_id=user_id, top_k=3)
            if rag_results:
                knowledge = "\n\n以下是与用户问题相关的知识库内容:\n"
                for i, r in enumerate(rag_results, 1):
                    knowledge += f"\n[{i}] (来源:{r['metadata'].get('filename','')}, 相似度:{r['similarity']:.2f})\n{r['text']}"
                knowledge += "\n\n请参考以上信息回答用户问题。如果不相关请忽略。"
                if messages_api and messages_api[0]["role"] == "system":
                    messages_api[0]["content"] += knowledge
                logger.debug(f"RAG: 注入 {len(rag_results)} 条知识片段")
        except Exception:
            pass  # RAG 失败不影响主流程

        logger.info(f"调用LLM: {actual_model} (工具:{len(self.tools)})")
        logger.debug(f"[步骤4/6] LLM调用开始 model={actual_model}")
        try:
            while True:
                response = await client.chat.completions.create(
                    model=actual_model,
                    messages=messages_api,
                    tools=self.tools,
                    tool_choice="auto",
                    stream=True,
                )

                assistant_msg = {"role": "assistant", "content": None, "tool_calls": None}
                collected_content = ""
                collected_reasoning = ""
                collected_tool_calls = []

                async for chunk in response:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta

                    reasoning = getattr(delta, 'model_extra', {}) or {}
                    reasoning_text = reasoning.get('reasoning_content', '')
                    if reasoning_text:
                        collected_reasoning += reasoning_text
                        yield {"type": "reasoning", "content": reasoning_text}

                    if delta.content:
                        collected_content += delta.content
                        yield {"type": "text", "content": delta.content}
                        await asyncio.sleep(0)

                    if delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index
                            while len(collected_tool_calls) <= idx:
                                collected_tool_calls.append({
                                    "id": "", "type": "function",
                                    "function": {"name": "", "arguments": ""}
                                })
                            if tc_delta.id:
                                collected_tool_calls[idx]["id"] = tc_delta.id
                            if tc_delta.function:
                                if tc_delta.function.name:
                                    collected_tool_calls[idx]["function"]["name"] += tc_delta.function.name
                                if tc_delta.function.arguments:
                                    collected_tool_calls[idx]["function"]["arguments"] += tc_delta.function.arguments

                if not collected_tool_calls:
                    assistant_msg["content"] = collected_content or None
                    if collected_reasoning:
                        assistant_msg["reasoning_content"] = collected_reasoning
                    messages_api.append(assistant_msg)
                    save_message_raw(session_id, "assistant", collected_content or None,
                                     reasoning_content=collected_reasoning or None,
                                     parent_id=user_msg_id)
                    audit_chat_completion(actual_model, token_usage)
                    logger.debug(f"LLM回复完成: content_len={len(collected_content or '')} reasoning_len={len(collected_reasoning)}")
                    break

                tool_names = [tc['function']['name'] for tc in collected_tool_calls]
                logger.info(f"工具调用: {tool_names}")
                logger.debug(f"[步骤5/6] 工具执行开始 tools={tool_names}")
                for name in tool_names:
                    ctx.add_tool(name)

                assistant_msg["tool_calls"] = collected_tool_calls
                if collected_reasoning:
                    assistant_msg["reasoning_content"] = collected_reasoning
                messages_api.append(assistant_msg)
                assistant_msg_id = save_message_raw(session_id, "assistant", collected_content, collected_tool_calls,
                                 reasoning_content=collected_reasoning or None,
                                 parent_id=user_msg_id)

                for tc in collected_tool_calls:
                    func_name = tc["function"]["name"]
                    try:
                        func_args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        func_args = {}

                    yield {"type": "tool_call", "id": tc["id"],
                           "function": {"name": func_name, "arguments": tc["function"]["arguments"]}}
                    await asyncio.sleep(0)

                    # 图片工具注入 session_id (修复会话隔离)
                    if func_name in ("analyze_image", "edit_image"):
                        func_args.setdefault("session_id", session_id)

                    tool_start = time.time()

                    if tool_queue.is_async_tool(func_name):
                        # ── 异步执行: 投递队列 → 等待完成 (带进度通知) ──
                        task_id = await tool_queue.submit(func_name, func_args)
                        yield {"type": "tool_queued", "task_id": task_id,
                               "tool": func_name, "message": f"{func_name} 已提交，预计需要几秒到几十秒"}
                        await asyncio.sleep(0)

                        result = None
                        elapsed = 0.0
                        while result is None:
                            await asyncio.sleep(PROGRESS_INTERVAL)
                            elapsed += PROGRESS_INTERVAL
                            yield {"type": "tool_progress", "task_id": task_id,
                                   "elapsed_seconds": elapsed, "tool": func_name}
                            await asyncio.sleep(0)
                            result = await tool_queue.wait(task_id, timeout=0.5)
                            if result is None:
                                continue
                            break

                        # 异步工具直接用 Worker 的结果，不再过 ToolExecutor
                        exec_success = result.get("success", False)
                        result_text = result.get("result", f"{func_name} 未返回结果")
                    else:
                        # ── 同步执行: 原地调用 (快工具，不变) ──
                        exec_result = self.executor.execute(func_name, func_args)
                        result_text = exec_result["result"]
                        exec_success = exec_result.get("success", True)
                        if not exec_success and "suggestion" in exec_result:
                            result_text = f"{result_text}。提示: {exec_result['suggestion']}"

                    audit_tool_exec(func_name, exec_success, (time.time() - tool_start) * 1000)

                    yield {"type": "tool_result", "tool_call_id": tc["id"], "content": str(result_text)}
                    await asyncio.sleep(0)

                    save_message_raw(session_id, "tool", str(result_text), parent_id=assistant_msg_id)
                    messages_api.append({"role": "tool", "tool_call_id": tc["id"],
                                         "content": str(result_text)})

                    if func_name == "analyze_image":
                        usage_tracker.log_usage(user_id, "multimodal", "multimodal")
                    elif func_name in ("generate_image", "edit_image"):
                        usage_tracker.log_usage(user_id, "image_gen", "image_gen")
                        url_match = re.search(r'https?://\S+', str(result_text))
                        if url_match:
                            from tools.multimodal import _session_images
                            _session_images.setdefault(session_id, []).append(url_match.group())

        except Exception as e:
            logger.error(f"Agent异常: model={actual_model} err={e}\n{traceback.format_exc()}")
            yield {"type": "error", "content": f"{type(e).__name__}: {e}"}

        logger.debug(f"[步骤6/6] Agent完成 session={session_id[:8]}")
        yield {"type": "done"}

    async def process_non_streaming(self, session_id: str, user_id: str, model_id: str,
                                      user_content, parent_id: str | None = None):
        """非流式版本 — 复用流式循环收集结果"""
        collected = {"content": "", "tool_calls": [], "error": None}
        async for event in self.process_streaming(session_id, user_id, model_id, user_content, parent_id):
            if event["type"] == "text":
                collected["content"] += event.get("content", "")
            elif event["type"] == "tool_call":
                collected["tool_calls"].append(event)
            elif event["type"] == "error":
                collected["error"] = event.get("content")
            elif event["type"] == "done":
                break
        if collected["error"]:
            return {"error": collected["error"], "content": collected["content"]}
        return {"content": collected["content"], "tool_calls": collected["tool_calls"]}

    def _replace_image_uris(self, content, session_id: str):
        from tools.multimodal import get_session_images
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return content
        urls = get_session_images(session_id)
        result = []
        img_idx = 0
        for part in content:
            if isinstance(part, dict) and part.get("type") == "image_url":
                if img_idx < len(urls):
                    result.append({"type": "image_url", "image_url": {"url": urls[img_idx]}})
                    img_idx += 1
            else:
                result.append(part)
        return result
