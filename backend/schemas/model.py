from pydantic import BaseModel


class ModelInfo(BaseModel):
    id: str
    name: str
    provider: str
    type: str  # "text" | "multimodal" | "image_gen"
    context_window: int
    multimodal: bool
    description: str


class ModelListResponse(BaseModel):
    models: list[ModelInfo]
    default_model: str
