"""Token 用量提取（CO-01 的基础）。"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from app.agents.llm import extract_usage
from app.agents.state import merge_token_usage


class _FakeMessage:
    usage_metadata: ClassVar[dict[str, Any]] = {
        "input_tokens": 120,
        "output_tokens": 80,
        "total_tokens": 200,
    }


@pytest.mark.unit
def test_extract_usage_prefixes_keys_with_scope() -> None:
    usage = extract_usage(_FakeMessage(), "case_gen")
    assert usage == {
        "case_gen.input_tokens": 120,
        "case_gen.output_tokens": 80,
        "case_gen.total_tokens": 200,
    }


@pytest.mark.unit
def test_extract_usage_without_metadata_returns_empty() -> None:
    assert extract_usage(object(), "analyzer") == {}


@pytest.mark.unit
def test_extract_usage_ignores_zero_and_non_int() -> None:
    class _Msg:
        usage_metadata: ClassVar[dict[str, Any]] = {
            "input_tokens": 0,
            "output_tokens": "8",
            "total_tokens": 7,
        }

    assert extract_usage(_Msg(), "x") == {"x.total_tokens": 7}


@pytest.mark.unit
def test_usage_from_several_nodes_accumulates() -> None:
    """四个节点各自上报，最后应汇总成一份总账。"""
    total: dict[str, int] = {}
    for scope in ("case_gen", "analyzer", "defect", "report"):
        total = merge_token_usage(total, extract_usage(_FakeMessage(), scope))

    assert total["case_gen.total_tokens"] == 200
    assert total["report.total_tokens"] == 200
    assert sum(v for k, v in total.items() if k.endswith(".total_tokens")) == 800
