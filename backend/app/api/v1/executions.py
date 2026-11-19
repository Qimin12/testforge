"""执行记录 / 缺陷查询接口（TE / DA / RP 的读侧）。"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status
from langgraph.types import Command

from app.agents.graph import get_graph, thread_config
from app.api.deps import CurrentUser, DbSession
from app.api.serializers import defect_out, execution_detail, execution_out
from app.core.logging import get_logger
from app.db.models import Defect, Execution, Project, User
from app.schemas.execution import (
    DefectPage,
    ExecutionDetail,
    ExecutionPage,
)
from app.schemas.graph import ReviewDecision
from app.services import execution_service, report_service

logger = get_logger(__name__)

router = APIRouter(tags=["执行与缺陷"])


async def _owned_execution(db: DbSession, execution_id: UUID, user: User) -> Execution:
    execution = await execution_service.get_execution(db, execution_id)
    if execution is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="执行记录不存在")
    project = await db.get(Project, execution.project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="执行记录不存在")
    return execution


# --------------------------------------------------------------------------- #
# 执行记录
# --------------------------------------------------------------------------- #
@router.get("/executions", response_model=ExecutionPage)
async def list_executions(
    user: CurrentUser,
    db: DbSession,
    project_id: UUID | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ExecutionPage:
    rows, total = await execution_service.list_executions(
        db,
        project_id=project_id,
        user_id=user.id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return ExecutionPage(items=[execution_out(row) for row in rows], total=total)


@router.get("/executions/{execution_id}", response_model=ExecutionDetail)
async def get_execution(execution_id: UUID, user: CurrentUser, db: DbSession) -> ExecutionDetail:
    await _owned_execution(db, execution_id, user)
    detail = await execution_service.get_execution_detail(db, execution_id)
    if detail is None:  # pragma: no cover
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="执行记录不存在")
    return execution_detail(detail)


@router.get("/executions/{execution_id}/report")
async def get_report(execution_id: UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """RP-01：报告就是 executions.report 这一列。"""
    execution = await _owned_execution(db, execution_id, user)
    return {
        "execution_id": str(execution.id),
        "status": execution.status,
        "total_cases": execution.total_cases,
        "passed_cases": execution.passed_cases,
        "failed_cases": execution.failed_cases,
        "duration_ms": execution.duration_ms,
        "report": execution.report,
        "token_usage": execution.token_usage,
    }


@router.get("/executions/{execution_id}/export")
async def export_execution(
    execution_id: UUID,
    user: CurrentUser,
    db: DbSession,
    fmt: str = Query(default="json", alias="format", pattern="^(json|markdown|csv|xlsx)$"),
) -> Response:
    """RP-05：导出报告。支持 json / markdown / csv / xlsx（PDF 暂不做）。"""
    await _owned_execution(db, execution_id, user)
    detail = await execution_service.get_execution_detail(db, execution_id)
    if detail is None:  # pragma: no cover
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="执行记录不存在")

    try:
        content, media_type, filename = report_service.render(detail, fmt)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/executions/{execution_id}/resume", response_model=ExecutionDetail)
async def resume_execution(
    execution_id: UUID, decision: ReviewDecision, user: CurrentUser, db: DbSession
) -> ExecutionDetail:
    """TG-04：项目级执行被审核中断后，用这个接口恢复并回写结果。"""
    execution = await _owned_execution(db, execution_id, user)
    if not execution.graph_thread_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="该执行没有可恢复的图状态"
        )

    graph = await get_graph()
    try:
        result = await graph.ainvoke(
            Command(resume=decision.model_dump()), thread_config(execution.graph_thread_id)
        )
    except Exception as exc:
        logger.exception("execution.resume.failed", execution_id=str(execution_id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"恢复失败: {exc}"
        ) from exc

    # 只追加新的结果行：先清掉上次落库的结果，避免重复
    await execution_service.persist_state(db, execution, result)

    detail = await execution_service.get_execution_detail(db, execution.id)
    if detail is None:  # pragma: no cover
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="执行记录丢失")
    return execution_detail(detail)


# --------------------------------------------------------------------------- #
# 缺陷
# --------------------------------------------------------------------------- #
@router.get("/defects", response_model=DefectPage)
async def list_defects(
    user: CurrentUser,
    db: DbSession,
    project_id: UUID | None = None,
    execution_id: UUID | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> DefectPage:
    if execution_id is not None:
        await _owned_execution(db, execution_id, user)
    rows, total = await execution_service.list_defects(
        db,
        execution_id=execution_id,
        project_id=project_id,
        user_id=None if execution_id else user.id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return DefectPage(items=[defect_out(row) for row in rows], total=total)


@router.patch("/defects/{defect_id}", response_model=DefectPage)
async def update_defect_status(
    defect_id: UUID,
    new_status: Literal["open", "fixed", "closed", "wontfix"],
    user: CurrentUser,
    db: DbSession,
) -> DefectPage:
    """改缺陷状态（open → fixed / closed / wontfix）。"""
    defect = await db.get(Defect, defect_id)
    if defect is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="缺陷不存在")
    await _owned_execution(db, defect.execution_id, user)
    defect.status = new_status
    await db.flush()
    return DefectPage(items=[defect_out(defect)], total=1)
