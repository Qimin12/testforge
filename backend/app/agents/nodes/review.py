"""Review 节点（TG-04 / §12 人工审核）：用例生成后暂停，等人确认再执行。

这是整张图里唯一使用 ``interrupt()`` 的地方：
* ``REQUIRE_REVIEW=0``（开发默认）→ 直接放行，链路全自动；
* ``REQUIRE_REVIEW=1`` → 图在此挂起，状态落检查点，前端拿到待审用例，
  确认后调用 ``Command(resume=决策)`` 从断点继续，**不会重跑前面已完成的节点**。
"""

from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


async def review(
    state: dict[str, Any], config: RunnableConfig | None = None
) -> dict[str, Any]:
    cases = state.get("cases") or []

    if not settings.require_review:
        return {"review": {"approved": True, "skipped": True, "count": len(cases)}}

    if not cases:
        return {"review": {"approved": True, "skipped": False, "count": 0}}

    # 挂起：把待审用例交给调用方。恢复时 interrupt() 的返回值就是 Command(resume=...)
    decision = interrupt(
        {
            "action": "review_test_cases",
            "message": "请审核 AI 生成的测试用例，确认后继续执行",
            "count": len(cases),
            "cases": cases,
        }
    )

    decision = decision or {}
    approved = bool(decision.get("approved", False))
    edited = decision.get("cases")

    logger.info("review.decision", approved=approved, count=len(cases))

    if not approved:
        return {
            "review": {"approved": False, "count": len(cases), "reason": decision.get("reason", "")},
            "cases": [],
            "errors": ["用例审核未通过，已跳过执行"],
        }

    if isinstance(edited, list) and edited:
        return {
            "review": {"approved": True, "count": len(edited), "edited": True},
            "cases": edited,
        }

    return {"review": {"approved": True, "count": len(cases), "edited": False}}
