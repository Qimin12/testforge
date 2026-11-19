"""Token 用量与预算（PRD CO-01 / CO-04）。

每次执行已经把按节点的 token 用量写进 ``executions.token_usage``，
这里按月汇总，和 ``TOKEN_BUDGET_MONTHLY`` 比对给出告警。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Execution, Project


def month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # SQLite 存的 datetime 是 naive，用 aware 去比较会拿不到数据
    return start.replace(tzinfo=None) if settings.is_sqlite else start


async def monthly_usage(db: AsyncSession, user_id: UUID) -> dict:
    stmt = (
        select(Execution.token_usage, Execution.created_at)
        .join(Project, Project.id == Execution.project_id)
        .where(Project.user_id == user_id, Execution.created_at >= month_start())
    )
    rows = list(await db.execute(stmt))

    by_node: dict[str, int] = {}
    total = 0
    for token_usage, _created in rows:
        for key, value in (token_usage or {}).items():
            if not isinstance(value, int):
                continue
            by_node[key] = by_node.get(key, 0) + value
            if key.endswith("total_tokens"):
                total += value

    budget = max(0, settings.token_budget_monthly)
    ratio = round(total / budget * 100, 2) if budget else 0.0

    return {
        "period": month_start().strftime("%Y-%m"),
        "total_tokens": total,
        "by_node": by_node,
        "budget": budget,
        "used_ratio": ratio,
        "over_budget": bool(budget and total > budget),
        "warning": _warning(total, budget),
        "executions": len(rows),
    }


def _warning(total: int, budget: int) -> str | None:
    if not budget:
        return None
    if total > budget:
        return f"本月 token 已超出预算（{total}/{budget}）"
    if total > budget * 0.8:
        return f"本月 token 已使用 {total}/{budget}，接近预算上限"
    return None
