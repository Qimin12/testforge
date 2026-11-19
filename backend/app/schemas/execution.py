"""执行记录 / 结果 / 缺陷 / 报告 schema。"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ResultOut(BaseModel):
    id: UUID
    case_id: UUID | None = None
    case_name: str
    status: str
    expected_output: str | None = None
    actual_output: str | None = None
    error_message: str | None = None
    duration_ms: int | None = None


class DefectOut(BaseModel):
    id: UUID
    execution_id: UUID
    case_id: UUID | None = None
    title: str
    description: str
    severity: str
    category: str
    root_cause: str | None = None
    fix_suggestion: str | None = None
    fingerprint: str | None = None
    status: str
    created_at: datetime


class DefectPage(BaseModel):
    items: list[DefectOut]
    total: int


class ExecutionOut(BaseModel):
    id: UUID
    project_id: UUID
    trigger_type: str
    status: str
    graph_mode: str | None = None
    graph_thread_id: str | None = None
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    pass_rate: float = 0.0
    duration_ms: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class ExecutionDetail(ExecutionOut):
    results: list[ResultOut] = Field(default_factory=list)
    defects: list[DefectOut] = Field(default_factory=list)
    report: dict[str, Any] | None = None
    token_usage: dict[str, Any] | None = None


class ExecutionPage(BaseModel):
    items: list[ExecutionOut]
    total: int


class RunProjectRequest(BaseModel):
    """从项目直接发起一次执行（走项目的 api_spec 与 target_base_url）。"""

    mode: str = Field(default="full", description="full / generate / execute_only")
    trigger_type: str = Field(default="manual", description="manual / cron / webhook / api")
    thread_id: str | None = None
    async_mode: bool = Field(
        default=False,
        description="true 时交给 Celery 后台执行，立即返回 pending 的执行记录",
    )
