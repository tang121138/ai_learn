from fastapi import APIRouter, Depends
from backend.services.model_manager import model_manager

router = APIRouter(prefix="/api/models", tags=["模型"])


@router.get("")
async def list_models():
    return {"models": model_manager.list_models(), "default_model": model_manager.get_default_id()}
