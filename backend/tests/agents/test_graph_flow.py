"""整图行为：全链路跑通、模式分发、人工审核中断与恢复。"""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app.agents.graph import build_graph, thread_config
from app.agents.state import new_state

BASE = "http://testserver"


def _graph():
    """每个用例一张独立的图，带独立检查点，互不干扰。"""
    return build_graph(MemorySaver())


@pytest.mark.agents
async def test_full_mode_end_to_end(fake_api, sample_spec: dict) -> None:
    graph = _graph()
    state = new_state(
        mode="full", run_id="r-full", target_base_url=BASE, api_spec=sample_spec
    )

    result = await graph.ainvoke(state, thread_config("t-full"))

    assert result["cases"], "应生成用例"
    assert result["results"], "应执行用例"
    assert len(result["results"]) == len(result["cases"])

    report = result["report"]
    assert report["total"] == len(result["results"])
    assert 0.0 <= report["pass_rate"] <= 100.0
    assert report["summary"]
    assert report["risk_level"] in {"low", "medium", "high"}


@pytest.mark.agents
async def test_failures_trigger_analysis_and_defects(fake_api, sample_spec: dict) -> None:
    """假 API 会让部分用例失败，图应自动进入分析→缺陷分支。"""
    graph = _graph()
    state = new_state(mode="full", target_base_url=BASE, api_spec=sample_spec)

    result = await graph.ainvoke(state, thread_config("t-fail"))

    assert result["report"]["failed"] > 0
    assert result["analysis"]["items"], "失败用例必须进入分析"
    assert result["defects"], "分析后必须产出缺陷条目"
    for defect in result["defects"]:
        assert defect["severity"] in {"blocker", "critical", "major", "minor"}
        assert defect["category"] in {"functional", "performance", "security"}
        assert defect["fingerprint"]


@pytest.mark.agents
async def test_execute_only_mode_skips_generation(fake_api) -> None:
    graph = _graph()
    cases = [{"name": "健康检查", "method": "GET", "path": "/health", "expected_status": 200}]
    state = new_state(mode="execute_only", target_base_url=BASE, cases=cases)

    result = await graph.ainvoke(state, thread_config("t-exec"))

    assert len(result["results"]) == 1
    assert result["report"]["total"] == 1
    # 没有 api_spec 也不该报错，因为根本没走生成节点
    assert not [e for e in result.get("errors", []) if "api_spec" in e]


@pytest.mark.agents
async def test_report_only_mode_builds_report_from_results(fake_api) -> None:
    graph = _graph()
    state = new_state(mode="report_only")
    state["results"] = [
        {"case_name": "a", "status": "passed", "duration_ms": 10},
        {"case_name": "b", "status": "failed", "duration_ms": 20},
    ]

    result = await graph.ainvoke(state, thread_config("t-report"))

    assert result["report"]["total"] == 2
    assert result["report"]["failed"] == 1


@pytest.mark.agents
async def test_review_interrupt_then_resume(fake_api, sample_spec: dict, monkeypatch) -> None:
    """TG-04：开启审核后图应挂起，给 approve 后从断点继续跑完。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "require_review", True)

    graph = _graph()
    config = thread_config("t-review")
    state = new_state(mode="full", target_base_url=BASE, api_spec=sample_spec)

    paused = await graph.ainvoke(state, config)
    assert "__interrupt__" in paused, "开启审核后必须中断"

    payload = paused["__interrupt__"][0].value
    assert payload["action"] == "review_test_cases"
    assert payload["count"] == len(payload["cases"])

    resumed = await graph.ainvoke(Command(resume={"approved": True}), config)
    assert resumed.get("report"), "恢复后应跑完并产出报告"
    assert resumed["report"]["total"] > 0


@pytest.mark.agents
async def test_review_rejection_stops_execution(fake_api, sample_spec: dict, monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "require_review", True)

    graph = _graph()
    config = thread_config("t-reject")
    state = new_state(mode="full", target_base_url=BASE, api_spec=sample_spec)

    await graph.ainvoke(state, config)
    resumed = await graph.ainvoke(
        Command(resume={"approved": False, "reason": "用例质量不达标"}), config
    )

    assert resumed["results"] == [] or all(
        r["status"] != "passed" for r in resumed.get("results", [])
    )
    assert any("审核未通过" in e for e in resumed.get("errors", []))
