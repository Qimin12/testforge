"""Executor 节点：用假 transport 测真实判定逻辑，不联网。"""

from __future__ import annotations

import httpx
import pytest

from app.agents.nodes.executor import build_client, run_case

BASE = "http://testserver"


@pytest.mark.agents
async def test_passing_case(fake_api) -> None:
    case = {"name": "健康检查", "method": "GET", "path": "/health", "expected_status": 200}
    async with build_client(BASE) as client:
        result = await run_case(client, case)

    assert result["status"] == "passed"
    assert result["error"] is None
    assert result["duration_ms"] >= 0
    assert result["assertions"][0]["passed"] is True


@pytest.mark.agents
async def test_status_code_mismatch_is_failed(fake_api) -> None:
    case = {"name": "期望 200 实际 404", "method": "GET", "path": "/users/0", "expected_status": 200}
    async with build_client(BASE) as client:
        result = await run_case(client, case)

    assert result["status"] == "failed"
    assert "404" in str(result["actual"])
    assert "404" in (result["error"] or "")


@pytest.mark.agents
async def test_json_path_assertion_passes(fake_api) -> None:
    case = {
        "name": "断言第一个用户名",
        "method": "GET",
        "path": "/users",
        "expected_status": 200,
        "assertions": [{"mode": "json_path", "target": "items.0.name", "expected": "alice"}],
    }
    async with build_client(BASE) as client:
        result = await run_case(client, case)

    assert result["status"] == "passed"


@pytest.mark.agents
async def test_json_path_assertion_fails(fake_api) -> None:
    case = {
        "name": "断言错误的用户名",
        "method": "GET",
        "path": "/users",
        "expected_status": 200,
        "assertions": [{"mode": "json_path", "target": "items.0.name", "expected": "bob"}],
    }
    async with build_client(BASE) as client:
        result = await run_case(client, case)

    assert result["status"] == "failed"
    assert result["assertions"][1]["passed"] is False


@pytest.mark.agents
async def test_header_assertion(fake_api) -> None:
    case = {
        "name": "断言响应头",
        "method": "GET",
        "path": "/health",
        "expected_status": 200,
        "assertions": [{"mode": "header", "target": "content-type", "expected": "application/json"}],
    }
    async with build_client(BASE) as client:
        result = await run_case(client, case)

    assert result["status"] == "passed"


@pytest.mark.agents
async def test_contains_assertion(fake_api) -> None:
    case = {
        "name": "断言响应文本",
        "method": "GET",
        "path": "/health",
        "expected_status": 200,
        "assertions": [{"mode": "contains", "target": "", "expected": "ok"}],
    }
    async with build_client(BASE) as client:
        result = await run_case(client, case)

    assert result["status"] == "passed"


@pytest.mark.agents
async def test_transport_error_becomes_error_result() -> None:
    """连接失败不能把整张图炸掉，要收敛成 error 结果。"""

    def _raise(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    from app.agents.nodes.executor import set_http_transport

    set_http_transport(httpx.MockTransport(_raise))
    try:
        case = {"name": "连不上", "method": "GET", "path": "/x", "expected_status": 200}
        async with build_client(BASE) as client:
            result = await run_case(client, case)
    finally:
        set_http_transport(None)

    assert result["status"] == "error"
    assert result["error"]


@pytest.mark.agents
async def test_parallel_execution_keeps_case_order(fake_api, monkeypatch) -> None:
    """TE-03：并发执行，但结果顺序必须与用例顺序一致。"""
    from app.agents.nodes.executor import executor
    from app.core.config import settings

    monkeypatch.setattr(settings, "executor_concurrency", 3)

    cases = [
        {"name": f"用例{i}", "method": "GET", "path": "/health", "expected_status": 200}
        for i in range(8)
    ]
    result = await executor({"cases": cases, "target_base_url": BASE})

    assert len(result["results"]) == 8
    assert [r["case_name"] for r in result["results"]] == [c["name"] for c in cases]
    assert all(r["status"] == "passed" for r in result["results"])


@pytest.mark.agents
async def test_empty_cases_returns_error() -> None:
    from app.agents.nodes.executor import executor

    result = await executor({"cases": [], "target_base_url": BASE})
    assert result["results"] == []
    assert result["errors"]


@pytest.mark.agents
async def test_unresolvable_json_path_is_failed_not_crash(fake_api) -> None:
    case = {
        "name": "路径不存在",
        "method": "GET",
        "path": "/health",
        "expected_status": 200,
        "assertions": [{"mode": "json_path", "target": "no.such.path", "expected": "x"}],
    }
    async with build_client(BASE) as client:
        result = await run_case(client, case)

    assert result["status"] == "failed"
