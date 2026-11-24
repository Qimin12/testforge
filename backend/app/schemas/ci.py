"""CI/CD 相关 schema（PRD CD-01~CD-05）。"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class CIProjectOut(BaseModel):
    id: UUID
    name: str
    operation_count: int = 0
    case_count: int = 0
    target_base_url: str | None = None


class CIRunRequest(BaseModel):
    project_id: UUID
    mode: Literal["full", "generate", "execute_only"] = "full"
    # 质量门禁（CD-05）：通过率低于这个值就判定失败
    min_pass_rate: float = Field(default=100.0, ge=0, le=100)
    # 有 open 状态的缺陷也算失败
    fail_on_defects: bool = True
    async_mode: bool = Field(default=False, description="true 时立即返回 execution_id，后台跑")


class CIGate(BaseModel):
    passed: bool
    min_pass_rate: float
    actual_pass_rate: float
    reasons: list[str] = Field(default_factory=list)


class CIRunResponse(BaseModel):
    execution_id: UUID
    status: str
    queued: bool = False
    total: int = 0
    passed: int = 0
    failed: int = 0
    pass_rate: float = 0.0
    defect_count: int = 0
    gate: CIGate
    report: dict[str, Any] | None = None


class UsageOut(BaseModel):
    period: str
    total_tokens: int
    by_node: dict[str, int] = Field(default_factory=dict)
    budget: int
    used_ratio: float
    over_budget: bool
    warning: str | None = None
    executions: int = 0
