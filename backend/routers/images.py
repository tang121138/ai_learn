from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from backend.middleware.auth import get_current_user
from backend.services.image_gen import submit_image_generation, query_task
from backend.services.usage_tracker import usage_tracker

router = APIRouter(prefix="/api/images", tags=["生图"])


@router.post("/generations")
async def create_generation(
    body: dict,
    user: Annotated[dict, Depends(get_current_user)],
):
    prompt = body.get("prompt", "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="请输入生图提示词")

    if not usage_tracker.check_quota(user["id"], "image_gen"):
        raise HTTPException(status_code=429, detail="今日生图次数已用完，请明天再试")

    model_id = body.get("model_id")
    size = body.get("size", "1024x1024")
    steps = body.get("steps", 30)

    try:
        task_id = submit_image_generation(prompt, model_id, size, steps)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"提交生图任务失败: {str(e)}")

    usage_tracker.log_usage(user["id"], "image_gen", model_id or "Tongyi-MAI/Z-Image-Turbo")
    return {"task_id": task_id, "status": "PENDING"}


@router.get("/generations/{task_id}")
async def get_generation(task_id: str, user: Annotated[dict, Depends(get_current_user)]):
    try:
        result = query_task(task_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询任务失败: {str(e)}")
    return result
