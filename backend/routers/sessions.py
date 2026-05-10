from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from backend.middleware.auth import get_current_user
from backend.schemas.session import SessionCreate, SessionUpdate, SessionResponse
from models.session import create_session, get_user_sessions, update_session_title, delete_session
from models.message import load_session_history

router = APIRouter(prefix="/api/sessions", tags=["会话"])


@router.get("")
async def list_sessions(user: Annotated[dict, Depends(get_current_user)]):
    sessions = get_user_sessions(user["id"])
    return [
        {
            "id": s["id"],
            "title": s["title"],
            "created_at": str(s["created_at"]) if s.get("created_at") else None,
            "updated_at": str(s["updated_at"]) if s.get("updated_at") else None,
        }
        for s in sessions
    ]


@router.post("", status_code=201)
async def create_new_session(req: SessionCreate, user: Annotated[dict, Depends(get_current_user)]):
    session = create_session(user["id"], req.title)
    return {"id": session["id"], "title": session["title"], "model_id": req.model_id}


@router.get("/{session_id}")
async def get_session(session_id: str, user: Annotated[dict, Depends(get_current_user)]):
    sessions = get_user_sessions(user["id"])
    session = next((s for s in sessions if s["id"] == session_id), None)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    messages = load_session_history(session_id)
    return {
        "id": session["id"],
        "title": session["title"],
        "created_at": str(session.get("created_at", "")),
        "updated_at": str(session.get("updated_at", "")),
        "messages": messages,
    }


@router.patch("/{session_id}")
async def update_session(session_id: str, req: SessionUpdate, user: Annotated[dict, Depends(get_current_user)]):
    sessions = get_user_sessions(user["id"])
    session = next((s for s in sessions if s["id"] == session_id), None)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    if req.title:
        update_session_title(session_id, req.title)
        session["title"] = req.title
    return {"id": session["id"], "title": session["title"], "updated_at": str(session.get("updated_at", ""))}


@router.delete("/{session_id}", status_code=204)
async def delete_session_route(session_id: str, user: Annotated[dict, Depends(get_current_user)]):
    sessions = get_user_sessions(user["id"])
    session = next((s for s in sessions if s["id"] == session_id), None)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    delete_session(session_id)
