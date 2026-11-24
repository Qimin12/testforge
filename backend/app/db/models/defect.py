"""缺陷（PRD §6.5 / §7.2.5）。"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.db.models.execution import Execution


class Severity(StrEnum):
    BLOCKER = "blocker"
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class DefectCategory(StrEnum):
    """PRD DA-04：自动分类缺陷类型。"""

    FUNCTIONAL = "functional"
    PERFORMANCE = "performance"
    SECURITY = "security"
    UNKNOWN = "unknown"


class DefectStatus(StrEnum):
    OPEN = "open"
    FIXED = "fixed"
    CLOSED = "closed"
    WONTFIX = "wontfix"


class Defect(Base, TimestampMixin):
    __tablename__ = "defects"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    execution_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("executions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    case_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("test_cases.id", ondelete="SET NULL"), index=True, default=None
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(10), default=Severity.MAJOR.value, nullable=False)
    category: Mapped[str] = mapped_column(
        String(20), default=DefectCategory.UNKNOWN.value, nullable=False
    )

    # DA-02 / DA-03：AI 给出的根因与修复建议
    root_cause: Mapped[str | None] = mapped_column(Text, default=None)
    fix_suggestion: Mapped[str | None] = mapped_column(Text, default=None)
    # DA-05 重复缺陷检测预留：case+错误信息的稳定指纹
    fingerprint: Mapped[str | None] = mapped_column(String(64), index=True, default=None)
    status: Mapped[str] = mapped_column(String(20), default=DefectStatus.OPEN.value, nullable=False)

    execution: Mapped[Execution] = relationship(back_populates="defects")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Defect {self.title} {self.severity}>"
