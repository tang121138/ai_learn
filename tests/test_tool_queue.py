"""测试异步工具队列"""
import asyncio
import pytest
from backend.services.tool_queue import AsyncToolQueue, ToolTask


def _slow_tool(sleep: float = 0.1, result: str = "done") -> str:
    import time
    time.sleep(sleep)
    return result


def _fast_tool(a: int, b: int) -> str:
    return str(a + b)


class TestAsyncToolQueue:
    @pytest.fixture
    def queue(self):
        q = AsyncToolQueue()
        q.set_function_map({"slow": _slow_tool, "fast": _fast_tool})
        q.set_tool_configs([
            {"type": "function", "function": {"name": "slow"}, "exec_mode": "async"},
            {"type": "function", "function": {"name": "fast"}},
        ])
        return q

    def test_is_async_tool(self, queue):
        assert queue.is_async_tool("slow") is True
        assert queue.is_async_tool("fast") is False
        assert queue.is_async_tool("unknown") is False

    def test_submit_and_wait(self, queue):
        """测试异步提交流程 (用 asyncio.run)"""

        async def _run():
            worker_task = asyncio.create_task(queue.start_worker())
            await asyncio.sleep(0.05)  # 等 worker 就绪
            task_id = await queue.submit("slow", {"sleep": 0.03, "result": "hello"})
            assert len(task_id) == 12

            result = None
            for _ in range(20):
                await asyncio.sleep(0.05)
                result = await queue.wait(task_id, timeout=0.05)
                if result is not None:
                    break

            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass
            return result

        result = asyncio.run(_run())
        assert result is not None
        assert result["success"] is True
        assert "hello" in result["result"]

    def test_is_async_tool_from_real_config(self):
        """验证真实工具配置中 image_gen 和 multimodal 已标记为 async"""
        from tools import get_tools
        q = AsyncToolQueue()
        q.set_tool_configs(get_tools())
        assert q.is_async_tool("generate_image") is True
        assert q.is_async_tool("analyze_image") is True
        assert q.is_async_tool("get_weather") is False
        assert q.is_async_tool("calculate") is False
