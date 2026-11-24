"""项目接口：CRUD、OpenAPI 导入、用例入库、发起执行。"""

from __future__ import annotations

import pytest


@pytest.fixture()
def project(client, api_prefix, auth_headers) -> dict:
    response = client.post(
        f"{api_prefix}/projects",
        headers=auth_headers,
        json={
            "name": "示例项目",
            "description": "端到端测试用",
            "target_base_url": "http://testserver",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.api
def test_create_project(project: dict) -> None:
    assert project["name"] == "示例项目"
    assert project["status"] == "active"
    assert project["target_base_url"] == "http://testserver"
    assert project["case_count"] == 0


@pytest.mark.api
def test_create_project_requires_auth(client, api_prefix) -> None:
    assert client.post(f"{api_prefix}/projects", json={"name": "x"}).status_code == 401


@pytest.mark.api
def test_list_and_get_project(client, api_prefix, auth_headers, project: dict) -> None:
    listed = client.get(f"{api_prefix}/projects", headers=auth_headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    detail = client.get(f"{api_prefix}/projects/{project['id']}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["id"] == project["id"]


@pytest.mark.api
def test_update_project(client, api_prefix, auth_headers, project: dict) -> None:
    response = client.patch(
        f"{api_prefix}/projects/{project['id']}",
        headers=auth_headers,
        json={"name": "改名后", "target_base_url": "http://other:9000"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "改名后"
    assert body["target_base_url"] == "http://other:9000"


@pytest.mark.api
def test_archive_project(client, api_prefix, auth_headers, project: dict) -> None:
    assert (
        client.delete(f"{api_prefix}/projects/{project['id']}", headers=auth_headers).status_code
        == 204
    )
    detail = client.get(f"{api_prefix}/projects/{project['id']}", headers=auth_headers)
    assert detail.json()["status"] == "archived"


@pytest.mark.api
def test_other_user_cannot_see_project(
    client, api_prefix, auth_headers, project: dict, user_payload
) -> None:
    """越权访问一律 404，不暴露项目是否存在。"""
    other = {
        "email": "other-" + user_payload["email"],
        "password": "Passw0rd!",
        "nickname": "other",
    }
    client.post(f"{api_prefix}/auth/register", json=other)
    login = client.post(
        f"{api_prefix}/auth/login", json={"email": other["email"], "password": other["password"]}
    ).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}

    assert (
        client.get(f"{api_prefix}/projects/{project['id']}", headers=headers).status_code == 404
    )


# --------------------------------------------------------------------------- #
# PM-03 OpenAPI 导入
# --------------------------------------------------------------------------- #
@pytest.mark.api
def test_import_openapi(client, api_prefix, auth_headers, project: dict, sample_spec: dict) -> None:
    response = client.post(
        f"{api_prefix}/projects/{project['id']}/openapi",
        headers=auth_headers,
        json={"spec": sample_spec},
    )
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["operation_count"] == 3
    assert {(op["method"], op["path"]) for op in body["operations"]} == {
        ("GET", "/users"),
        ("POST", "/users"),
        ("GET", "/users/{id}"),
    }

    detail = client.get(f"{api_prefix}/projects/{project['id']}", headers=auth_headers).json()
    assert detail["operation_count"] == 2  # paths 的条数（/users 与 /users/{id}）


@pytest.mark.api
def test_import_invalid_openapi(client, api_prefix, auth_headers, project: dict) -> None:
    response = client.post(
        f"{api_prefix}/projects/{project['id']}/openapi",
        headers=auth_headers,
        json={"spec": {"foo": "bar"}},
    )
    assert response.status_code == 400


# --------------------------------------------------------------------------- #
# 用例入库与编辑
# --------------------------------------------------------------------------- #
@pytest.mark.api
def test_bulk_create_cases_and_dedupe(client, api_prefix, auth_headers, project: dict) -> None:
    payload = {
        "cases": [
            {"name": "健康检查", "method": "GET", "path": "/health", "expected_status": 200},
            {"name": "列用户", "method": "GET", "path": "/users", "expected_status": 200},
        ]
    }
    created = client.post(
        f"{api_prefix}/projects/{project['id']}/cases", headers=auth_headers, json=payload
    )
    assert created.status_code == 201
    assert created.json()["total"] == 2

    # 同名再提交一次不会重复入库
    again = client.post(
        f"{api_prefix}/projects/{project['id']}/cases", headers=auth_headers, json=payload
    )
    assert again.json()["total"] == 0


@pytest.mark.api
def test_update_and_delete_case(client, api_prefix, auth_headers, project: dict) -> None:
    created = client.post(
        f"{api_prefix}/projects/{project['id']}/cases",
        headers=auth_headers,
        json={"cases": [{"name": "用例A", "method": "GET", "path": "/a"}]},
    ).json()["items"][0]
    case_id = created["id"]

    patched = client.patch(
        f"{api_prefix}/cases/{case_id}",
        headers=auth_headers,
        json={"name": "用例A-改", "assertions": [{"mode": "status_code", "expected": 204}]},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "用例A-改"
    assert patched.json()["version"] == 2

    assert client.delete(f"{api_prefix}/cases/{case_id}", headers=auth_headers).status_code == 204
    assert client.get(f"{api_prefix}/cases/{case_id}", headers=auth_headers).status_code == 404
