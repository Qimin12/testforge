"""测试用例（PRD §6.3 / §7.2.2）。"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSONType, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.db.models.project import Project


class CaseType(StrEnum):
    API = "api"
    UI = "ui"
    UNIT = "unit"


class CaseSource(StrEnum):
    AI = "ai"
    MANUAL = "manual"


class TestCase(Base, TimestampMixin):
    __tablename__ = "test_cases"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), default=None)
    type: Mapped[str] = mapped_column(String(20), default=CaseType.API.value, nullable=False)

    # 结构化请求：{method, path, headers, params, body}
    request: Mapped[dict | None] = mapped_column(JSONType, default=None)
    # 断言列表：[{mode, target, expected}, ...]
    assertions: Mapped[list | None] = mapped_column(JSONType, default=None)

    source: Mapped[str] = mapped_column(String(20), default=CaseSource.AI.value, nullable=False)
    # AI 生成的附加信息：分类(正向/边界/异常)、生成理由、模型名
    ai_meta: Mapped[dict | None] = mapped_column(JSONType, default=None)
    # TG-06 版本管理预留
    version: Mapped[int] = mapped_column(default=1, nullable=False)

    project: Mapped[Project] = relationship(back_populates="test_cases")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TestCase {self.name} type={self.type}>"
