"""项目接口：CRUD、OpenAPI 导入、用例管理、发起执行、覆盖率（PM-01~PM-05 / TG-05 / RP-02）。"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.api.serializers import case_out, execution_detail, project_out
from app.core.logging import get_logger
from app.db.models import Project, User
from app.schemas.case import CaseBulkCreate, CasePage
from app.schemas.coverage import CoverageIn, CoverageOut
from app.schemas.execution import ExecutionDetail, RunProjectRequest
from app.schemas.project import (
    OpenAPIImportRequest,
    OpenAPIImportResult,
    OpenAPIOperation,
    ProjectCreate,
    ProjectOut,
    ProjectPage,
    ProjectUpdate,
)
from app.services import (
    case_service,
    coverage_service,
    execution_service,
    project_service,
)
from app.services.execution_runner import ExecutionError, run_or_enqueue

logger = get_logger(__name__)

router = APIRouter(prefix="/projects", tags=["项目管理"])


async def _owned_project(db: AsyncSession, project_id: UUID, user: User) -> Project:
    project = await project_service.get_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    if project.user_id != user.id:
        # 不暴露「存在但不属于你」，统一按 404 处理
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    return project


# --------------------------------------------------------------------------- #
# PM-01 / PM-04 创建、列表
# --------------------------------------------------------------------------- #
@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreate, user: CurrentUser, db: DbSession) -> ProjectOut:
    project = await project_service.create_project(
        db,
        user_id=user.id,
        name=payload.name,
        description=payload.description,
        repo_url=payload.repo_url,
        target_base_url=payload.target_base_url,
    )
    return project_out(project)


@router.get("", response_model=ProjectPage)
async def list_projects(
    user: CurrentUser,
    db: DbSession,
    status_filter: str | None = Query(default=None, alias="status"),
    keyword: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ProjectPage:
    rows, total = await project_service.list_projects(
        db, user_id=user.id, status=status_filter, keyword=keyword, limit=limit, offset=offset
    )
    items = []
    for project in rows:
        case_count = await case_service.count_by_project(db, project.id)
        operation_count = len((project.api_spec or {}).get("paths") or {})
        items.append(project_out(project, case_count=case_count, operation_count=operation_count))
    return ProjectPage(items=items, total=total)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: UUID, user: CurrentUser, db: DbSession) -> ProjectOut:
    project = await _owned_project(db, project_id, user)
    case_count = await case_service.count_by_project(db, project.id)
    operation_count = len((project.api_spec or {}).get("paths") or {})
    return project_out(project, case_count=case_count, operation_count=operation_count)


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: UUID, payload: ProjectUpdate, user: CurrentUser, db: DbSession
) -> ProjectOut:
    project = await _owned_project(db, project_id, user)
    data = payload.model_dump(exclude_unset=True)
    status_value = data.pop("status", None)
    project = await project_service.update_project(db, project, data)
    if status_value:
        project.status = status_value
        await db.flush()
    return project_out(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_project(project_id: UUID, user: CurrentUser, db: DbSession) -> None:
    """PM-06 的轻量实现：归档而不是物理删除，避免误删测试历史。"""
    project = await _owned_project(db, project_id, user)
    project.status = "archived"
    await db.flush()


# --------------------------------------------------------------------------- #
# PM-03 OpenAPI 导入
# --------------------------------------------------------------------------- #
@router.post("/{project_id}/openapi", response_model=OpenAPIImportResult)
async def import_openapi(
    project_id: UUID, payload: OpenAPIImportRequest, user: CurrentUser, db: DbSession
) -> OpenAPIImportResult:
    project = await _owned_project(db, project_id, user)

    try:
        parsed = project_service.parse_openapi(payload.spec)
    except project_service.OpenAPIError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    project.api_spec = parsed["spec"]
    config = dict(project.target_config or {})
    if parsed["base_url"] and not config.get("base_url"):
        config["base_url"] = parsed["base_url"]
    project.target_config = config or None
    await db.flush()

    logger.info("openapi.imported", project_id=str(project.id), operations=parsed["operation_count"])
    return OpenAPIImportResult(
        project_id=project.id,
        operation_count=parsed["operation_count"],
        base_url=parsed["base_url"],
        operations=[OpenAPIOperation(**op) for op in parsed["operations"]],
    )


# --------------------------------------------------------------------------- #
# 用例管理（TG-05）
# --------------------------------------------------------------------------- #
@router.get("/{project_id}/cases", response_model=CasePage)
async def list_cases(
    project_id: UUID,
    user: CurrentUser,
    db: DbSession,
    case_type: str | None = Query(default=None, alias="type"),
    keyword: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> CasePage:
    await _owned_project(db, project_id, user)
    rows, total = await case_service.list_cases(
        db,
        project_id=project_id,
        case_type=case_type,
        keyword=keyword,
        limit=limit,
        offset=offset,
    )
    return CasePage(items=[case_out(row) for row in rows], total=total)


@router.post("/{project_id}/cases", response_model=CasePage, status_code=status.HTTP_201_CREATED)
async def bulk_create_cases(
    project_id: UUID, payload: CaseBulkCreate, user: CurrentUser, db: DbSession
) -> CasePage:
    await _owned_project(db, project_id, user)
    payloads = [
        {
            "name": item.name,
            "method": item.method,
            "path": item.path,
            "headers": item.headers,
            "params": item.params,
            "body": item.body,
            "expected_status": item.expected_status,
            "assertions": [a.model_dump() for a in item.assertions],
            "category": item.category,
            "rationale": item.rationale,
        }
        for item in payload.cases
    ]
    created = await case_service.bulk_create(
        db, project_id=project_id, cases=payloads, source=payload.source
    )
    return CasePage(items=[case_out(row) for row in created], total=len(created))


# --------------------------------------------------------------------------- #
# 发起执行（M1.4 的入口：项目 → 图 → 落库）
# --------------------------------------------------------------------------- #
@router.post("/{project_id}/run", response_model=ExecutionDetail)
async def run_project(
    project_id: UUID, payload: RunProjectRequest, user: CurrentUser, db: DbSession
) -> ExecutionDetail:
    project = await _owned_project(db, project_id, user)

    try:
        execution, state_kind = await run_or_enqueue(
            db,
            project,
            mode=payload.mode,
            trigger_type=payload.trigger_type,
            async_mode=payload.async_mode,
        )
    except ExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message
        ) from exc
    except Exception as exc:  # 图内部异常
        logger.exception("project.run.failed", project_id=str(project.id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"执行失败: {exc}"
        ) from exc

    detail = await execution_service.get_execution_detail(db, execution.id)
    if detail is None:  # pragma: no cover
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="执行记录丢失")

    if state_kind == "queued":
        logger.info("project.run.queued", project_id=str(project.id), execution_id=str(execution.id))

    return execution_detail(detail)


# --------------------------------------------------------------------------- #
# 覆盖率上报（RP-02）
# --------------------------------------------------------------------------- #
@router.post(
    "/{project_id}/coverage", response_model=CoverageOut, status_code=status.HTTP_201_CREATED
)
async def upload_coverage(
    project_id: UUID, payload: CoverageIn, user: CurrentUser, db: DbSession
) -> CoverageOut:
    await _owned_project(db, project_id, user)

    report = await coverage_service.create_report(
        db,
        project_id=project_id,
        payload=payload.model_dump(),
        execution_id=payload.execution_id,
        source=payload.source,
    )
    return CoverageOut.model_validate(report)


@router.get("/{project_id}/coverage", response_model=list[CoverageOut])
async def list_coverage(
    project_id: UUID,
    user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[CoverageOut]:
    await _owned_project(db, project_id, user)
    rows, _ = await coverage_service.list_reports(db, project_id, limit=limit)
    return [CoverageOut.model_validate(row) for row in rows]


@router.get("/{project_id}/coverage/latest", response_model=CoverageOut | None)
async def latest_coverage(
    project_id: UUID, user: CurrentUser, db: DbSession
) -> CoverageOut | None:
    await _owned_project(db, project_id, user)
    row = await coverage_service.latest(db, project_id)
    return CoverageOut.model_validate(row) if row is not None else None
