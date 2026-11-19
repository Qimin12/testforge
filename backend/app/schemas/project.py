"""项目与 OpenAPI 导入 schema。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    repo_url: str | None = Field(default=None, max_length=500)
    target_base_url: str | None = Field(default=None, max_length=500, description="被测服务地址")


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    repo_url: str | None = Field(default=None, max_length=500)
    target_base_url: str | None = Field(default=None, max_length=500)
    status: Literal["active", "archived"] | None = None
    # TE-04 定时调度
    schedule_enabled: bool | None = None
    schedule_interval_minutes: int | None = Field(default=None, ge=0, le=10080)


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None = None
    repo_url: str | None = None
    status: str
    target_base_url: str | None = None
    case_count: int = 0
    operation_count: int = 0
    schedule_enabled: bool = False
    schedule_interval_minutes: int | None = None
    last_scheduled_at: datetime | None = None
    created_at: datetime


class ProjectPage(BaseModel):
    items: list[ProjectOut]
    total: int


class OpenAPIImportRequest(BaseModel):
    spec: dict[str, Any] = Field(description="OpenAPI / Swagger 文档原文")


class OpenAPIOperation(BaseModel):
    method: str
    path: str
    summary: str = ""
    operation_id: str = ""
    tags: list[str] = Field(default_factory=list)


class OpenAPIImportResult(BaseModel):
    project_id: UUID
    operation_count: int
    base_url: str = ""
    operations: list[OpenAPIOperation]
