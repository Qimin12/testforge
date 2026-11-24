"""Case Generator 节点。"""

from __future__ import annotations

import pytest

from app.agents.nodes.case_gen import case_gen


@pytest.mark.agents
async def test_generates_cases_from_spec(sample_spec: dict) -> None:
    result = await case_gen({"api_spec": sample_spec})

    cases = result["cases"]
    assert cases, "mock 模式应能从 spec 生成用例"
    assert not result.get("errors")

    for case in cases:
        assert case["path"].startswith("/"), "path 必须是相对路径"
        assert case["method"] in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
        assert isinstance(case["expected_status"], int)
        assert isinstance(case["assertions"], list)
        assert case["source"] == "ai"


@pytest.mark.agents
async def test_generates_negative_case_for_post(sample_spec: dict) -> None:
    result = await case_gen({"api_spec": sample_spec})
    categories = {c["category"] for c in result["cases"]}
    assert {"happy", "negative"} <= categories


@pytest.mark.agents
async def test_missing_spec_returns_error_without_crashing() -> None:
    result = await case_gen({"api_spec": {}})
    assert result["cases"] == []
    assert result["errors"], "缺 spec 必须给出可读错误"


@pytest.mark.agents
async def test_spec_without_paths_returns_error() -> None:
    result = await case_gen({"api_spec": {"info": {"title": "x"}}})
    assert result["cases"] == []
    assert any("paths" in e for e in result["errors"])


@pytest.mark.agents
async def test_respects_max_cases_limit(sample_spec: dict, monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_cases_per_run", 2)
    result = await case_gen({"api_spec": sample_spec})
    assert len(result["cases"]) <= 2
