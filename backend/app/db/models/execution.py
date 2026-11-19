"""执行记录与用例结果（PRD §6.4 / §7.2.3 / §7.2.4）。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSONType, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.db.models.defect import Defect
    from app.db.models.project import Project


class TriggerType(StrEnum):
    MANUAL = "manual"
    CRON = "cron"
    WEBHOOK = "webhook"
    API = "api"


class ExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    # LangGraph 在 review 节点挂起，等人工确认
    INTERRUPTED = "interrupted"


class ResultStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


class Execution(Base, TimestampMixin):
    __tablename__ = "executions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    trigger_type: Mapped[str] = mapped_column(
        String(20), default=TriggerType.MANUAL.value, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default=ExecutionStatus.PENDING.value, nullable=False
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, default=None)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    # LangGraph 的 thread_id —— 用它恢复中断的执行
    graph_thread_id: Mapped[str | None] = mapped_column(String(64), index=True, default=None)
    graph_mode: Mapped[str | None] = mapped_column(String(20), default=None)

    total_cases: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    passed_cases: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_cases: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    token_usage: Mapped[dict | None] = mapped_column(JSONType, default=None)
    # 报告快照（RP-01）：PRD 没有独立的报告表，报告本质是「一次执行的结论」
    report: Mapped[dict | None] = mapped_column(JSONType, default=None)

    project: Mapped[Project] = relationship(back_populates="executions")
    results: Mapped[list[TestResult]] = relationship(
        back_populates="execution", cascade="all, delete-orphan"
    )
    defects: Mapped[list[Defect]] = relationship(
        back_populates="execution", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Execution {self.id} {self.status}>"


class TestResult(Base, TimestampMixin):
    __tablename__ = "test_results"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    execution_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("executions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    case_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("test_cases.id", ondelete="SET NULL"), index=True, default=None
    )
    case_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)

    actual_output: Mapped[str | None] = mapped_column(Text, default=None)
    expected_output: Mapped[str | None] = mapped_column(Text, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    duration_ms: Mapped[int | None] = mapped_column(Integer, default=None)

    execution: Mapped[Execution] = relationship(back_populates="results")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TestResult {self.case_name} {self.status}>"
