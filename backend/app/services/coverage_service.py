"""覆盖率上报与查询（PRD RP-02）。

平台不执行覆盖率采集，只接收项目测试跑出来的结果。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import CoverageReport

logger = get_logger(__name__)


def compute_rates(data: dict[str, Any]) -> tuple[float, float]:
    """从 total/covered 推导百分比；允许直接传 line_rate/branch_rate。"""
    line_rate = data.get("line_rate")
    branch_rate = data.get("branch_rate")

    total_lines = int(data.get("total_lines") or 0)
    covered_lines = int(data.get("covered_lines") or 0)
    total_branches = int(data.get("total_branches") or 0)
    covered_branches = int(data.get("covered_branches") or 0)

    if line_rate is None:
        line_rate = covered_lines / total_lines * 100 if total_lines else 0.0
    if branch_rate is None:
        branch_rate = covered_branches / total_branches * 100 if total_branches else 0.0

    return round(float(line_rate), 2), round(float(branch_rate), 2)


async def create_report(
    db: AsyncSession,
    *,
    project_id: UUID,
    payload: dict[str, Any],
    execution_id: UUID | None = None,
    source: str = "pytest-cov",
) -> CoverageReport:
    line_rate, branch_rate = compute_rates(payload)

    report = CoverageReport(
        project_id=project_id,
        execution_id=execution_id,
        line_rate=line_rate,
        branch_rate=branch_rate,
        total_lines=int(payload.get("total_lines") or 0),
        covered_lines=int(payload.get("covered_lines") or 0),
        total_branches=int(payload.get("total_branches") or 0),
        covered_branches=int(payload.get("covered_branches") or 0),
        source=source,
        raw=payload.get("raw"),
    )
    db.add(report)
    await db.flush()
    logger.info("coverage.created", project_id=str(project_id), line_rate=line_rate)
    return report


async def list_reports(
    db: AsyncSession, project_id: UUID, *, limit: int = 20
) -> tuple[list[CoverageReport], int]:
    total = await db.scalar(
        select(func.count()).select_from(CoverageReport).where(CoverageReport.project_id == project_id)
    )
    stmt = (
        select(CoverageReport)
        .where(CoverageReport.project_id == project_id)
        .order_by(CoverageReport.created_at.desc())
        .limit(limit)
    )
    return list(await db.scalars(stmt)), int(total or 0)


async def latest(db: AsyncSession, project_id: UUID) -> CoverageReport | None:
    stmt = (
        select(CoverageReport)
        .where(CoverageReport.project_id == project_id)
        .order_by(CoverageReport.created_at.desc())
        .limit(1)
    )
    return await db.scalar(stmt)
