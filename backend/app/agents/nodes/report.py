"""Report Generator 节点（RP-01 / RP-03）：汇总统计 + 生成结论。

统计部分永远由代码算（可信），只有「结论文字」交给模型（会惜字如金）。
"""

from datetime import UTC, datetime
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agents.llm import is_mock_mode, structured_invoke
from app.agents.prompts import REPORT_SYSTEM, build_report_prompt
from app.agents.schemas import ReportOutput
from app.agents.state import is_failed_result
from app.core.logging import get_logger

logger = get_logger(__name__)


async def report_generator(
    state: dict[str, Any], config: RunnableConfig | None = None
) -> dict[str, Any]:
    results = state.get("results") or []
    defects = state.get("defects") or []
    stats = build_stats(results, defects)

    if not results:
        report = {
            **stats,
            "summary": "本次未执行任何用例。",
            "risk_level": "medium",
            "highlights": ["没有执行结果，无法评估质量"],
            "generated_at": _now(),
        }
        return {"report": report}

    try:
        usage: dict[str, int] = {}
        if is_mock_mode():
            output = _mock_report(stats)
        else:
            output, usage = await structured_invoke(
                ReportOutput,
                [("system", REPORT_SYSTEM), ("human", build_report_prompt(stats, defects))],
                tier="small",
                scope="report",
            )
    except Exception as exc:
        logger.warning("report.failed", error=str(exc))
        output = _mock_report(stats)
        return {
            "report": {**stats, **output.model_dump(), "generated_at": _now()},
            "errors": [f"报告生成失败，已退化为统计结论: {exc}"],
        }

    return {"report": {**stats, **output.model_dump(), "generated_at": _now()}, "token_usage": usage}


def build_stats(results: list[dict[str, Any]], defects: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    failed = sum(1 for r in results if is_failed_result(r))
    passed = total - failed
    durations = [int(r.get("duration_ms") or 0) for r in results]

    by_severity: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for d in defects:
        by_severity[d.get("severity", "major")] = by_severity.get(d.get("severity", "major"), 0) + 1
        by_category[d.get("category", "unknown")] = (
            by_category.get(d.get("category", "unknown"), 0) + 1
        )

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / total * 100, 2) if total else 0.0,
        "total_duration_ms": sum(durations),
        "avg_duration_ms": int(sum(durations) / total) if total else 0,
        "defect_count": len(defects),
        "defects_by_severity": by_severity,
        "defects_by_category": by_category,
    }


def _mock_report(stats: dict[str, Any]) -> ReportOutput:
    total = stats["total"]
    failed = stats["failed"]
    rate = stats["pass_rate"]

    if failed == 0:
        summary = f"共执行 {total} 条用例，全部通过，通过率 {rate}%。未发现缺陷。"
        risk = "low"
        highlights = ["全部用例通过，可继续后续流程"]
    else:
        summary = f"共执行 {total} 条用例，{failed} 条失败，通过率 {rate}%。已生成对应缺陷条目。"
        risk = "high" if rate < 80 else "medium"
        highlights = [f"{failed} 条用例失败，需确认是用例问题还是服务缺陷"]

    return ReportOutput(summary=summary, risk_level=risk, highlights=highlights)  # type: ignore[arg-type]


def _now() -> str:
    return datetime.now(UTC).isoformat()
