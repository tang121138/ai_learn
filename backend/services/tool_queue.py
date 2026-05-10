"""异步工具执行队列 — 消息队列解耦慢工具，避免阻塞 Agent 循环"""
import asyncio
import uuid
import time
from dataclasses import dataclass, field
from backend.logger import get_logger

logger = get_logger("tool_queue")

SLOW_TOOL_TIMEOUT = 90  # 慢工具总超时 (秒)
PROGRESS_INTERVAL = 3   # 进度通知间隔 (秒)


@dataclass
class ToolTask:
    task_id: str
    func_name: str
    func_args: dict
    submitted_at: float = field(default_factory=time.time)


class AsyncToolQueue:
    """异步工具执行队列 — 解耦慢工具，非阻塞执行"""

    def __init__(self):
        self._queue: asyncio.Queue[ToolTask] = asyncio.Queue()
        self._results: dict[str, dict] = {}
        self._events: dict[str, asyncio.Event] = {}
        self._function_map: dict = {}
        self._tool_configs: dict[str, dict] = {}

    def set_function_map(self, fm: dict):
        self._function_map = fm

    def set_tool_configs(self, configs: list[dict]):
        """传入 tools 列表，建立 name → config 映射"""
        for t in configs:
            name = t.get("function", {}).get("name", "")
            if name:
                self._tool_configs[name] = t

    def is_async_tool(self, func_name: str) -> bool:
        cfg = self._tool_configs.get(func_name, {})
        return cfg.get("exec_mode") == "async"

    async def submit(self, func_name: str, func_args: dict) -> str:
        """投递任务到队列，返回 task_id"""
        task_id = uuid.uuid4().hex[:12]
        task = ToolTask(task_id=task_id, func_name=func_name, func_args=func_args)
        self._events[task_id] = asyncio.Event()
        await self._queue.put(task)
        logger.info(f"工具入队: {func_name} task_id={task_id}")
        return task_id

    async def wait(self, task_id: str, timeout: float = PROGRESS_INTERVAL) -> dict | None:
        """
        等待任务结果。返回 None 表示还在执行中。
        返回 dict 表示已完成: {"result": ..., "success": bool}
        """
        event = self._events.get(task_id)
        if event is None:
            return {"result": "任务不存在", "success": False}
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            result = self._results.pop(task_id, None)
            self._events.pop(task_id, None)
            if result is None:
                return {"result": "结果丢失", "success": False}
            return result
        except asyncio.TimeoutError:
            return None  # 还在执行

    async def start_worker(self):
        """启动后台 Worker — 消费队列，线程池执行阻塞函数"""
        logger.info("工具 Worker 已启动")
        while True:
            task = await self._queue.get()
            logger.info(f"Worker 处理: {task.func_name} task_id={task.task_id}")
            try:
                result = await asyncio.to_thread(
                    self._execute, task.func_name, task.func_args
                )
                self._results[task.task_id] = {"result": str(result), "success": True}
            except asyncio.TimeoutError:
                self._results[task.task_id] = {
                    "result": f"工具执行超时 ({task.func_name})",
                    "success": False,
                }
            except Exception as e:
                logger.error(f"Worker 执行失败: {task.func_name} {e}")
                self._results[task.task_id] = {
                    "result": f"工具执行失败: {e}",
                    "success": False,
                }
            finally:
                if task.task_id in self._events:
                    self._events[task.task_id].set()
                self._queue.task_done()
                elapsed = time.time() - task.submitted_at
                logger.info(f"Worker 完成: {task.func_name} task_id={task.task_id} elapsed={elapsed:.1f}s")

    def _execute(self, func_name: str, func_args: dict) -> str:
        """同步执行工具函数 (在线程池中运行)"""
        fn = self._function_map.get(func_name)
        if fn is None:
            return f"未知工具: {func_name}"
        return fn(**func_args)


# 全局单例
tool_queue = AsyncToolQueue()
