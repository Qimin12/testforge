"""图状态 reducer 与摘要。"""

from __future__ import annotations

import pytest

from app.agents.state import is_failed_result, merge_token_usage, new_state, summarize


@pytest.mark.unit
def test_merge_token_usage_sums_per_key() -> None:
    left = {"large": 100, "small": 10}
    right = {"large": 50, "small": 5}
    assert merge_token_usage(left, right) == {"large": 150, "small": 15}


@pytest.mark.unit
def test_merge_token_usage_handles_none() -> None:
    assert merge_token_usage(None, {"a": 1}) == {"a": 1}
    assert merge_token_usage({"a": 1}, None) == {"a": 1}
    assert merge_token_usage(None, None) == {}


@pytest.mark.unit
def test_merge_token_usage_does_not_mutate_input() -> None:
    left = {"a": 1}
    merge_token_usage(left, {"a": 2})
    assert left == {"a": 1}


@pytest.mark.unit
def test_new_state_has_required_defaults() -> None:
    state = new_state(mode="full", run_id="r1", project_id="p1")
    assert state["mode"] == "full"
    assert state["run_id"] == "r1"
    assert state["cases"] == []
    assert state["errors"] == []
    assert state["token_usage"] == {}


@pytest.mark.unit
def test_new_state_does_not_share_mutable_defaults() -> None:
    """两个 state 的 list 必须是各自独立的，否则会串数据。"""
    a = new_state()
    b = new_state()
    a["errors"].append("boom")
    assert b["errors"] == []


@pytest.mark.unit
@pytest.mark.parametrize("status", ["failed", "error"])
def test_is_failed_result_true(status: str) -> None:
    assert is_failed_result({"status": status}) is True


@pytest.mark.unit
@pytest.mark.parametrize("status", ["passed", "skipped", None])
def test_is_failed_result_false(status: str | None) -> None:
    assert is_failed_result({"status": status}) is False


@pytest.mark.unit
def test_summarize_counts_passed_and_failed() -> None:
    state = new_state()
    state["results"] = [
        {"status": "passed"},
        {"status": "failed"},
        {"status": "error"},
    ]
    state["cases"] = [{}, {}]
    state["defects"] = [{}]
    summary = summarize(state)

    assert summary["results"] == 3
    assert summary["passed"] == 1
    assert summary["failed"] == 2
    assert summary["cases"] == 2
    assert summary["defects"] == 1
