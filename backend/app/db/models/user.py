"""用户与 API Key（PRD §6.1 / §4.1）。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.db.models.project import Project


class UserRole(StrEnum):
    """PRD §4.1 的三种角色。"""

    QA = "qa"
    DEVELOPER = "developer"
    ADMIN = "admin"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    nickname: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500), default=None)
    bio: Mapped[str | None] = mapped_column(Text, default=None)
    role: Mapped[str] = mapped_column(String(20), default=UserRole.QA.value, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # PRD §6.1.3：登录失败 5 次锁 15 分钟
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    api_keys: Mapped[list[ApiKey]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    projects: Mapped[list[Project]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.email} role={self.role}>"


class ApiKey(Base, TimestampMixin):
    """PRD UC-05：明文只在创建时返回一次，库里只存哈希。"""

    __tablename__ = "api_keys"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), default="default", nullable=False)
    # 用于列表展示的前缀（前 12 位），以及完整 Key 的 bcrypt 哈希
    prefix: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    user: Mapped[User] = relationship(back_populates="api_keys")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ApiKey {self.prefix}…>"
