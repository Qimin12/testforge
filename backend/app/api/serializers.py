"""ORM → 响应模型的转换。集中一处，避免各 router 里重复拼字典。"""

from __future__ import annotations

from typing import Any

from app.db.models import Defect, Execution, Project, TestCase
from app.schemas.case import CaseOut
from app.schemas.execution import DefectOut, ExecutionDetail, ExecutionOut, ResultOut
from app.schemas.project import ProjectOut


def project_out(
    project: Project, *, case_count: int = 0, operation_count: int = 0
) -> ProjectOut:
    config: dict[str, Any] = project.target_config or {}
    return ProjectOut(
        id=project.id,
        name=project.name,
        description=project.description,
        repo_url=project.repo_url,
        status=project.status,
        target_base_url=config.get("base_url"),
        case_count=case_count,
        operation_count=operation_count,
        schedule_enabled=bool(project.schedule_enabled),
        schedule_interval_minutes=project.schedule_interval_minutes,
        last_scheduled_at=project.last_scheduled_at,
        created_at=project.created_at,
    )


def case_out(case: TestCase) -> CaseOut:
    request: dict[str, Any] = case.request or {}
    ai_meta: dict[str, Any] = case.ai_meta or {}
    return CaseOut(
        id=case.id,
        project_id=case.project_id,
        name=case.name,
        description=case.description,
        type=case.type,
        request=request,
        method=(request.get("method") or "GET").upper(),
        path=request.get("path") or "/",
        expected_status=int(request.get("expected_status") or 200),
        assertions=case.assertions or [],
        source=case.source,
        category=ai_meta.get("category"),
        version=case.version or 1,
        created_at=case.created_at,
    )


def execution_out(execution: Execution) -> ExecutionOut:
    total = execution.total_cases or 0
    passed = execution.passed_cases or 0
    return ExecutionOut(
        id=execution.id,
        project_id=execution.project_id,
        trigger_type=execution.trigger_type,
        status=execution.status,
        graph_mode=execution.graph_mode,
        graph_thread_id=execution.graph_thread_id,
        total_cases=total,
        passed_cases=passed,
        failed_cases=execution.failed_cases or 0,
        pass_rate=round(passed / total * 100, 2) if total else 0.0,
        duration_ms=execution.duration_ms,
        started_at=execution.started_at,
        finished_at=execution.finished_at,
        created_at=execution.created_at,
    )


def execution_detail(execution: Execution) -> ExecutionDetail:
    base = execution_out(execution)
    return ExecutionDetail(
        **base.model_dump(),
        results=[
            ResultOut(
                id=row.id,
                case_id=row.case_id,
                case_name=row.case_name,
                status=row.status,
                expected_output=row.expected_output,
                actual_output=row.actual_output,
                error_message=row.error_message,
                duration_ms=row.duration_ms,
            )
            for row in (execution.results or [])
        ],
        defects=[defect_out(row) for row in (execution.defects or [])],
        report=execution.report,
        token_usage=execution.token_usage,
    )


def defect_out(defect: Defect) -> DefectOut:
    return DefectOut(
        id=defect.id,
        execution_id=defect.execution_id,
        case_id=defect.case_id,
        title=defect.title,
        description=defect.description,
        severity=defect.severity,
        category=defect.category,
        root_cause=defect.root_cause,
        fix_suggestion=defect.fix_suggestion,
        fingerprint=defect.fingerprint,
        status=defect.status,
        created_at=defect.created_at,
    )
