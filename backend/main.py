import os
import time
from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from typing import Annotated

from backend.logger import setup_logging, get_logger, TraceContext, get_trace
from backend.middleware.auth import get_current_user
from backend.routers import auth, sessions, chat, models, images, api_keys, knowledge
from backend.services.usage_tracker import usage_tracker
from config import MYSQL_DATABASE

setup_logging()
logger = get_logger("main")

app = FastAPI(title="AI Agent 系统 (1号机)", version="0.1.0")

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:4000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    """注入全链路 trace_id"""
    ctx = TraceContext()
    ctx.trace_id = os.urandom(6).hex()
    ctx.start_time = time.time()
    # 注入到请求状态，方便路由层获取
    request.state.trace_ctx = ctx
    response = await call_next(request)
    response.headers["X-Trace-Id"] = ctx.trace_id
    return response


app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(chat.router)
app.include_router(models.router)
app.include_router(images.router)
app.include_router(api_keys.router)
app.include_router(knowledge.router)

UPLOADS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")


@app.on_event("startup")
async def startup():
    import asyncio
    from backend.services.tool_queue import tool_queue
    asyncio.create_task(tool_queue.start_worker())
    logger.info("工具 Worker 已调度启动")

    # 初始化 Redis (可选，失败降级)
    from backend.services.redis_client import redis_client
    await redis_client.initialize()

    from database import init_database, get_connection
    try:
        init_database()
        conn2 = get_connection()
        try:
            with conn2.cursor() as c:
                c.execute(
                    "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='messages' AND COLUMN_NAME='reasoning_content'",
                    (MYSQL_DATABASE,))
                if not c.fetchone():
                    c.execute("ALTER TABLE messages ADD COLUMN reasoning_content TEXT NULL")
                c.execute(
                    "SELECT COLUMN_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='messages' AND COLUMN_NAME='content'",
                    (MYSQL_DATABASE,))
                row = c.fetchone()
                if row and row["COLUMN_TYPE"] != "mediumtext":
                    c.execute("ALTER TABLE messages MODIFY content MEDIUMTEXT")
                c.execute(
                    "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='messages' AND COLUMN_NAME='branch'",
                    (MYSQL_DATABASE,))
                if not c.fetchone():
                    c.execute("ALTER TABLE messages ADD COLUMN branch INT DEFAULT 1")
                c.execute(
                    "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='messages' AND COLUMN_NAME='turn_index'",
                    (MYSQL_DATABASE,))
                if not c.fetchone():
                    c.execute("ALTER TABLE messages ADD COLUMN turn_index INT DEFAULT NULL")
                c.execute(
                    "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='messages' AND COLUMN_NAME='parent_id'",
                    (MYSQL_DATABASE,))
                if not c.fetchone():
                    c.execute("ALTER TABLE messages ADD COLUMN parent_id VARCHAR(36) NULL")
            conn2.commit()
        finally:
            conn2.close()
        conn = get_connection()
        try:
            with conn.cursor() as c:
                c.execute("""
                    CREATE TABLE IF NOT EXISTS usage_logs (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id VARCHAR(36) NOT NULL,
                        api_type ENUM('text','multimodal','image_gen') NOT NULL,
                        model_id VARCHAR(200) NOT NULL,
                        tokens_used INT DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_user_date (user_id, created_at)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
            conn.commit()
        finally:
            conn.close()
        logger.info("数据库就绪")
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")

    # 初始化 MCP Server (暴露我方工具)
    from tools import get_function_map, get_tools
    from backend.services.mcp_server import register_tools_as_mcp, get_mcp_app
    register_tools_as_mcp(get_function_map(), get_tools())
    mcp = get_mcp_app()
    if mcp is not None:
        app.mount("/mcp", mcp.streamable_http_app())
        logger.info("MCP Server 已挂载: /mcp")

    # 连接外部 MCP Server (导入外部工具)
    from backend.services.mcp_client import mcp_manager
    servers = mcp_manager.load_config()
    for srv in servers:
        if srv.get("enabled") and srv.get("transport") == "stdio":
            mcp_manager.connect_stdio(
                name=srv["name"],
                command=srv["command"],
                args=srv.get("args", []),
            )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"未处理异常 [{request.method} {request.url.path}]: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"error": "内部服务器错误"})


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/usage")
async def get_usage(user: Annotated[dict, Depends(get_current_user)]):
    return usage_tracker.get_remaining(user["id"])


@app.get("/api/tools")
async def list_tools(user: Annotated[dict, Depends(get_current_user)]):
    from tools import list_tools as lt
    return {"tools": lt()}


@app.get("/api/mcp/servers")
async def list_mcp_servers(user: Annotated[dict, Depends(get_current_user)]):
    """列出 MCP 服务器状态和可用工具"""
    from backend.services.mcp_client import mcp_manager
    from backend.services.mcp_server import HAS_MCP as MCP_SDK_AVAILABLE
    servers_config = mcp_manager.load_config()
    active = []
    for srv in servers_config:
        tools = [t for t in mcp_manager.get_all_tools() if t.server_name == srv["name"]]
        active.append({
            "name": srv["name"],
            "transport": srv.get("transport", "stdio"),
            "enabled": srv.get("enabled", False),
            "connected": len(tools) > 0,
            "tools": [{"name": t.name, "description": t.description} for t in tools],
        })
    return {
        "sdk_available": MCP_SDK_AVAILABLE,
        "servers": active,
    }
