from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
import uuid

from backend.config import JWT_SECRET, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from backend.logger import get_logger
from models.user import get_user_by_id

logger = get_logger("auth.middleware")
security = HTTPBearer(auto_error=False)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "jti": uuid.uuid4().hex})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def blacklist_token(token: str):
    """将 JWT 加入 Redis 黑名单 (登出时调用)"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM],
                             options={"verify_exp": False})
        jti = payload.get("jti", "")
        exp = payload.get("exp", 0)
        now = datetime.now(timezone.utc).timestamp()
        remaining = int(exp - now)
        if remaining > 0 and jti:
            from backend.services.redis_client import redis_client
            if redis_client.enabled:
                await redis_client.setex(f"blacklist:jti:{jti}", remaining, "1")
    except Exception:
        pass


async def _is_token_blacklisted(jti: str) -> bool:
    try:
        from backend.services.redis_client import redis_client
        if redis_client.enabled and jti:
            return bool(await redis_client.get(f"blacklist:jti:{jti}"))
    except Exception:
        pass
    return False


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="需要认证")

    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="令牌中缺少用户ID")
        # 检查 JWT 黑名单
        jti = payload.get("jti", "")
        if jti and await _is_token_blacklisted(jti):
            raise HTTPException(status_code=401, detail="令牌已被注销")
    except JWTError:
        logger.warning("JWT令牌无效或已过期")
        raise HTTPException(status_code=401, detail="令牌无效或已过期")

    user = get_user_by_id(user_id)
    if user is None:
        logger.warning(f"JWT中的用户未找到: {user_id}")
        raise HTTPException(status_code=401, detail="用户未找到")
    return user
