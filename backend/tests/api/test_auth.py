"""用户中心接口：注册、登录、个人信息、API Key。"""

from __future__ import annotations

import pytest


@pytest.mark.api
def test_register_returns_user(client, api_prefix, user_payload) -> None:
    response = client.post(f"{api_prefix}/auth/register", json=user_payload)
    assert response.status_code == 201, response.text

    body = response.json()
    assert body["email"] == user_payload["email"]
    assert body["role"] == "qa"
    assert body["is_active"] is True
    assert "password" not in body and "hashed_password" not in body


@pytest.mark.api
def test_duplicate_email_conflicts(client, api_prefix, user_payload) -> None:
    assert client.post(f"{api_prefix}/auth/register", json=user_payload).status_code == 201
    assert client.post(f"{api_prefix}/auth/register", json=user_payload).status_code == 409


@pytest.mark.api
@pytest.mark.parametrize("password", ["short", "aaaaaaaa"])
def test_weak_password_rejected(client, api_prefix, password: str) -> None:
    """PRD §6.1.3 的复杂度规则。"""
    response = client.post(
        f"{api_prefix}/auth/register",
        json={"email": f"w{password}@example.com", "password": password},
    )
    assert response.status_code == 400


@pytest.mark.api
def test_login_success_returns_token_pair(client, api_prefix, user_payload) -> None:
    client.post(f"{api_prefix}/auth/register", json=user_payload)
    response = client.post(
        f"{api_prefix}/auth/login",
        json={"email": user_payload["email"], "password": user_payload["password"]},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["access_token"] and body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0


@pytest.mark.api
def test_login_wrong_password(client, api_prefix, user_payload) -> None:
    client.post(f"{api_prefix}/auth/register", json=user_payload)
    response = client.post(
        f"{api_prefix}/auth/login",
        json={"email": user_payload["email"], "password": "Wr0ng!pass"},
    )
    assert response.status_code == 401


@pytest.mark.api
def test_login_unknown_email(client, api_prefix) -> None:
    response = client.post(
        f"{api_prefix}/auth/login",
        json={"email": "nobody@example.com", "password": "Passw0rd!"},
    )
    assert response.status_code == 401


@pytest.mark.api
def test_me_requires_token(client, api_prefix) -> None:
    assert client.get(f"{api_prefix}/auth/me").status_code == 401


@pytest.mark.api
def test_me_returns_current_user(client, api_prefix, auth_headers, user_payload) -> None:
    response = client.get(f"{api_prefix}/auth/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["email"] == user_payload["email"]


@pytest.mark.api
def test_update_profile(client, api_prefix, auth_headers) -> None:
    response = client.patch(
        f"{api_prefix}/auth/me", headers=auth_headers, json={"nickname": "新昵称"}
    )
    assert response.status_code == 200
    assert response.json()["nickname"] == "新昵称"


@pytest.mark.api
def test_api_key_full_value_shown_once(client, api_prefix, auth_headers) -> None:
    """PRD UC-05：完整 Key 只在创建时返回，列表里必须遮罩。"""
    created = client.post(f"{api_prefix}/auth/api-keys", headers=auth_headers, json={"name": "ci"})
    assert created.status_code == 201
    full_key = created.json()["full_key"]
    assert full_key.startswith("tfg_")

    listed = client.get(f"{api_prefix}/auth/api-keys", headers=auth_headers)
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    assert full_key not in str(rows), "列表不得回显完整 Key"
    assert "*" in rows[0]["prefix"]


@pytest.mark.api
def test_delete_api_key(client, api_prefix, auth_headers) -> None:
    created = client.post(f"{api_prefix}/auth/api-keys", headers=auth_headers, json={"name": "tmp"})
    key_id = created.json()["id"]

    deleted = client.delete(f"{api_prefix}/auth/api-keys/{key_id}", headers=auth_headers)
    assert deleted.status_code == 204

    rows = client.get(f"{api_prefix}/auth/api-keys", headers=auth_headers).json()
    assert rows == []


@pytest.mark.api
def test_refresh_token_issues_new_pair(client, api_prefix, user_payload) -> None:
    client.post(f"{api_prefix}/auth/register", json=user_payload)
    login = client.post(
        f"{api_prefix}/auth/login",
        json={"email": user_payload["email"], "password": user_payload["password"]},
    ).json()

    refreshed = client.post(
        f"{api_prefix}/auth/refresh", json={"refresh_token": login["refresh_token"]}
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]


@pytest.mark.api
def test_access_token_cannot_be_used_as_refresh(client, api_prefix, user_payload) -> None:
    client.post(f"{api_prefix}/auth/register", json=user_payload)
    login = client.post(
        f"{api_prefix}/auth/login",
        json={"email": user_payload["email"], "password": user_payload["password"]},
    ).json()

    response = client.post(
        f"{api_prefix}/auth/refresh", json={"refresh_token": login["access_token"]}
    )
    assert response.status_code == 401
