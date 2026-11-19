"""节点之间传递的结构化输出契约。

用 Pydantic 模型接 ``with_structured_output``，让模型必须返回合法结构，
而不是让下游节点去猜字符串。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


# --------------------------------------------------------------------------- #
# Case Generator（TG-01 / TG-02 / TG-03）
# --------------------------------------------------------------------------- #
class AssertionSpec(BaseModel):
    """一条断言。"""

    mode: Literal["status_code", "json_path", "header", "contains"] = Field(
        description="断言类型：状态码 / JSON 路径取值 / 响应头 / 文本包含"
    )
    target: str = Field(default="", description="json_path 用点号路径如 data.items.0.id；header 用头名")
    expected: str | int | float | bool = Field(description="期望值")


class GeneratedCase(BaseModel):
    """AI 生成的一条 API 测试用例。"""

    name: str = Field(description="用例名，中文，能一眼看出测什么")
    category: Literal["happy", "boundary", "negative"] = Field(
        description="happy=正向, boundary=边界, negative=异常"
    )
    method: HttpMethod = Field(description="HTTP 方法")
    path: str = Field(description="相对路径，如 /users/{id}，不要带域名")
    headers: dict[str, str] = Field(default_factory=dict)
    params: dict[str, str] = Field(default_factory=dict)
    body: dict | None = Field(default=None, description="JSON 请求体，GET 用 null")
    expected_status: int = Field(description="期望的 HTTP 状态码")
    assertions: list[AssertionSpec] = Field(default_factory=list)
    rationale: str = Field(default="", description="为什么设计这条用例")


class CaseGenOutput(BaseModel):
    cases: list[GeneratedCase] = Field(default_factory=list)
    notes: str = Field(default="", description="覆盖策略说明或无法覆盖的地方")


# --------------------------------------------------------------------------- #
# Analyzer（DA-01 / DA-02 / DA-03）
# --------------------------------------------------------------------------- #
class FailureAnalysis(BaseModel):
    case_name: str
    failure_reason: str = Field(description="失败的直接原因")
    root_cause: str = Field(description="根因：是请求构造错、被测服务 bug、还是断言写错")
    fix_suggestion: str = Field(description="可执行的修复建议")
    severity: Literal["blocker", "critical", "major", "minor"] = "major"
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)


class AnalysisOutput(BaseModel):
    items: list[FailureAnalysis] = Field(default_factory=list)
    overall: str = Field(default="", description="整体判断")


# --------------------------------------------------------------------------- #
# Defect Classifier（DA-04）
# --------------------------------------------------------------------------- #
class DefectItem(BaseModel):
    case_name: str
    title: str = Field(description="缺陷标题，一句话")
    description: str = Field(description="缺陷描述：现象 + 期望")
    category: Literal["functional", "performance", "security"] = "functional"
    severity: Literal["blocker", "critical", "major", "minor"] = "major"


class DefectOutput(BaseModel):
    defects: list[DefectItem] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Report Generator（RP-01 / RP-03）
# --------------------------------------------------------------------------- #
class ReportOutput(BaseModel):
    summary: str = Field(description="2~4 句话的结论")
    risk_level: Literal["low", "medium", "high"] = "low"
    highlights: list[str] = Field(default_factory=list, description="值得注意的点")
