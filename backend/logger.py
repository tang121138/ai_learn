"""结构化日志 + 全链路追踪 + 审计日志"""
import logging
import sys
import os
import json
import uuid
import time
from datetime import datetime, timezone, timedelta
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler

# 全链路 trace_id
_trace_id: ContextVar[str] = ContextVar("trace_id", default="")

_log_initialized = False


def setup_logging(level: int = logging.INFO) -> None:
    global _log_initialized
    if _log_initialized:
        return
    _log_initialized = True

    tz_utc8 = timezone(timedelta(hours=8))

    # --- 开发日志 (控制台 stderr) ---
    console_fmt = logging.Formatter(
        "%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_fmt.converter = lambda *args: datetime.now(tz_utc8).timetuple()
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_fmt)
    console_handler.setLevel(level)

    # --- 审计日志 (文件, JSON 格式) ---
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    audit_path = os.path.join(log_dir, "audit.log")
    audit_handler = RotatingFileHandler(
        audit_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    audit_handler.setLevel(logging.INFO)
    audit_handler.setFormatter(logging.Formatter("%(message)s"))

    root = logging.getLogger("agent")
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(console_handler)
    root.addHandler(audit_handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"agent.{name}")


# --- 全链路追踪 ---

class TraceContext:
    """请求级追踪上下文"""

    def __init__(self):
        self.trace_id: str = ""
        self.user_id: str = ""
        self.model_id: str = ""
        self.start_time: float = 0.0
        self.tool_calls: list[str] = []

    @property
    def latency_ms(self) -> float:
        if self.start_time:
            return (time.time() - self.start_time) * 1000
        return 0.0

    def start(self, user_id: str = "", model_id: str = "") -> str:
        self.trace_id = uuid.uuid4().hex[:12]
        self.user_id = user_id
        self.model_id = model_id
        self.start_time = time.time()
        self.tool_calls = []
        _trace_id.set(self.trace_id)
        return self.trace_id

    def add_tool(self, name: str) -> None:
        self.tool_calls.append(name)


_trace_ctx: ContextVar[TraceContext] = ContextVar("trace_ctx", default=TraceContext())


def get_trace() -> TraceContext:
    return _trace_ctx.get()


# --- 审计日志 ---

def _audit(event: str, **kwargs) -> None:
    tz_utc8 = timezone(timedelta(hours=8))
    ctx = get_trace()
    record = {
        "ts": datetime.now(tz_utc8).isoformat(timespec="milliseconds"),
        "trace_id": ctx.trace_id,
        "user": ctx.user_id,
        "event": event,
        **kwargs,
    }
    logging.getLogger("agent").info(json.dumps(record, ensure_ascii=False))


def audit_chat_completion(model: str, tokens: int) -> None:
    ctx = get_trace()
    _audit("chat_completion", model=model, tokens=tokens,
           latency_ms=round(ctx.latency_ms), tool_calls=ctx.tool_calls)


def audit_tool_exec(tool: str, success: bool, latency_ms: float) -> None:
    _audit("tool_exec", tool=tool, success=success, latency_ms=round(latency_ms))


def audit_quota_check(api_type: str, remaining: int) -> None:
    _audit("quota_check", api_type=api_type, remaining=remaining)


def audit_login(username: str, success: bool) -> None:
    _audit("login", username=username, success=success)


def audit_register(username: str) -> None:
    _audit("register", username=username)
