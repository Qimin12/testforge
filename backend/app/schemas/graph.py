"""图运行相关 schema。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

GraphModeLiteral = Literal["full", "generate", "execute_only", "analyze_only", "report_only"]


class GraphRunRequest(BaseModel):
    mode: GraphModeLiteral = "full"
    project_id: str | None = None
    target_base_url: str = Field(default="", description="被测服务基地址，如 http://localhost:8080")
    api_spec: dict[str, Any] | None = Field(default=None, description="OpenAPI 文档原文")
    cases: list[dict[str, Any]] | None = Field(default=None, description="已有用例（execute_only 模式）")
    thread_id: str | None = Field(default=None, description="不传则自动生成")


class ReviewDecision(BaseModel):
    approved: bool
    cases: list[dict[str, Any]] | None = Field(default=None, description="审核修改后的用例，可选")
    reason: str = ""


class GraphResumeRequest(BaseModel):
    thread_id: str
    decision: ReviewDecision


class GraphRunResponse(BaseModel):
    thread_id: str
    execution_id: str | None = Field(default=None, description="带 project_id 运行时会落库并返回")
    interrupted: bool = False
    pending: dict[str, Any] | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
