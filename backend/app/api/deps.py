"""FastAPI 依赖注入。

认证支持两种方式（二选一）：
* ``Authorization: Bearer <access_token>`` —— 前端 / 人工调用
* ``X-API-Key: tfg_xxx``                   —— CI/CD、脚本（PRD CD-01~CD-03）

两者最终都解析成同一个 ``User``，所以业务接口不需要区分调用来源。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenError, decode_token, verify_api_key
from app.db.models import ApiKey, User
from app.db.session import get_db

DbSession = Annotated[AsyncSession, Depends(get_db)]

_bearer = HTTPBearer(auto_error=False, description="Bearer <access_token>")

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="未认证或凭证已失效（支持 Bearer token 或 X-API-Key）",
    headers={"WWW-Authenticate": "Bearer"},
)


async def _user_from_jwt(db: AsyncSession, token: str) -> User:
    try:
        payload = decode_token(token, expected_type="access")
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    try:
        user_id = UUID(str(payload["sub"]))
    except (KeyError, ValueError) as exc:
        raise _CREDENTIALS_ERROR from exc

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise _CREDENTIALS_ERROR
    return user


async def _user_from_api_key(db: AsyncSession, raw_key: str) -> User:
    """按前缀查候选，再用 bcrypt 校验完整值。

    Key 的格式是 ``tfg_<随机串>``，前 12 位作为可检索前缀存在库里，
    所以这里能走索引，不必全表扫描。
    """
    raw_key = raw_key.strip()
    if not raw_key:
        raise _CREDENTIALS_ERROR

    prefix = raw_key[:12]
    candidates = await db.scalars(
        select(ApiKey).where(ApiKey.prefix == prefix, ApiKey.is_active.is_(True))
    )
    for candidate in candidates:
        if not verify_api_key(raw_key, candidate.key_hash):
            continue
        user = await db.get(User, candidate.user_id)
        if user is None or not user.is_active:
            raise _CREDENTIALS_ERROR
        candidate.last_used_at = datetime.now(UTC)
        await db.flush()
        return user

    raise _CREDENTIALS_ERROR


async def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> User:
    if x_api_key:
        return await _user_from_api_key(db, x_api_key)
    if credentials is not None and credentials.credentials:
        return await _user_from_jwt(db, credentials.credentials)
    raise _CREDENTIALS_ERROR


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> User:
    """PRD §4.2：平台配置/资源管理/审计日志仅测试管理员可用。"""
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
