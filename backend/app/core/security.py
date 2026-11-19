"""密码哈希、JWT 签发与校验、密码强度校验（PRD §6.1.3 / §8.3）。

刻意不使用 passlib：它 2020 年后停止维护，读取 ``bcrypt.__about__`` 在
bcrypt>=4.1 会抛错。这里直接调用 bcrypt 库。
"""

from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid4

import bcrypt
import jwt

from app.core.config import settings

TokenType = Literal["access", "refresh"]

# bcrypt 只处理前 72 字节，超出会被静默截断——这里显式拒绝，避免“密码后半段无效”。
BCRYPT_MAX_BYTES = 72


class TokenError(Exception):
    """JWT 无效、过期或类型不匹配。"""


class WeakPasswordError(ValueError):
    """密码不满足 PRD 的复杂度要求。"""


# --------------------------------------------------------------------------- #
# 密码
# --------------------------------------------------------------------------- #
def hash_password(plain: str) -> str:
    """生成 bcrypt 哈希（自带随机盐）。"""
    encoded = plain.encode("utf-8")
    if len(encoded) > BCRYPT_MAX_BYTES:
        raise WeakPasswordError(f"密码过长（超过 {BCRYPT_MAX_BYTES} 字节）")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """校验密码。哈希串损坏时返回 False 而不是抛异常。"""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def validate_password_strength(
    password: str, *, min_length: int = 8, min_classes: int = 2
) -> None:
    """PRD §6.1.3：长度 >= 8，且包含 字母/数字/特殊字符 中至少两种。

    不满足时抛 :class:`WeakPasswordError`。
    """
    if len(password) < min_length:
        raise WeakPasswordError(f"密码长度不能少于 {min_length} 位")

    classes = 0
    if re.search(r"[A-Za-z]", password):
        classes += 1
    if re.search(r"\d", password):
        classes += 1
    if re.search(r"[^A-Za-z0-9]", password):
        classes += 1

    if classes < min_classes:
        raise WeakPasswordError("密码需包含字母、数字、特殊字符中至少两种")
    if len(password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise WeakPasswordError(f"密码过长（超过 {BCRYPT_MAX_BYTES} 字节）")


# --------------------------------------------------------------------------- #
# JWT
# --------------------------------------------------------------------------- #
def create_token(
    subject: str | UUID,
    token_type: TokenType = "access",
    *,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """签发 JWT。access 默认 30 分钟，refresh 默认 7 天。"""
    now = datetime.now(UTC)
    if expires_delta is None:
        expires_delta = (
            timedelta(minutes=settings.access_token_expire_minutes)
            if token_type == "access"
            else timedelta(days=settings.refresh_token_expire_days)
        )

    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "jti": uuid4().hex,
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str, *, expected_type: TokenType | None = None) -> dict[str, Any]:
    """解析并校验 JWT；``expected_type`` 用于区分 access / refresh。"""
    try:
        payload: dict[str, Any] = jwt.decode(
            token, settings.secret_key, algorithms=[settings.jwt_algorithm]
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token 已过期") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("token 无效") from exc

    if expected_type is not None and payload.get("type") != expected_type:
        raise TokenError(f"token 类型错误，期望 {expected_type}")
    if not payload.get("sub"):
        raise TokenError("token 缺少 sub")
    return payload


def create_token_pair(subject: str | UUID) -> dict[str, str]:
    """一次生成 access + refresh。"""
    return {
        "access_token": create_token(subject, "access"),
        "refresh_token": create_token(subject, "refresh"),
        "token_type": "bearer",
    }


# --------------------------------------------------------------------------- #
# API Key（PRD UC-05：完整明文只显示一次）
# --------------------------------------------------------------------------- #
def generate_api_key(prefix: str = "tfg") -> tuple[str, str, str]:
    """返回 ``(完整明文, 展示前缀, 用于存储的哈希)``。

    存哈希而不是明文：库被拖走也拿不到可用 Key。
    """
    raw = secrets.token_urlsafe(32)
    full = f"{prefix}_{raw}"
    shown_prefix = full[:12]
    return full, shown_prefix, hash_api_key(full)


def hash_api_key(full_key: str) -> str:
    """API Key 用 bcrypt 哈希（与密码同一套校验逻辑）。"""
    return bcrypt.hashpw(full_key.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_api_key(full_key: str, stored_hash: str) -> bool:
    return verify_password(full_key, stored_hash)


def mask_api_key(prefix: str) -> str:
    """PRD 要求：后续只显示前后各 4 位。"""
    tail = "*" * 8
    head = prefix[:4] if len(prefix) >= 4 else prefix
    return f"{head}{tail}"
