import json
import time
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.logger import get_logger, get_trace
from backend.middleware.auth import get_current_user
from backend.schemas.chat import ChatRequest
from backend.services.agent_service import AgentService
from backend.services.model_manager import model_manager
from models.api_key import get_user_keys
from models.session import get_user_sessions

router = APIRouter(prefix="/api/chat", tags=["聊天"])
logger = get_logger("chat")

agent_service = AgentService()


def _validate_session(session_id: str, user_id: str) -> dict:
    sessions = get_user_sessions(user_id)
    session = next((s for s in sessions if s["id"] == session_id), None)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


async def _stream_events(session_id: str, user_id: str, model_id: str, user_content, parent_id: str | None = None):
    try:
        async for event in agent_service.process_streaming(session_id, user_id, model_id, user_content, parent_id):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    except Exception as e:
        logger.error(f"SSE流异常: {e}", exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/completions")
async def chat_completions(req: ChatRequest, user: Annotated[dict, Depends(get_current_user)],
                           request: Request):
    t0 = time.time()
    ctx = get_trace()
    ctx.start(user_id=user["id"], model_id=req.model_id or "default")

    session = _validate_session(req.session_id, user["id"])

    model_id = req.model_id or model_manager.get_default_id()
    if not model_manager.has_model(model_id):
        raise HTTPException(status_code=400, detail=f"未知模型: {model_id}")

    # 注入用户自定义 API Key
    user_keys = get_user_keys(user["id"])
    model_manager.set_user_keys(user["id"], user_keys)

    last_user_msg = None
    for msg in reversed(req.messages):
        if msg.get("role") == "user":
            last_user_msg = msg.get("content")
            break

    if last_user_msg is None:
        raise HTTPException(status_code=400, detail="缺少用户消息")

    logger.info(f"聊天请求 user={user['id'][:8]} session={req.session_id[:8]} model={model_id}")

    if req.stream:
        return StreamingResponse(
            _stream_events(req.session_id, user["id"], model_id, last_user_msg, req.parent_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        result = await agent_service.process_non_streaming(
            req.session_id, user["id"], model_id, last_user_msg, req.parent_id
        )
        elapsed = (time.time() - t0) * 1000
        logger.info(f"非流式完成 latency={elapsed:.0f}ms")
        return result
