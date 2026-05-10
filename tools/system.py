import os
import sys
import platform


def get_system_info() -> str:
    """获取系统信息"""
    info = {
        "操作系统": platform.system(),
        "系统版本": platform.version(),
        "Python 版本": sys.version,
        "主机名": platform.node(),
        "CPU 架构": platform.machine(),
        "当前工作目录": os.getcwd(),
        "用户目录": os.path.expanduser("~"),
    }
    return "\n".join(f"{k}: {v}" for k, v in info.items())


def get_env_var(name: str) -> str:
    """读取环境变量（仅返回安全的非敏感变量）"""
    # 只允许读取安全的环境变量
    safe_prefixes = ("PATH", "HOME", "USER", "TEMP", "TMP", "LANG", "PYTHON")
    if not any(name.upper().startswith(p) for p in safe_prefixes):
        return f"出于安全考虑，不允许读取 '{name}' 环境变量"
    value = os.environ.get(name)
    if value is None:
        return f"环境变量 '{name}' 不存在"
    return f"{name}={value}"


def get_process_info() -> str:
    """获取当前进程信息"""
    import psutil
    try:
        proc = psutil.Process()
        info = {
            "PID": proc.pid,
            "CPU 使用率": f"{proc.cpu_percent(interval=0.1):.1f}%",
            "内存使用": f"{proc.memory_info().rss / (1024*1024):.1f}MB",
            "线程数": proc.num_threads(),
        }
        return "\n".join(f"{k}: {v}" for k, v in info.items())
    except ImportError:
        return "psutil 未安装，无法获取进程信息"


tool_defs = [
    {
        "type": "function",
        "function": {
            "name": "get_system_info",
            "description": "获取当前系统信息，包括操作系统、Python版本、主机名等",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_env_var",
            "description": "读取安全的环境变量（PATH, HOME, USER, TEMP, LANG, PYTHON等）",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "环境变量名称",
                    }
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_process_info",
            "description": "获取当前进程的CPU和内存使用情况（需要psutil）",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]
