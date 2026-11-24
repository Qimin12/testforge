"""用户中心接口：注册、登录、刷新、个人信息、API Key（PRD §6.1）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.security import (
    TokenError,
    WeakPasswordError,
    create_token,
    decode_token,
    generate_api_key,
    hash_password,
    mask_api_key,
    validate_password_strength,
    verify_password,
)
from app.db.models import ApiKey, User
from app.schemas.auth import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserOut,
    UserUpdate,
)

router = APIRouter(prefix="/auth", tags=["用户中心"])


def _as_aware(value: datetime | None) -> datetime | None:
    """SQLite 读出来的 datetime 是 naive 的，比较前统一补上 UTC。

    不做这一步，``locked_until > now`` 会抛 TypeError——这是 SQLite 开发环境
    最常见的坑之一。
    """
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: DbSession) -> User:
    try:
        validate_password_strength(payload.password)
    except WeakPasswordError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    exists = await db.scalar(select(User).where(User.email == payload.email))
    if exists is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该邮箱已注册")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        nickname=payload.nickname or payload.email.split("@")[0],
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginRequest, db: DbSession) -> TokenPair:
    user = await db.scalar(select(User).where(User.email == payload.email))

    # 用户不存在也走相同的耗时分支意义不大，这里直接返回统一错误
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误"
        )

    now = datetime.now(UTC)
    locked_until = _as_aware(user.locked_until)
    if locked_until is not None and locked_until > now:
        remain = int((locked_until - now).total_seconds() // 60) + 1
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"账户已锁定，请 {remain} 分钟后再试",
        )

    if not verify_password(payload.password, user.hashed_password):
        user.failed_login_count += 1
        if user.failed_login_count >= settings.max_login_failures:
            user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
            user.failed_login_count = 0  # 锁定后重新计数
            await db.flush()
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"连续失败 {settings.max_login_failures} 次，账户锁定 "
                f"{settings.lockout_minutes} 分钟",
            )
        await db.flush()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误"
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账户已被禁用")

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    await db.flush()

    return TokenPair(
        access_token=create_token(user.id, "access"),
        refresh_token=create_token(user.id, "refresh"),
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, db: DbSession) -> TokenPair:
    try:
        claims = decode_token(payload.refresh_token, expected_type="refresh")
        user_id = UUID(str(claims["sub"]))
    except (TokenError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="refresh token 无效"
        ) from exc

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不可用")

    return TokenPair(
        access_token=create_token(user.id, "access"),
        refresh_token=create_token(user.id, "refresh"),
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserOut)
async def read_me(user: CurrentUser) -> User:
    return user


@router.patch("/me", response_model=UserOut)
async def update_me(payload: UserUpdate, user: CurrentUser, db: DbSession) -> User:
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(user, field, value)
    await db.flush()
    await db.refresh(user)
    return user


# --------------------------------------------------------------------------- #
# API Key（PRD UC-05）
# --------------------------------------------------------------------------- #
@router.post("/api-keys", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(payload: ApiKeyCreate, user: CurrentUser, db: DbSession) -> ApiKeyCreated:
    full_key, prefix, key_hash = generate_api_key()
    api_key = ApiKey(user_id=user.id, name=payload.name, prefix=prefix, key_hash=key_hash)
    db.add(api_key)
    await db.flush()
    await db.refresh(api_key)

    return ApiKeyCreated(
        id=api_key.id,
        name=api_key.name,
        prefix=api_key.prefix,
        is_active=api_key.is_active,
        created_at=api_key.created_at,
        last_used_at=api_key.last_used_at,
        full_key=full_key,
    )


@router.get("/api-keys", response_model=list[ApiKeyOut])
async def list_api_keys(user: CurrentUser, db: DbSession) -> list[ApiKeyOut]:
    rows = await db.scalars(select(ApiKey).where(ApiKey.user_id == user.id))
    return [
        ApiKeyOut(
            id=row.id,
            name=row.name,
            prefix=mask_api_key(row.prefix),
            is_active=row.is_active,
            created_at=row.created_at,
            last_used_at=row.last_used_at,
        )
        for row in rows
    ]


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(key_id: UUID, user: CurrentUser, db: DbSession) -> None:
    row = await db.get(ApiKey, key_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API Key 不存在")
    await db.delete(row)
