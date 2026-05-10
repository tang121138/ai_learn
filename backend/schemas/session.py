from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    title: str = "新会话"
    model_id: str | None = None


class SessionUpdate(BaseModel):
    title: str | None = None
    model_id: str | None = None


class SessionResponse(BaseModel):
    id: str
    title: str
    model_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
