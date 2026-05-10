"""SQL 查询工具 — 安全地执行只读 SQL 查询 (SQLite)"""
import sqlite3
import os
from backend.logger import get_logger

logger = get_logger("tool.sql")


def sql_query(query: str, db_path: str = ":memory:") -> str:
    """执行 SQL 查询（仅允许 SELECT，最多返回 50 行）

    Args:
        query: SQL 查询语句 (仅 SELECT 被允许)
        db_path: SQLite 数据库路径，默认 :memory:。可用绝对路径或相对于项目根目录
    """
    query_upper = query.strip().upper()
    if not query_upper.startswith("SELECT"):
        logger.warning(f"sql_query: 非 SELECT 语句被拒绝: {query[:50]}")
        return "错误: 仅允许 SELECT 查询。不支持 INSERT/UPDATE/DELETE/DROP 等写操作。"
    # 禁止危险关键字
    forbidden = ["DROP", "ALTER", "CREATE", "INSERT", "UPDATE", "DELETE", "ATTACH", "DETACH"]
    for kw in forbidden:
        if kw in query_upper.split():
            return f"错误: 查询包含禁止关键字: {kw}"

    # 路径解析
    if db_path != ":memory:" and not os.path.isabs(db_path):
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), db_path)

    if db_path != ":memory:" and not os.path.exists(db_path):
        return f"错误: 数据库文件不存在: {db_path}"

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchmany(50)
        col_names = [desc[0] for desc in cursor.description] if cursor.description else []

        if not rows:
            conn.close()
            return "查询结果为空。"

        # 格式化输出
        lines = []
        lines.append(f"列: {', '.join(col_names)}")
        lines.append(f"共 {len(rows)} 行 (最多显示 50 行):")
        for i, row in enumerate(rows, 1):
            values = ", ".join(str(row[c]) for c in col_names)
            lines.append(f"  [{i}] {values}")

        # 检查是否还有更多行
        if len(rows) == 50:
            remaining = cursor.fetchone()
            if remaining:
                lines.append("  ... (结果被截断，仅显示前 50 行)")
        conn.close()
        return "\n".join(lines)
    except sqlite3.Error as e:
        return f"SQL 查询错误: {e}"
    except Exception as e:
        return f"查询失败: {e}"


tool_def = {
    "type": "function",
    "function": {
        "name": "sql_query",
        "description": "执行 SQL 查询（仅支持 SELECT）。用于查询 SQLite 数据库中的数据。可以对项目中的数据文件进行分析查询。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "SQL SELECT 查询语句，例如: SELECT * FROM users LIMIT 10",
                },
                "db_path": {
                    "type": "string",
                    "description": "SQLite 数据库文件路径。默认 :memory: (内存数据库)。可指定本地 .db 文件路径。",
                },
            },
            "required": ["query"],
        },
    },
}
