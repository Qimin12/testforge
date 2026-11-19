"""密码 / JWT / API Key 的纯逻辑测试。"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.security import (
    TokenError,
    WeakPasswordError,
    create_token,
    create_token_pair,
    decode_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    mask_api_key,
    validate_password_strength,
    verify_api_key,
    verify_password,
)


# --------------------------------------------------------------------------- #
# 密码
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_hash_is_salted_and_verifiable() -> None:
    hashed = hash_password("Passw0rd!")
    assert hashed != "Passw0rd!"
    assert hashed.startswith("$2")
    assert verify_password("Passw0rd!", hashed) is True


@pytest.mark.unit
def test_same_password_hashes_differ() -> None:
    """bcrypt 自带随机盐：同一密码两次哈希不能相同。"""
    assert hash_password("Passw0rd!") != hash_password("Passw0rd!")


@pytest.mark.unit
def test_verify_rejects_wrong_password() -> None:
    hashed = hash_password("Passw0rd!")
    assert verify_password("passw0rd!", hashed) is False


@pytest.mark.unit
def test_verify_tolerates_broken_hash() -> None:
    """哈希串损坏时返回 False，而不是抛异常把接口打成 500。"""
    assert verify_password("x", "not-a-bcrypt-hash") is False


@pytest.mark.unit
@pytest.mark.parametrize(
    "password",
    [
        "short1!",       # 太短
        "aaaaaaaa",      # 只有一类字符
        "12345678",      # 只有数字
    ],
)
def test_weak_passwords_rejected(password: str) -> None:
    with pytest.raises(WeakPasswordError):
        validate_password_strength(password)


@pytest.mark.unit
@pytest.mark.parametrize("password", ["Passw0rd!", "abcd1234", "abcd!@#$"])
def test_acceptable_passwords(password: str) -> None:
    validate_password_strength(password)  # 不抛异常即通过


@pytest.mark.unit
def test_overlong_password_rejected() -> None:
    with pytest.raises(WeakPasswordError):
        validate_password_strength("A1!" + "x" * 80)


# --------------------------------------------------------------------------- #
# JWT
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_token_roundtrip() -> None:
    token = create_token("user-123", "access")
    claims = decode_token(token, expected_type="access")
    assert claims["sub"] == "user-123"
    assert claims["type"] == "access"
    assert "jti" in claims


@pytest.mark.unit
def test_token_pair_has_both_types() -> None:
    pair = create_token_pair("user-123")
    assert decode_token(pair["access_token"], expected_type="access")["type"] == "access"
    assert decode_token(pair["refresh_token"], expected_type="refresh")["type"] == "refresh"


@pytest.mark.unit
def test_refresh_token_rejected_as_access() -> None:
    pair = create_token_pair("user-123")
    with pytest.raises(TokenError):
        decode_token(pair["refresh_token"], expected_type="access")


@pytest.mark.unit
def test_expired_token_rejected() -> None:
    token = create_token("user-123", "access", expires_delta=timedelta(seconds=-5))
    with pytest.raises(TokenError):
        decode_token(token)


@pytest.mark.unit
def test_garbage_token_rejected() -> None:
    with pytest.raises(TokenError):
        decode_token("abc.def.ghi")


# --------------------------------------------------------------------------- #
# API Key
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_api_key_generation_shape() -> None:
    full, prefix, stored = generate_api_key()
    assert full.startswith("tfg_")
    assert full.startswith(prefix)
    assert stored != full
    assert verify_api_key(full, stored) is True


@pytest.mark.unit
def test_api_key_hash_roundtrip() -> None:
    full = "tfg_demo-key-value"
    assert verify_api_key(full, hash_api_key(full)) is True
    assert verify_api_key("tfg_other", hash_api_key(full)) is False


@pytest.mark.unit
def test_mask_keeps_only_head() -> None:
    masked = mask_api_key("tfg_abcdefgh")
    assert masked.startswith("tfg_")
    assert "abcdefgh" not in masked
