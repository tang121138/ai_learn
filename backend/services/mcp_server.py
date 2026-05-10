"""MCP Server — 将我们的工具暴露为 MCP 服务，供 Claude Desktop / Cursor 等外部应用调用"""
from backend.logger import get_logger

logger = get_logger("mcp.server")

try:
    from mcp.server.fastmcp import FastMCP
    HAS_MCP = True
except ImportError:
    HAS_MCP = False
    FastMCP = None


mcp_app = None  # FastMCP 实例，在 register_tools 后可用


def _build_tool_wrapper(fn, name: str, description: str):
    """将工具函数包装为 MCP 兼容的工具"""

    def wrapper(**kwargs):
        try:
            result = fn(**kwargs)
            return str(result)
        except Exception as e:
            return f"MCP工具错误 [{name}]: {e}"

    wrapper.__name__ = name
    wrapper.__doc__ = description
    return wrapper


def register_tools_as_mcp(function_map: dict, tool_defs: list[dict]):
    """将 function_map 中的所有工具注册为 MCP 工具"""
    global mcp_app

    if not HAS_MCP:
        logger.warning("MCP SDK 未安装，跳过 MCP Server 初始化")
        return

    mcp_app = FastMCP("AI-Agent-1号机")

    for tool_def in tool_defs:
        fn_info = tool_def.get("function", {})
        name = fn_info.get("name", "")
        description = fn_info.get("description", "")

        if name in function_map:
            wrapped = _build_tool_wrapper(function_map[name], name, description)
            mcp_app.tool()(wrapped)

    logger.info(f"MCP Server 已注册 {len(function_map)} 个工具")


def get_mcp_app():
    """获取 MCP FastMCP 实例，用于挂载到 FastAPI"""
    return mcp_app
