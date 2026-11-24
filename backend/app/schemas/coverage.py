"""覆盖率上报 schema（RP-02）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CoverageIn(BaseModel):
    """可以直接传百分比，也可以传分子分母（自动算百分比）。"""

    line_rate: float | None = Field(default=None, ge=0, le=100)
    branch_rate: float | None = Field(default=None, ge=0, le=100)
    total_lines: int = Field(default=0, ge=0)
    covered_lines: int = Field(default=0, ge=0)
    total_branches: int = Field(default=0, ge=0)
    covered_branches: int = Field(default=0, ge=0)
    execution_id: UUID | None = None
    source: str = Field(default="pytest-cov", max_length=30)
    raw: dict[str, Any] | None = None


class CoverageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    execution_id: UUID | None = None
    line_rate: float
    branch_rate: float
    total_lines: int
    covered_lines: int
    total_branches: int
    covered_branches: int
    source: str
    created_at: datetime
