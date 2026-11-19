"""测试项目（PRD §6.2 / §7.2.1）。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSONType, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.db.models.execution import Execution
    from app.db.models.test_case import TestCase
    from app.db.models.user import User


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    repo_url: Mapped[str | None] = mapped_column(String(500), default=None)
    # JSONB：OpenAPI 文档原文 + 解析结果 + 目标环境配置
    api_spec: Mapped[dict | None] = mapped_column(JSONType, default=None)
    # 被测服务的基地址等，执行器从这里取
    target_config: Mapped[dict | None] = mapped_column(JSONType, default=None)
    status: Mapped[str] = mapped_column(String(20), default=ProjectStatus.ACTIVE.value, nullable=False)

    # TE-04 定时调度：开启后 Celery beat 每隔 N 分钟自动跑一次
    schedule_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    schedule_interval_minutes: Mapped[int | None] = mapped_column(Integer, default=None)
    last_scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    owner: Mapped[User] = relationship(back_populates="projects")
    test_cases: Mapped[list[TestCase]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    executions: Mapped[list[Execution]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Project {self.name}>"
