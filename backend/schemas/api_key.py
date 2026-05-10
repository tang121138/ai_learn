from pydantic import BaseModel, Field


class ApiKeyUpsertRequest(BaseModel):
    provider: str = Field(..., description="提供商: modelscope 或 deepseek")
    api_key: str = Field(..., min_length=1, description="API Key")
    base_url: str = Field(default="", description="Base URL，不填则用默认")
