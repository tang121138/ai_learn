from typing import Annotated
from fastapi import APIRouter, Depends, status, HTTPException
from backend.logger import get_logger, audit_login, audit_register
from backend.middleware.auth import create_access_token, get_current_user
from backend.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from models.user import create_user, authenticate_user

router = APIRouter(prefix="/api/auth", tags=["认证"])
logger = get_logger("auth")


@router.post("/register", status_code=201)
async def register(req: RegisterRequest):
    user = create_user(req.username, req.password)
    if user is None:
        raise HTTPException(status_code=409, detail="用户名已存在")
    logger.info(f"用户注册: {req.username}")
    audit_register(req.username)
    return {"id": user["id"], "username": user["username"]}


@router.post("/login")
async def login(req: LoginRequest):
    user = authenticate_user(req.username, req.password)
    if user is None:
        logger.warning(f"登录失败: {req.username}")
        audit_login(req.username, False)
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    logger.info(f"用户登录: {req.username}")
    audit_login(req.username, True)
    token = create_access_token(data={"sub": user["id"]})
    return TokenResponse(
        access_token=token,
        user={"id": user["id"], "username": user["username"]},
    )


@router.get("/me")
async def me(user: Annotated[dict, Depends(get_current_user)]):
    return {"id": user["id"], "username": user["username"], "created_at": user.get("created_at")}
