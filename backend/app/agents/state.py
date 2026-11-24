"""图的共享状态。

这是整个测试链路的数据契约：每个节点只返回自己负责的字段，
LangGraph 负责合并。``errors`` 与 ``token_usage`` 用 reducer 累加，
其余字段是覆盖语义。
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict

# 图入口支持的运行模式（对应「只生成 / 只执行 / 只分析 / 只出报告」的复用场景）
GraphMode = Literal["full", "generate", "execute_only", "analyze_only", "report_only"]

GRAPH_MODES: tuple[str, ...] = (
    "full",
    "generate",
    "execute_only",
    "analyze_only",
    "report_only",
)


def merge_token_usage(left: dict[str, int] | None, right: dict[str, int] | None) -> dict[str, int]:
    """按节点/模型累加 token 用量（CO-01）。"""
    merged = dict(left or {})
    for key, value in (right or {}).items():
        merged[key] = merged.get(key, 0) + int(value)
    return merged


class TestForgeState(TypedDict, total=False):
    """一次测试执行在图中的全部状态。"""

    # --- 输入 ---
    mode: str                       # GraphMode
    run_id: str                     # executions.id
    project_id: str
    target_base_url: str            # 被测服务地址
    api_spec: dict[str, Any]        # OpenAPI 文档（已解析为 dict）

    # --- 中间产物 ---
    cases: list[dict[str, Any]]     # case_gen 产出 / 或外部传入
    review: dict[str, Any]          # review 节点的人工决策
    results: list[dict[str, Any]]   # executor 产出
    analysis: dict[str, Any]        # analyzer 产出
    defects: list[dict[str, Any]]   # defect 产出

    # --- 输出 ---
    report: dict[str, Any]

    # --- 累加型 ---
    errors: Annotated[list[str], operator.add]
    token_usage: Annotated[dict[str, int], merge_token_usage]


def new_state(
    *,
    mode: str = "full",
    run_id: str = "",
    project_id: str = "",
    target_base_url: str = "",
    api_spec: dict[str, Any] | None = None,
    cases: list[dict[str, Any]] | None = None,
) -> TestForgeState:
    """构造一份干净的初始状态。"""
    state: TestForgeState = {
        "mode": mode,
        "run_id": run_id,
        "project_id": project_id,
        "target_base_url": target_base_url,
        "api_spec": api_spec or {},
        "cases": cases or [],
        "errors": [],
        "token_usage": {},
    }
    return state


def is_failed_result(result: dict[str, Any]) -> bool:
    return result.get("status") in {"failed", "error"}


def summarize(state: TestForgeState) -> dict[str, Any]:
    """给接口层用的轻量摘要，避免把全量状态直接吐给前端。"""
    results = state.get("results") or []
    failed = [r for r in results if is_failed_result(r)]
    return {
        "mode": state.get("mode"),
        "run_id": state.get("run_id"),
        "cases": len(state.get("cases") or []),
        "results": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "defects": len(state.get("defects") or []),
        "errors": state.get("errors") or [],
        "token_usage": state.get("token_usage") or {},
        "report": state.get("report") or {},
    }
