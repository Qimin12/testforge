"""测试用例 schema。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AssertionIn(BaseModel):
    mode: Literal["status_code", "json_path", "header", "contains"] = "status_code"
    target: str = ""
    expected: Any = None


class CaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    method: str = Field(default="GET", max_length=10)
    path: str = Field(min_length=1, max_length=500)
    headers: dict[str, str] = Field(default_factory=dict)
    params: dict[str, str] = Field(default_factory=dict)
    body: dict[str, Any] | None = None
    expected_status: int = 200
    assertions: list[AssertionIn] = Field(default_factory=list)
    category: Literal["happy", "boundary", "negative"] | None = None
    rationale: str = ""


class CaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    request: dict[str, Any] | None = None
    assertions: list[AssertionIn] | None = None
    source: Literal["ai", "manual"] | None = None


class CaseOut(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    description: str | None = None
    type: str
    # 完整请求配置：前端编辑时要原样带回，否则 headers/params/body 会被覆盖
    request: dict[str, Any] = Field(default_factory=dict)
    method: str
    path: str
    expected_status: int
    assertions: list[dict[str, Any]] = Field(default_factory=list)
    source: str
    category: str | None = None
    version: int = 1
    created_at: datetime


class CasePage(BaseModel):
    items: list[CaseOut]
    total: int


class CaseBulkCreate(BaseModel):
    cases: list[CaseCreate] = Field(min_length=1)
    source: Literal["ai", "manual"] = "manual"
