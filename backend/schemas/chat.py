from pydantic import BaseModel, Field


class ChatContentPart(BaseModel):
    type: str  # "text" | "image_url"
    text: str | None = None
    image_url: dict | None = None


class ChatMessage(BaseModel):
    role: str  # "user"
    content: str | list[ChatContentPart]


class ChatRequest(BaseModel):
    session_id: str
    messages: list[dict] = Field(default_factory=list)
    model_id: str | None = None
    stream: bool = True
    parent_id: str | None = None  # 树形分支: 父消息 ID
    mcp_servers: list[str] = Field(default_factory=list)  # 启用的 MCP 服务器

