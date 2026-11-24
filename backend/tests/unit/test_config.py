"""配置解析：DSN 规范化的各种写法。"""

from __future__ import annotations

import pytest

from app.core.config import normalize_async_dsn, normalize_sync_dsn, settings


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # 用户手写 postgresql:// 时自动补异步驱动
        ("postgresql://u:p@h:5432/db", "postgresql+asyncpg://u:p@h:5432/db"),
        # 已经写了驱动就原样返回
        ("postgresql+asyncpg://u:p@h:5432/db", "postgresql+asyncpg://u:p@h:5432/db"),
        # Heroku 风格的 postgres:// 也要认
        ("postgres://u:p@h:5432/db", "postgresql+asyncpg://u:p@h:5432/db"),
        # SQLite 补 aiosqlite
        ("sqlite:///./x.db", "sqlite+aiosqlite:///./x.db"),
        ("sqlite+aiosqlite:///./x.db", "sqlite+aiosqlite:///./x.db"),
        # 未知协议不猜，原样返回
        ("mysql://u:p@h/db", "mysql://u:p@h/db"),
    ],
)
def test_normalize_async_dsn(raw: str, expected: str) -> None:
    assert normalize_async_dsn(raw) == expected


@pytest.mark.unit
def test_normalize_async_dsn_strips_whitespace() -> None:
    assert normalize_async_dsn("  sqlite:///./x.db  ") == "sqlite+aiosqlite:///./x.db"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("postgresql+asyncpg://u:p@h:5432/db", "postgresql://u:p@h:5432/db"),
        ("postgresql://u:p@h:5432/db", "postgresql://u:p@h:5432/db"),
    ],
)
def test_normalize_sync_dsn(raw: str, expected: str) -> None:
    """LangGraph 的 PostgresSaver 只认同步 DSN。"""
    assert normalize_sync_dsn(raw) == expected


@pytest.mark.unit
def test_settings_expose_async_url_and_sqlite_flag() -> None:
    assert settings.sqlalchemy_url.startswith("sqlite+aiosqlite:///")
    assert settings.is_sqlite is True


@pytest.mark.unit
def test_sync_dsn_falls_back_to_database_url() -> None:
    """没配 CHECKPOINT_DB_URL 时，用主库 DSN 兜底且去掉异步驱动名。"""
    dsn = settings.sync_dsn
    assert "+asyncpg" not in dsn
