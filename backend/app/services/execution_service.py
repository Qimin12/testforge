"""执行记录服务：创建执行、把图结果落库、查询执行详情。

这是补齐「图跑完什么都不剩」这个缺口的核心模块。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.db.models import Defect, Execution, ExecutionStatus, Project, ResultStatus, TestResult

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# 创建
# --------------------------------------------------------------------------- #
async def create_execution(
    db: AsyncSession,
    *,
    project_id: UUID | str,
    trigger_type: str = "manual",
    mode: str = "full",
    thread_id: str | None = None,
) -> Execution:
    execution = Execution(
        project_id=_as_uuid(project_id),
        trigger_type=trigger_type,
        status=ExecutionStatus.RUNNING.value,
        graph_thread_id=thread_id,
        graph_mode=mode,
        started_at=datetime.now(UTC),
    )
    db.add(execution)
    await db.flush()
    logger.info("execution.created", execution_id=str(execution.id), mode=mode)
    return execution


# --------------------------------------------------------------------------- #
# 落库
# --------------------------------------------------------------------------- #
async def persist_state(db: AsyncSession, execution: Execution, state: dict[str, Any]) -> Execution:
    """把 LangGraph 的最终状态写进 executions / test_results / defects。"""
    results: list[dict[str, Any]] = state.get("results") or []
    defects: list[dict[str, Any]] = state.get("defects") or []
    interrupted = bool(state.get("__interrupt__"))

    for item in results:
        db.add(
            TestResult(
                execution_id=execution.id,
                case_id=_as_uuid(item.get("case_id")),
                case_name=(item.get("case_name") or "未命名用例")[:200],
                status=item.get("status") or ResultStatus.ERROR.value,
                expected_output=_clip(item.get("expected")),
                actual_output=_clip(item.get("actual")),
                error_message=_clip(item.get("error")),
                duration_ms=_as_int(item.get("duration_ms")),
            )
        )

    for item in defects:
        db.add(
            Defect(
                execution_id=execution.id,
                case_id=_as_uuid(item.get("case_id")),
                title=(item.get("title") or "未命名缺陷")[:200],
                description=item.get("description") or "",
                severity=item.get("severity") or "major",
                category=item.get("category") or "unknown",
                root_cause=item.get("root_cause"),
                fix_suggestion=item.get("fix_suggestion"),
                fingerprint=item.get("fingerprint"),
            )
        )

    total = len(results)
    failed = sum(
        1 for r in results if r.get("status") in {ResultStatus.FAILED.value, ResultStatus.ERROR.value}
    )
    execution.total_cases = total
    execution.passed_cases = total - failed
    execution.failed_cases = failed
    execution.report = state.get("report")
    execution.token_usage = state.get("token_usage") or None
    execution.finished_at = datetime.now(UTC)

    if execution.started_at is not None:
        started = execution.started_at
        if started.tzinfo is None:  # SQLite 读出来是 naive
            started = started.replace(tzinfo=UTC)
        execution.duration_ms = int((execution.finished_at - started).total_seconds() * 1000)

    if interrupted:
        execution.status = ExecutionStatus.INTERRUPTED.value
    elif failed == 0 and total > 0:
        execution.status = ExecutionStatus.SUCCESS.value
    elif total == 0:
        execution.status = ExecutionStatus.FAILED.value
    else:
        execution.status = ExecutionStatus.FAILED.value

    await db.flush()
    logger.info(
        "execution.persisted",
        execution_id=str(execution.id),
        total=total,
        failed=failed,
        defects=len(defects),
        status=execution.status,
    )
    return execution


async def mark_failed(db: AsyncSession, execution: Execution, error: str) -> Execution:
    """图抛异常时的收尾：状态置失败并记录原因。"""
    execution.status = ExecutionStatus.FAILED.value
    execution.finished_at = datetime.now(UTC)
    execution.report = {"error": error[:2000]}
    await db.flush()
    return execution


# --------------------------------------------------------------------------- #
# 查询
# --------------------------------------------------------------------------- #
async def get_execution(db: AsyncSession, execution_id: UUID | str) -> Execution | None:
    return await db.get(Execution, _as_uuid(execution_id))


async def get_execution_detail(db: AsyncSession, execution_id: UUID | str) -> Execution | None:
    """带 results / defects 一起返回，供详情页使用。"""
    stmt = (
        select(Execution)
        .where(Execution.id == _as_uuid(execution_id))
        .options(selectinload(Execution.results), selectinload(Execution.defects))
    )
    return await db.scalar(stmt)


async def list_executions(
    db: AsyncSession,
    *,
    project_id: UUID | str | None = None,
    user_id: UUID | None = None,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Execution], int]:
    conditions = []
    if project_id:
        conditions.append(Execution.project_id == _as_uuid(project_id))
    if user_id is not None:
        conditions.append(
            Execution.project_id.in_(select(Project.id).where(Project.user_id == user_id))
        )
    if status:
        conditions.append(Execution.status == status)

    total = await db.scalar(select(func.count()).select_from(Execution).where(*conditions))
    stmt = (
        select(Execution)
        .where(*conditions)
        .order_by(Execution.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = list(await db.scalars(stmt))
    return rows, int(total or 0)


async def list_defects(
    db: AsyncSession,
    *,
    execution_id: UUID | str | None = None,
    project_id: UUID | str | None = None,
    user_id: UUID | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Defect], int]:
    conditions = []
    if execution_id:
        conditions.append(Defect.execution_id == _as_uuid(execution_id))
    if project_id:
        conditions.append(
            Defect.execution_id.in_(
                select(Execution.id).where(Execution.project_id == _as_uuid(project_id))
            )
        )
    if user_id is not None:
        conditions.append(
            Defect.execution_id.in_(
                select(Execution.id).where(
                    Execution.project_id.in_(select(Project.id).where(Project.user_id == user_id))
                )
            )
        )
    if status:
        conditions.append(Defect.status == status)

    total = await db.scalar(select(func.count()).select_from(Defect).where(*conditions))
    stmt = (
        select(Defect)
        .where(*conditions)
        .order_by(Defect.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = list(await db.scalars(stmt))
    return rows, int(total or 0)


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #
def _as_uuid(value: Any) -> UUID | None:
    if value is None or value == "":
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, AttributeError):
        return None


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clip(value: Any, limit: int = 4000) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text[:limit]
