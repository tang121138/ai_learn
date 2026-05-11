import json
import os
from tools.weather import get_weather, tool_def as weather_tool_def
from tools.calculator import calculate, tool_def as calculator_tool_def
from tools.file_ops import (
    list_directory, read_file, write_file, search_files,
    tool_defs as file_ops_tool_defs,
)
from tools.datetime_tools import (
    get_current_time, calculate_date, days_between, weekday,
    tool_defs as datetime_tool_defs,
)
from tools.web_request import (
    http_get, http_post,
    tool_defs as web_tool_defs,
)
from tools.system import (
    get_system_info, get_env_var, get_process_info,
    tool_defs as system_tool_defs,
)
from tools.multimodal import analyze_image, store_session_images, clear_session_images, tool_def as multimodal_tool_def
from tools.image_gen import generate_image, tool_def as image_gen_tool_def
from tools.image_edit import edit_image, tool_def as image_edit_tool_def
from tools.sql_tools import sql_query, tool_def as sql_tool_def
from tools.chart_tools import generate_chart, tool_def as chart_tool_def
from tools.excel_tools import read_excel, write_excel, tool_defs as excel_tool_defs
from tools.rag_tools import (
    search_knowledge, upload_document, list_documents, delete_document,
    tool_defs as rag_tool_defs,
)

# 函数名 → 实际函数映射
function_map = {
    "get_weather": get_weather,
    "calculate": calculate,
    "list_directory": list_directory,
    "read_file": read_file,
    "write_file": write_file,
    "search_files": search_files,
    "get_current_time": get_current_time,
    "calculate_date": calculate_date,
    "days_between": days_between,
    "weekday": weekday,
    "http_get": http_get,
    "http_post": http_post,
    "get_system_info": get_system_info,
    "get_env_var": get_env_var,
    "get_process_info": get_process_info,
    "analyze_image": analyze_image,
    "generate_image": generate_image,
    "edit_image": edit_image,
    "sql_query": sql_query,
    "generate_chart": generate_chart,
    "read_excel": read_excel,
    "write_excel": write_excel,
    "search_knowledge": search_knowledge,
    "upload_document": upload_document,
    "list_documents": list_documents,
    "delete_document": delete_document,
}

# 给模型的工具描述列表
tools = [
    weather_tool_def,
    calculator_tool_def,
    *file_ops_tool_defs,
    *datetime_tool_defs,
    *web_tool_defs,
    *system_tool_defs,
    multimodal_tool_def,
    image_gen_tool_def,
    image_edit_tool_def,
    sql_tool_def,
    chart_tool_def,
    *excel_tool_defs,
    *rag_tool_defs,
]

# 按类别组织的工具注册表 (硬编码默认值)
TOOL_CATEGORIES = {
    "基础工具": ["calculate", "get_current_time", "calculate_date", "days_between", "weekday"],
    "网络工具": ["get_weather", "http_get", "http_post"],
    "文件工具": ["list_directory", "read_file", "write_file", "search_files"],
    "系统工具": ["get_system_info", "get_env_var", "get_process_info"],
    "AI工具": ["analyze_image", "generate_image", "edit_image"],
    "数据工具": ["sql_query", "generate_chart", "read_excel", "write_excel"],
    "知识库": ["search_knowledge", "upload_document", "list_documents", "delete_document"],
}


def load_tools_config() -> dict:
    """从 configs/tools.json 加载工具配置, 失败时返回硬编码默认值"""
    json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                             "configs", "tools.json")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        if isinstance(config.get("categories"), dict):
            return config
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {"categories": dict(TOOL_CATEGORIES), "tool_settings": {}}


def load_tool_settings() -> dict:
    """获取工具设置（超时、文件大小限制等）"""
    config = load_tools_config()
    return config.get("tool_settings", {})


def get_tool_categories() -> dict:
    """获取工具分类 (从 JSON 配置或硬编码默认值)"""
    config = load_tools_config()
    return config.get("categories", dict(TOOL_CATEGORIES))


def register_tool(func, tool_def):
    name = tool_def["function"]["name"]
    function_map[name] = func
    tools.append(tool_def)


def remove_tool(name: str):
    if name in function_map:
        del function_map[name]
    for i, t in enumerate(tools):
        if t["function"]["name"] == name:
            tools.pop(i)
            break


def get_tools():
    return tools


def get_function_map():
    return function_map


def list_tools() -> str:
    categories = get_tool_categories()
    result = [f"已注册工具 ({len(tools)} 个):"]
    for category, names in categories.items():
        result.append(f"\n  {category}:")
        for name in names:
            if name in function_map:
                result.append(f"    - {name}")
    return "\n".join(result)

