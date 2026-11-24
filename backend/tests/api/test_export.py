"""报告导出（RP-05）与 token 用量（CO-01/CO-04）。"""

from __future__ import annotations

import json

import pytest

BASE = "http://testserver"


@pytest.fixture()
def execution_id(client, api_prefix, auth_headers, sample_spec: dict, fake_api) -> str:
    created = client.post(
        f"{api_prefix}/projects",
        headers=auth_headers,
        json={"name": "导出项目", "target_base_url": BASE},
    ).json()
    pid = created["id"]
    client.post(
        f"{api_prefix}/projects/{pid}/openapi", headers=auth_headers, json={"spec": sample_spec}
    )
    run = client.post(
        f"{api_prefix}/projects/{pid}/run", headers=auth_headers, json={"mode": "full"}
    )
    assert run.status_code == 200, run.text
    return run.json()["id"]


@pytest.mark.api
def test_export_json(client, api_prefix, auth_headers, execution_id: str) -> None:
    response = client.get(
        f"{api_prefix}/executions/{execution_id}/export?format=json", headers=auth_headers
    )
    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]

    payload = json.loads(response.content)
    assert payload["execution"]["id"] == execution_id
    assert isinstance(payload["results"], list)
    assert payload["execution"]["total_cases"] == len(payload["results"])


@pytest.mark.api
def test_export_markdown(client, api_prefix, auth_headers, execution_id: str) -> None:
    response = client.get(
        f"{api_prefix}/executions/{execution_id}/export?format=markdown", headers=auth_headers
    )
    assert response.status_code == 200
    text = response.content.decode()
    assert text.startswith("# 测试报告")
    assert "通过率" in text
    assert "## 用例结果" in text


@pytest.mark.api
def test_export_csv(client, api_prefix, auth_headers, execution_id: str) -> None:
    response = client.get(
        f"{api_prefix}/executions/{execution_id}/export?format=csv", headers=auth_headers
    )
    assert response.status_code == 200
    lines = response.content.decode().strip().splitlines()
    assert lines[0].startswith("用例,状态")
    assert len(lines) > 1


@pytest.mark.api
def test_export_xlsx(client, api_prefix, auth_headers, execution_id: str) -> None:
    response = client.get(
        f"{api_prefix}/executions/{execution_id}/export?format=xlsx", headers=auth_headers
    )
    if response.status_code == 501:  # 没装 openpyxl
        pytest.skip("环境未安装 openpyxl")
    assert response.status_code == 200
    assert response.content[:2] == b"PK"  # xlsx 就是 zip


@pytest.mark.api
def test_export_rejects_unknown_format(client, api_prefix, auth_headers, execution_id: str) -> None:
    response = client.get(
        f"{api_prefix}/executions/{execution_id}/export?format=pdf", headers=auth_headers
    )
    assert response.status_code == 422  # Query pattern 校验


@pytest.mark.api
def test_export_requires_ownership(client, api_prefix, execution_id: str) -> None:
    assert (
        client.get(f"{api_prefix}/executions/{execution_id}/export?format=json").status_code == 401
    )


@pytest.mark.api
def test_usage_endpoint(client, api_prefix, auth_headers, execution_id: str) -> None:
    response = client.get(f"{api_prefix}/usage", headers=auth_headers)
    assert response.status_code == 200

    body = response.json()
    assert "period" in body
    assert body["budget"] > 0
    assert isinstance(body["by_node"], dict)
    assert body["used_ratio"] >= 0
