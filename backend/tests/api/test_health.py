"""健康检查与元信息。"""

from __future__ import annotations

import pytest


@pytest.mark.api
def test_health_ok(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "TestForge"
    assert body["database"]["driver"] == "sqlite"


@pytest.mark.api
def test_health_reports_component_state(client) -> None:
    body = client.get("/health").json()

    # 测试环境固定 memory 检查点 + mock 模型
    assert body["checkpointer"]["kind"] == "memory"
    assert body["llm"]["mock"] is True
    assert "model_large" in body["llm"]


@pytest.mark.api
def test_root_endpoint(client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["docs"] == "/docs"


@pytest.mark.api
def test_openapi_schema_is_served(client) -> None:
    """PRD §8.5 要求提供 OpenAPI 文档。"""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "/api/v1/auth/login" in response.json()["paths"]
