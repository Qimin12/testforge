"""路由函数：入口分发与执行后分支。"""

from __future__ import annotations

from typing import ClassVar

import pytest

from app.agents.graph import after_execute, extract_interrupt, route_entry
from app.agents.state import new_state


@pytest.mark.agents
@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("full", "case_gen"),
        ("generate", "case_gen"),
        ("execute_only", "executor"),
        ("analyze_only", "analyzer"),
        ("report_only", "report"),
    ],
)
def test_route_entry(mode: str, expected: str) -> None:
    assert route_entry(new_state(mode=mode)) == expected


@pytest.mark.agents
def test_route_entry_defaults_to_case_gen_for_unknown_mode() -> None:
    assert route_entry({"mode": "something-else"}) == "case_gen"


@pytest.mark.agents
def test_after_execute_goes_to_analyzer_when_any_failed() -> None:
    state = new_state()
    state["results"] = [{"status": "passed"}, {"status": "failed"}]
    assert after_execute(state) == "analyzer"


@pytest.mark.agents
@pytest.mark.parametrize("rows", [[], [{"status": "passed"}], [{"status": "skipped"}]])
def test_after_execute_goes_to_report_when_all_ok(rows: list[dict]) -> None:
    state = new_state()
    state["results"] = rows
    assert after_execute(state) == "report"


@pytest.mark.agents
def test_extract_interrupt_returns_none_without_interrupt() -> None:
    assert extract_interrupt({"report": {}}) is None


@pytest.mark.agents
def test_extract_interrupt_unwraps_value() -> None:
    """LangGraph 把中断包成对象，这里要能取出 dict 负载。"""

    class _Interrupt:
        value: ClassVar[dict[str, object]] = {"action": "review_test_cases", "count": 2}

    assert extract_interrupt({"__interrupt__": [_Interrupt()]}) == {
        "action": "review_test_cases",
        "count": 2,
    }
