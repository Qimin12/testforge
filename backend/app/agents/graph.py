"""Manager 主图（PRD §5.2）。

拓扑：

    START ─┬─(full/generate)─▶ case_gen ─▶ review ⏸ ─▶ executor ─┐
           ├─(execute_only)──────────────────────────▶ executor ─┤
           ├─(analyze_only)─▶ analyzer ─▶ defect ─▶ report ─▶ END │
           └─(report_only)──────────────────────────▶ report ─▶ END
                                                              执行后
    executor ─(有失败)─▶ analyzer ─▶ defect_classifier ─▶ report ─▶ END
    executor ─(全通过)──────────────────────────────────▶ report ─▶ END
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.checkpointer import get_saver
from app.agents.nodes import (
    analyzer,
    case_gen,
    defect_classifier,
    executor,
    report_generator,
    review,
)
from app.agents.state import TestForgeState, is_failed_result
from app.core.logging import get_logger

logger = get_logger(__name__)

# 节点名常量，避免各处写字符串写错
NODE_CASE_GEN = "case_gen"
NODE_REVIEW = "review"
NODE_EXECUTOR = "executor"
NODE_ANALYZER = "analyzer"
NODE_DEFECT = "defect_classifier"
NODE_REPORT = "report"


def route_entry(state: TestForgeState) -> str:
    """根据运行模式决定从哪个节点开始。"""
    mode = state.get("mode") or "full"
    if mode == "execute_only":
        return NODE_EXECUTOR
    if mode == "analyze_only":
        return NODE_ANALYZER
    if mode == "report_only":
        return NODE_REPORT
    return NODE_CASE_GEN  # full / generate


def after_execute(state: TestForgeState) -> str:
    """执行完：有失败才去分析，全通过直接出报告（省 token）。"""
    results = state.get("results") or []
    return NODE_ANALYZER if any(is_failed_result(r) for r in results) else NODE_REPORT


def build_graph(checkpointer: BaseCheckpointSaver | None = None) -> CompiledStateGraph:
    """构造并编译主图。传入 checkpointer 才能支持中断恢复。"""
    graph: StateGraph = StateGraph(TestForgeState)

    graph.add_node(NODE_CASE_GEN, case_gen)
    graph.add_node(NODE_REVIEW, review)
    graph.add_node(NODE_EXECUTOR, executor)
    graph.add_node(NODE_ANALYZER, analyzer)
    graph.add_node(NODE_DEFECT, defect_classifier)
    graph.add_node(NODE_REPORT, report_generator)

    graph.add_conditional_edges(
        START,
        route_entry,
        {
            NODE_CASE_GEN: NODE_CASE_GEN,
            NODE_EXECUTOR: NODE_EXECUTOR,
            NODE_ANALYZER: NODE_ANALYZER,
            NODE_REPORT: NODE_REPORT,
        },
    )
    graph.add_edge(NODE_CASE_GEN, NODE_REVIEW)
    graph.add_edge(NODE_REVIEW, NODE_EXECUTOR)
    graph.add_conditional_edges(
        NODE_EXECUTOR,
        after_execute,
        {NODE_ANALYZER: NODE_ANALYZER, NODE_REPORT: NODE_REPORT},
    )
    graph.add_edge(NODE_ANALYZER, NODE_DEFECT)
    graph.add_edge(NODE_DEFECT, NODE_REPORT)
    graph.add_edge(NODE_REPORT, END)

    return graph.compile(checkpointer=checkpointer)


_compiled: CompiledStateGraph | None = None


async def get_graph() -> CompiledStateGraph:
    """进程内单例编译结果（绑定单例 checkpointer，中断状态才不会丢）。"""
    global _compiled
    if _compiled is None:
        saver = await get_saver()
        _compiled = build_graph(saver)
        logger.info("graph.compiled")
    return _compiled


def reset_graph() -> None:
    global _compiled
    _compiled = None


def thread_config(thread_id: str) -> dict[str, Any]:
    """LangGraph 的运行配置：thread_id 决定检查点归属。"""
    return {"configurable": {"thread_id": thread_id}}


def extract_interrupt(result: dict[str, Any]) -> dict[str, Any] | None:
    """从 ainvoke 的返回里取出中断负载（有则说明图挂起了）。"""
    raw = result.get("__interrupt__")
    if not raw:
        return None
    first = raw[0] if isinstance(raw, (list, tuple)) and raw else raw
    value = getattr(first, "value", first)
    return value if isinstance(value, dict) else {"value": value}
