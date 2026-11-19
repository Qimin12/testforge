"""定时调度字段（TE-04）与异步执行入口。"""

from __future__ import annotations

import pytest

BASE = "http://testserver"


@pytest.mark.api
def test_schedule_fields_can_be_saved(client, api_prefix, auth_headers) -> None:
    created = client.post(
        f"{api_prefix}/projects",
        headers=auth_headers,
        json={"name": "定时项目", "target_base_url": BASE},
    ).json()

    patched = client.patch(
        f"{api_prefix}/projects/{created['id']}",
        headers=auth_headers,
        json={"schedule_enabled": True, "schedule_interval_minutes": 30},
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["schedule_enabled"] is True
    assert body["schedule_interval_minutes"] == 30


@pytest.mark.api
def test_async_mode_runs_inline_when_celery_eager(
    client, api_prefix, auth_headers, sample_spec: dict, fake_api
) -> None:
    """开发环境 CELERY_EAGER=true，async_mode 请求也应当直接跑完而不是排队。"""
    created = client.post(
        f"{api_prefix}/projects",
        headers=auth_headers,
        json={"name": "异步项目", "target_base_url": BASE},
    ).json()
    client.post(
        f"{api_prefix}/projects/{created['id']}/openapi",
        headers=auth_headers,
        json={"spec": sample_spec},
    )

    response = client.post(
        f"{api_prefix}/projects/{created['id']}/run",
        headers=auth_headers,
        json={"mode": "full", "async_mode": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_cases"] > 0
    assert body["status"] in {"success", "failed"}
