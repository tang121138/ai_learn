import os

SAFE_BASE_DIR = os.path.expanduser("~")


def _safe_path(path: str) -> str:
    """确保路径在安全范围内，防止目录穿越攻击"""
    real_path = os.path.realpath(os.path.expanduser(path))
    if not real_path.startswith(SAFE_BASE_DIR):
        raise PermissionError(f"禁止访问用户目录之外的路径: {path}")
    return real_path


def list_directory(path: str = ".") -> str:
    """列出目录下的文件和子目录"""
    try:
        target = _safe_path(path) if path != "." else os.getcwd()
        items = os.listdir(target)
        if not items:
            return f"目录 '{path}' 为空"
        result = [f"目录: {path}"]
        for item in sorted(items):
            item_path = os.path.join(target, item)
            tag = "[目录]" if os.path.isdir(item_path) else "[文件]"
            size = os.path.getsize(item_path) if os.path.isfile(item_path) else 0
            if size < 1024:
                size_str = f"{size}B"
            elif size < 1024 * 1024:
                size_str = f"{size / 1024:.1f}KB"
            else:
                size_str = f"{size / (1024 * 1024):.1f}MB"
            result.append(f"  {tag} {item} ({size_str})")
        return "\n".join(result)
    except PermissionError as e:
        return f"权限错误: {str(e)}"
    except Exception as e:
        return f"列出目录失败: {str(e)}"


def read_file(path: str) -> str:
    """读取文本文件内容"""
    try:
        target = _safe_path(path)
        if not os.path.isfile(target):
            return f"'{path}' 不是文件"
        if os.path.getsize(target) > 1024 * 1024:  # 1MB 限制
            return "文件过大（超过1MB），无法读取"
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(5000)  # 最多读5000字符
            if len(content) >= 5000:
                content += "\n...[内容已截断]"
            return content
    except PermissionError as e:
        return f"权限错误: {str(e)}"
    except Exception as e:
        return f"读取文件失败: {str(e)}"


def write_file(path: str, content: str) -> str:
    """写入文本文件"""
    try:
        target = _safe_path(path)
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        return f"已写入文件: {path} ({len(content)} 字符)"
    except PermissionError as e:
        return f"权限错误: {str(e)}"
    except Exception as e:
        return f"写入文件失败: {str(e)}"


def search_files(pattern: str) -> str:
    """在当前目录递归搜索匹配的文件名"""
    try:
        import glob
        matches = glob.glob(f"**/{pattern}", recursive=True)
        if not matches:
            return f"未找到匹配 '{pattern}' 的文件"
        result = [f"搜索 '{pattern}' 找到 {len(matches)} 个文件:"]
        for m in matches[:30]:
            result.append(f"  {m}")
        if len(matches) > 30:
            result.append(f"  ...（仅显示前30个）")
        return "\n".join(result)
    except Exception as e:
        return f"搜索失败: {str(e)}"


# 工具定义
tool_defs = [
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "列出指定目录下的文件和子目录，包含文件大小信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "目录路径，例如：. 表示当前目录，~/Documents 表示文档目录",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取文本文件的内容，最多返回5000个字符",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "创建或覆盖写入文本文件",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径",
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的文件内容",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "搜索匹配指定模式的文件名，支持通配符",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "搜索模式，例如：*.py 查找所有Python文件",
                    }
                },
                "required": ["pattern"],
            },
        },
    },
]
