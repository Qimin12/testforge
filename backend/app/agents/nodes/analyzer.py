"""Analyzer 节点（DA-01 / DA-02 / DA-03）：分析失败原因、定位根因、给修复建议。

只分析失败的用例——全部通过时不浪费 token。
"""

from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agents.llm import is_mock_mode, structured_invoke
from app.agents.prompts import ANALYZER_SYSTEM, build_analyzer_prompt
from app.agents.schemas import AnalysisOutput, FailureAnalysis
from app.agents.state import is_failed_result
from app.core.logging import get_logger

logger = get_logger(__name__)


async def analyzer(
    state: dict[str, Any], config: RunnableConfig | None = None
) -> dict[str, Any]:
    results = state.get("results") or []
    failed = [r for r in results if is_failed_result(r)]

    if not failed:
        return {"analysis": {"items": [], "overall": "本次执行无失败用例"}}

    try:
        usage: dict[str, int] = {}
        if is_mock_mode():
            output = _mock_analysis(failed)
        else:
            output, usage = await structured_invoke(
                AnalysisOutput,
                [("system", ANALYZER_SYSTEM), ("human", build_analyzer_prompt(failed))],
                tier="large",
                scope="analyzer",
            )
    except Exception as exc:
        logger.warning("analyzer.failed", error=str(exc))
        # 分析失败不能让执行结果丢失，退化成启发式结论
        return {
            "analysis": _mock_analysis(failed).model_dump(),
            "errors": [f"AI 分析失败，已退化为启发式判断: {exc}"],
        }

    return {"analysis": output.model_dump(), "token_usage": usage}


def _mock_analysis(failed: list[dict[str, Any]]) -> AnalysisOutput:
    items = [_heuristic(result) for result in failed]
    return AnalysisOutput(items=items, overall=f"共 {len(items)} 条用例失败，以下为逐条判断")


def _heuristic(result: dict[str, Any]) -> FailureAnalysis:
    """无模型时的确定性判定，同时也给了真实模型一个对照基线。"""
    name = result.get("case_name") or "未命名用例"
    error = str(result.get("error") or "")
    actual = str(result.get("actual") or "")
    expected = str(result.get("expected") or "")

    reason: str
    root_cause: str
    fix: str
    severity = "major"
    confidence = 0.55

    lowered = error.lower()
    if result.get("status") == "error" or "timeout" in lowered or "connect" in lowered:
        reason = f"请求未能完成：{error[:200]}"
        root_cause = "被测服务不可达或超时（service_error）"
        fix = "确认被测服务已启动、地址与端口正确；必要时放宽超时或加重试"
        severity = "blocker"
        confidence = 0.8
    elif "http 5" in actual.lower():
        reason = f"服务端返回 {actual}"
        root_cause = "被测服务内部错误（service_error）"
        fix = "取服务端日志定位异常栈；该用例应暂时标记为环境/服务问题"
        severity = "critical"
        confidence = 0.75
    elif "http 4" in actual.lower() and "http 2" in expected.lower():
        reason = f"期望 2xx，实际 {actual}"
        root_cause = "请求构造可能不合法（request_error），需核对参数与鉴权"
        fix = "检查路径参数、必填字段、鉴权头是否与接口文档一致"
        confidence = 0.6
    else:
        reason = f"期望 {expected}，实际 {actual}"
        root_cause = "断言与响应不一致（assertion_error）"
        fix = "核对断言的目标字段与值；若接口行为已变更，更新期望值"
        confidence = 0.5

    return FailureAnalysis(
        case_name=name,
        failure_reason=reason,
        root_cause=root_cause,
        fix_suggestion=fix,
        severity=severity,  # type: ignore[arg-type]
        confidence=confidence,
    )
