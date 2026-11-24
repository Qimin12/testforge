"""CI/CD：API Key 鉴权、质量门禁、覆盖率上报。"""

from __future__ import annotations

import pytest

BASE = "http://testserver"


@pytest.fixture()
def project_id(client, api_prefix, auth_headers, sample_spec: dict) -> str:
    created = client.post(
        f"{api_prefix}/projects",
        headers=auth_headers,
        json={"name": "CI 项目", "target_base_url": BASE},
    )
    pid = created.json()["id"]
    client.post(
        f"{api_prefix}/projects/{pid}/openapi", headers=auth_headers, json={"spec": sample_spec}
    )
    return pid


@pytest.fixture()
def api_key(client, api_prefix, auth_headers) -> str:
    created = client.post(
        f"{api_prefix}/auth/api-keys", headers=auth_headers, json={"name": "ci"}
    )
    assert created.status_code == 201
    return created.json()["full_key"]


# --------------------------------------------------------------------------- #
# 鉴权
# --------------------------------------------------------------------------- #
@pytest.mark.api
def test_ci_requires_auth(client, api_prefix) -> None:
    assert client.get(f"{api_prefix}/ci/projects").status_code == 401


@pytest.mark.api
def test_api_key_auth_works_without_jwt(client, api_prefix, api_key: str) -> None:
    """CI 里拿不到用户密码，必须能只用 API Key 调通。"""
    response = client.get(f"{api_prefix}/ci/projects", headers={"X-API-Key": api_key})
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.api
def test_invalid_api_key_rejected(client, api_prefix) -> None:
    response = client.get(f"{api_prefix}/ci/projects", headers={"X-API-Key": "tfg_wrong_key"})
    assert response.status_code == 401


@pytest.mark.api
def test_revoked_api_key_rejected(client, api_prefix, auth_headers, api_key: str) -> None:
    keys = client.get(f"{api_prefix}/auth/api-keys", headers=auth_headers).json()
    key_id = keys[0]["id"]
    client.delete(f"{api_prefix}/auth/api-keys/{key_id}", headers=auth_headers)

    response = client.get(f"{api_prefix}/ci/projects", headers={"X-API-Key": api_key})
    assert response.status_code == 401


# --------------------------------------------------------------------------- #
# 质量门禁
# --------------------------------------------------------------------------- #
@pytest.mark.api
def test_ci_run_passes_gate_when_all_green(
    client, api_prefix, api_key: str, project_id: str, fake_api
) -> None:
    health_case = {
        "name": "健康检查",
        "method": "GET",
        "path": "/health",
        "expected_status": 200,
    }
    client.post(
        f"{api_prefix}/projects/{project_id}/cases",
        headers={"X-API-Key": api_key},
        json={"cases": [health_case]},
    )

    response = client.post(
        f"{api_prefix}/ci/run",
        headers={"X-API-Key": api_key},
        json={"project_id": project_id, "mode": "execute_only", "min_pass_rate": 100},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["gate"]["passed"] is True
    assert body["pass_rate"] == 100.0
    assert body["defect_count"] == 0
    assert response.headers["X-TestForge-Gate"] == "pass"


@pytest.mark.api
def test_ci_run_fails_gate_on_low_pass_rate(
    client, api_prefix, api_key: str, project_id: str, fake_api
) -> None:
    bad_case = {
        "name": "期望 200 实际 404",
        "method": "GET",
        "path": "/users/0",
        "expected_status": 200,
    }
    client.post(
        f"{api_prefix}/projects/{project_id}/cases",
        headers={"X-API-Key": api_key},
        json={"cases": [bad_case]},
    )

    response = client.post(
        f"{api_prefix}/ci/run",
        headers={"X-API-Key": api_key},
        json={"project_id": project_id, "mode": "execute_only", "min_pass_rate": 100},
    )
    body = response.json()
    assert body["gate"]["passed"] is False
    assert body["gate"]["reasons"]
    assert response.headers["X-TestForge-Gate"] == "fail"


@pytest.mark.api
def test_ci_run_rejects_foreign_project(
    client, api_prefix, auth_headers, api_key: str, user_payload
) -> None:
    other = {
        "email": "ci-other-" + user_payload["email"],
        "password": "Passw0rd!",
    }
    client.post(f"{api_prefix}/auth/register", json=other)
    login = client.post(
        f"{api_prefix}/auth/login", json={"email": other["email"], "password": other["password"]}
    ).json()
    other_headers = {"Authorization": f"Bearer {login['access_token']}"}

    created = client.post(
        f"{api_prefix}/projects", headers=other_headers, json={"name": "别人的项目"}
    ).json()

    response = client.post(
        f"{api_prefix}/ci/run",
        headers={"X-API-Key": api_key},
        json={"project_id": created["id"], "mode": "execute_only"},
    )
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# 覆盖率
# --------------------------------------------------------------------------- #
@pytest.mark.api
def test_coverage_upload_and_query(client, api_prefix, auth_headers, project_id: str) -> None:
    upload = client.post(
        f"{api_prefix}/projects/{project_id}/coverage",
        headers=auth_headers,
        json={"total_lines": 200, "covered_lines": 150, "total_branches": 40, "covered_branches": 20},
    )
    assert upload.status_code == 201, upload.text
    body = upload.json()
    assert body["line_rate"] == 75.0
    assert body["branch_rate"] == 50.0

    latest = client.get(f"{api_prefix}/projects/{project_id}/coverage/latest", headers=auth_headers)
    assert latest.status_code == 200
    assert latest.json()["id"] == body["id"]

    listed = client.get(f"{api_prefix}/projects/{project_id}/coverage", headers=auth_headers)
    assert len(listed.json()) == 1


@pytest.mark.api
def test_coverage_accepts_direct_rates(client, api_prefix, api_key: str, project_id: str) -> None:
    response = client.post(
        f"{api_prefix}/ci/coverage?project_id={project_id}",
        headers={"X-API-Key": api_key},
        json={"line_rate": 88.5, "branch_rate": 70.2, "source": "jacoco"},
    )
    assert response.status_code == 201
    assert response.json()["line_rate"] == 88.5
    assert response.json()["source"] == "jacoco"
