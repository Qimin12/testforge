"""CI/CD 接口（PRD CD-01 ~ CD-05）。

给流水线用的最薄一层：
* ``GET /ci/projects``   用 API Key 列出可见项目，拿到 project_id
* ``POST /ci/run``       跑一次并返回质量门禁结论
* ``POST /ci/coverage``  顺手把覆盖率一起传上来（可选）

鉴权走 ``X-API-Key``，所以这三个接口不需要 JWT——CI 里不该存用户密码。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import CurrentUser, DbSession
from app.core.logging import get_logger
from app.schemas.ci import CIGate, CIProjectOut, CIRunRequest, CIRunResponse
from app.schemas.coverage import CoverageIn, CoverageOut
from app.services import coverage_service, execution_service, project_service
from app.services.execution_runner import ExecutionError, run_or_enqueue

logger = get_logger(__name__)

router = APIRouter(prefix="/ci", tags=["CI/CD"])


def _header_value(passed: bool) -> str:
    return "pass" if passed else "fail"


@router.get("/projects", response_model=list[CIProjectOut])
async def list_ci_projects(user: CurrentUser, db: DbSession) -> list[CIProjectOut]:
    rows, _ = await project_service.list_projects(db, user_id=user.id, limit=100)
    out: list[CIProjectOut] = []
    for project in rows:
        config: dict[str, Any] = project.target_config or {}
        out.append(
            CIProjectOut(
                id=project.id,
                name=project.name,
                operation_count=len((project.api_spec or {}).get("paths") or {}),
                target_base_url=config.get("base_url"),
            )
        )
    return out


@router.post("/run", response_model=CIRunResponse)
async def ci_run(
    payload: CIRunRequest, user: CurrentUser, db: DbSession, response: Response
) -> CIRunResponse:
    project = await project_service.get_project(db, payload.project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    try:
        execution, kind = await run_or_enqueue(
            db,
            project,
            mode=payload.mode,
            trigger_type="api",
            async_mode=payload.async_mode,
        )
    except ExecutionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    except Exception as exc:
        logger.exception("ci.run.failed", project_id=str(payload.project_id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"执行失败: {exc}"
        ) from exc

    detail = await execution_service.get_execution_detail(db, execution.id)
    defects = list(detail.defects) if detail else []
    total = execution.total_cases or 0
    passed = execution.passed_cases or 0
    failed = execution.failed_cases or 0
    pass_rate = round(passed / total * 100, 2) if total else 0.0

    reasons: list[str] = []
    if kind == "queued":
        reasons.append("执行已排队，尚未完成；CI 中请使用同步模式（async_mode=false）")
        gate = CIGate(
            passed=False,
            min_pass_rate=payload.min_pass_rate,
            actual_pass_rate=pass_rate,
            reasons=reasons,
        )
        response.headers["X-TestForge-Gate"] = _header_value(False)
        return CIRunResponse(
            execution_id=execution.id,
            status=execution.status,
            queued=True,
            gate=gate,
            report=execution.report,
        )

    if total == 0:
        reasons.append("没有执行任何用例")
    if pass_rate < payload.min_pass_rate:
        reasons.append(f"通过率 {pass_rate}% 低于门禁 {payload.min_pass_rate}%")
    if payload.fail_on_defects and defects:
        reasons.append(f"存在 {len(defects)} 条缺陷")

    gate = CIGate(
        passed=not reasons,
        min_pass_rate=payload.min_pass_rate,
        actual_pass_rate=pass_rate,
        reasons=reasons,
    )
    response.headers["X-TestForge-Gate"] = _header_value(gate.passed)

    return CIRunResponse(
        execution_id=execution.id,
        status=execution.status,
        queued=False,
        total=total,
        passed=passed,
        failed=failed,
        pass_rate=pass_rate,
        defect_count=len(defects),
        gate=gate,
        report=execution.report,
    )


@router.post("/coverage", response_model=CoverageOut, status_code=status.HTTP_201_CREATED)
async def ci_coverage(
    project_id: UUID, payload: CoverageIn, user: CurrentUser, db: DbSession
) -> CoverageOut:
    """CI 里通常拿不到登录态，所以单独开一个按 project_id 上报的入口。"""
    project = await project_service.get_project(db, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    report = await coverage_service.create_report(
        db,
        project_id=project_id,
        payload=payload.model_dump(),
        execution_id=payload.execution_id,
        source=payload.source,
    )
    return CoverageOut.model_validate(report)
