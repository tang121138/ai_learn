from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from backend.middleware.auth import get_current_user
from backend.schemas.api_key import ApiKeyUpsertRequest
from models.api_key import get_user_keys, upsert_user_key, delete_user_key, PROVIDERS

router = APIRouter(prefix="/api/keys", tags=["API Key"])


@router.get("")
async def list_keys(user: Annotated[dict, Depends(get_current_user)]):
    """获取当前用户所有 API Key (脱敏)"""
    keys = get_user_keys(user["id"])
    result = {}
    for prov in PROVIDERS:
        info = keys.get(prov, {})
        key = info.get("api_key", "")
        result[prov] = {
            "configured": bool(key),
            "masked_key": _mask(key) if key else "",
            "base_url": info.get("base_url", ""),
        }
    return {"keys": result}


@router.put("/{provider}")
async def save_key(
    provider: str,
    req: ApiKeyUpsertRequest,
    user: Annotated[dict, Depends(get_current_user)],
):
    """保存或更新 API Key"""
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"不支持的 provider: {provider}")
    ok = upsert_user_key(user["id"], provider, req.api_key, req.base_url)
    if not ok:
        raise HTTPException(status_code=500, detail="保存失败")
    return {"status": "ok"}


@router.delete("/{provider}")
async def remove_key(
    provider: str,
    user: Annotated[dict, Depends(get_current_user)],
):
    """删除 API Key"""
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"不支持的 provider: {provider}")
    delete_user_key(user["id"], provider)
    return {"status": "ok"}


def _mask(key: str) -> str:
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "****" + key[-4:]
