"""执行记录：项目发起执行 → 落库 → 查询 → 人工审核恢复。"""

from __future__ import annotations

import pytest

BASE = "http://testserver"


@pytest.fixture()
def project_id(client, api_prefix, auth_headers, sample_spec: dict) -> str:
    created = client.post(
        f"{api_prefix}/projects",
        headers=auth_headers,
        json={"name": "回归项目", "target_base_url": BASE},
    )
    assert created.status_code == 201, created.text
    pid = created.json()["id"]

    imported = client.post(
        f"{api_prefix}/projects/{pid}/openapi",
        headers=auth_headers,
        json={"spec": sample_spec},
    )
    assert imported.status_code == 200, imported.text
    return pid


@pytest.mark.api
def test_run_project_persists_everything(
    client, api_prefix, auth_headers, project_id: str, fake_api
) -> None:
    """一次执行之后：结果、缺陷、报告都要能在数据库里查回来。"""
    response = client.post(
        f"{api_prefix}/projects/{project_id}/run", headers=auth_headers, json={"mode": "full"}
    )
    assert response.status_code == 200, response.text

    body = response.json()
    execution_id = body["id"]

    assert body["total_cases"] > 0
    assert len(body["results"]) == body["total_cases"]
    assert body["status"] in {"success", "failed"}
    assert body["report"] and body["report"]["total"] == body["total_cases"]
    assert body["duration_ms"] is not None

    # 详情接口能读回同样的内容
    detail = client.get(f"{api_prefix}/executions/{execution_id}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["id"] == execution_id
    assert len(detail.json()["results"]) == body["total_cases"]

    # 报告接口
    report = client.get(f"{api_prefix}/executions/{execution_id}/report", headers=auth_headers)
    assert report.status_code == 200
    assert report.json()["report"]["summary"]


@pytest.mark.api
def test_generated_cases_are_saved_to_project(
    client, api_prefix, auth_headers, project_id: str, fake_api
) -> None:
    client.post(
        f"{api_prefix}/projects/{project_id}/run", headers=auth_headers, json={"mode": "full"}
    )
    cases = client.get(f"{api_prefix}/projects/{project_id}/cases", headers=auth_headers)
    assert cases.status_code == 200
    assert cases.json()["total"] > 0
    assert all(row["source"] == "ai" for row in cases.json()["items"])


@pytest.mark.api
def test_failures_produce_defects(
    client, api_prefix, auth_headers, project_id: str, fake_api
) -> None:
    body = client.post(
        f"{api_prefix}/projects/{project_id}/run", headers=auth_headers, json={"mode": "full"}
    ).json()

    if body["failed_cases"] == 0:  # pragma: no cover - 假 API 下通常会有失败
        pytest.skip("本次没有失败用例，跳过缺陷断言")

    defects = client.get(f"{api_prefix}/defects?project_id={project_id}", headers=auth_headers)
    assert defects.status_code == 200
    rows = defects.json()["items"]
    assert rows, "有失败用例就必须有缺陷记录"
    assert all(row["severity"] for row in rows)
    assert all(row["fingerprint"] for row in rows)


@pytest.mark.api
def test_execute_only_reuses_saved_cases(
    client, api_prefix, auth_headers, project_id: str, fake_api
) -> None:
    client.post(
        f"{api_prefix}/projects/{project_id}/run", headers=auth_headers, json={"mode": "full"}
    )

    second = client.post(
        f"{api_prefix}/projects/{project_id}/run",
        headers=auth_headers,
        json={"mode": "execute_only"},
    )
    assert second.status_code == 200, second.text
    assert second.json()["total_cases"] > 0


@pytest.mark.api
def test_list_executions_counts(client, api_prefix, auth_headers, project_id: str, fake_api) -> None:
    client.post(
        f"{api_prefix}/projects/{project_id}/run", headers=auth_headers, json={"mode": "full"}
    )
    listed = client.get(f"{api_prefix}/executions", headers=auth_headers)
    assert listed.status_code == 200
    assert listed.json()["total"] >= 1
    assert listed.json()["items"][0]["pass_rate"] >= 0


@pytest.mark.api
def test_run_without_openapi_is_rejected(client, api_prefix, auth_headers) -> None:
    created = client.post(
        f"{api_prefix}/projects",
        headers=auth_headers,
        json={"name": "空项目", "target_base_url": BASE},
    ).json()

    response = client.post(
        f"{api_prefix}/projects/{created['id']}/run", headers=auth_headers, json={"mode": "full"}
    )
    assert response.status_code == 400
    assert "OpenAPI" in response.json()["detail"]


@pytest.mark.api
def test_run_without_base_url_is_rejected(
    client, api_prefix, auth_headers, sample_spec: dict
) -> None:
    created = client.post(
        f"{api_prefix}/projects", headers=auth_headers, json={"name": "没地址"}
    ).json()
    client.post(
        f"{api_prefix}/projects/{created['id']}/openapi",
        headers=auth_headers,
        json={"spec": sample_spec},
    )

    response = client.post(
        f"{api_prefix}/projects/{created['id']}/run", headers=auth_headers, json={"mode": "full"}
    )
    assert response.status_code == 400
    assert "地址" in response.json()["detail"]


@pytest.mark.api
def test_review_interrupt_then_resume_execution(
    client, api_prefix, auth_headers, project_id: str, fake_api, monkeypatch
) -> None:
    """TG-04 + 落库：中断时执行状态为 interrupted，恢复后结果补齐。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "require_review", True)

    paused = client.post(
        f"{api_prefix}/projects/{project_id}/run", headers=auth_headers, json={"mode": "full"}
    )
    assert paused.status_code == 200, paused.text
    body = paused.json()
    assert body["status"] == "interrupted"
    assert body["results"] == []

    resumed = client.post(
        f"{api_prefix}/executions/{body['id']}/resume",
        headers=auth_headers,
        json={"approved": True},
    )
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["status"] in {"success", "failed"}
    assert resumed.json()["total_cases"] > 0
    assert resumed.json()["results"]


@pytest.mark.api
def test_defect_status_can_be_updated(
    client, api_prefix, auth_headers, project_id: str, fake_api
) -> None:
    body = client.post(
        f"{api_prefix}/projects/{project_id}/run", headers=auth_headers, json={"mode": "full"}
    ).json()
    if body["failed_cases"] == 0:  # pragma: no cover
        pytest.skip("本次没有缺陷可改")

    defect_id = body["defects"][0]["id"]
    updated = client.patch(
        f"{api_prefix}/defects/{defect_id}?new_status=fixed", headers=auth_headers
    )
    assert updated.status_code == 200
    assert updated.json()["items"][0]["status"] == "fixed"
