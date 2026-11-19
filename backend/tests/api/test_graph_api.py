"""图运行接口（/graph/run、/graph/resume）。"""

from __future__ import annotations

import pytest

BASE = "http://testserver"


@pytest.mark.api
def test_run_requires_authentication(client, api_prefix, sample_spec) -> None:
    response = client.post(
        f"{api_prefix}/graph/run",
        json={"mode": "full", "api_spec": sample_spec, "target_base_url": BASE},
    )
    assert response.status_code == 401


@pytest.mark.api
def test_full_mode_run(client, api_prefix, auth_headers, sample_spec, fake_api) -> None:
    response = client.post(
        f"{api_prefix}/graph/run",
        headers=auth_headers,
        json={"mode": "full", "api_spec": sample_spec, "target_base_url": BASE},
    )
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["thread_id"]
    assert body["interrupted"] is False
    assert body["summary"]["results"] > 0
    assert body["summary"]["report"]


@pytest.mark.api
def test_full_mode_requires_spec(client, api_prefix, auth_headers) -> None:
    response = client.post(
        f"{api_prefix}/graph/run", headers=auth_headers, json={"mode": "full"}
    )
    assert response.status_code == 422


@pytest.mark.api
def test_execute_only_requires_cases(client, api_prefix, auth_headers) -> None:
    response = client.post(
        f"{api_prefix}/graph/run", headers=auth_headers, json={"mode": "execute_only"}
    )
    assert response.status_code == 422


@pytest.mark.api
def test_execute_only_run(client, api_prefix, auth_headers, fake_api) -> None:
    cases = [{"name": "健康检查", "method": "GET", "path": "/health", "expected_status": 200}]
    response = client.post(
        f"{api_prefix}/graph/run",
        headers=auth_headers,
        json={"mode": "execute_only", "target_base_url": BASE, "cases": cases},
    )
    assert response.status_code == 200
    assert response.json()["summary"]["results"] == 1


@pytest.mark.api
def test_unknown_mode_rejected(client, api_prefix, auth_headers, sample_spec) -> None:
    response = client.post(
        f"{api_prefix}/graph/run",
        headers=auth_headers,
        json={"mode": "not-a-mode", "api_spec": sample_spec},
    )
    assert response.status_code == 422


@pytest.mark.api
def test_review_interrupt_and_resume_via_api(
    client, api_prefix, auth_headers, sample_spec, fake_api, monkeypatch
) -> None:
    """TG-04 的完整 HTTP 流程：挂起 → 拿到待审用例 → 恢复 → 出报告。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "require_review", True)

    paused = client.post(
        f"{api_prefix}/graph/run",
        headers=auth_headers,
        json={"mode": "full", "api_spec": sample_spec, "target_base_url": BASE},
    )
    assert paused.status_code == 200
    body = paused.json()
    assert body["interrupted"] is True
    assert body["pending"]["action"] == "review_test_cases"
    assert body["pending"]["cases"]

    resumed = client.post(
        f"{api_prefix}/graph/resume",
        headers=auth_headers,
        json={"thread_id": body["thread_id"], "decision": {"approved": True}},
    )
    assert resumed.status_code == 200
    assert resumed.json()["interrupted"] is False
    assert resumed.json()["summary"]["report"]
