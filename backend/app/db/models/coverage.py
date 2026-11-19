"""覆盖率上报（PRD RP-02）。

平台不自己跑覆盖率——覆盖率必须由项目自己的测试跑出来（pytest-cov / jacoco / nyc），
然后把结果 POST 上来。这里只负责存储与展示。
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Integer, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONType, TimestampMixin


class CoverageReport(Base, TimestampMixin):
    __tablename__ = "coverage_reports"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # 可以关联某次执行，也可以独立上报（CI 里带了用例执行时关联）
    execution_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("executions.id", ondelete="SET NULL"), index=True, default=None
    )

    line_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    branch_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    total_lines: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    covered_lines: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_branches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    covered_branches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source: Mapped[str] = mapped_column(String(30), default="pytest-cov", nullable=False)
    raw: Mapped[dict | None] = mapped_column(JSONType, default=None)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CoverageReport {self.project_id} lines={self.line_rate}%>"
