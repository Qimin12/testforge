"""连接与事务。

设计要点：引擎与会话工厂都是**懒加载 + 可重置**的，这样
1) 导入模块时不会连库（单元测试可以随便 import）；
2) 测试里可以改 ``DATABASE_URL`` 之后调用 :func:`reset_engine` 换库。
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.logging import get_logger
from app.db.base import Base

logger = get_logger(__name__)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _engine_kwargs() -> dict:
    kwargs: dict = {"echo": settings.db_echo, "pool_pre_ping": True, "future": True}
    if settings.is_sqlite:
        # aiosqlite 在工作线程里跑，必须关掉同线程检查；SQLite 也没有连接池参数
        kwargs["connect_args"] = {"check_same_thread": False}
        kwargs.pop("pool_pre_ping", None)
        # 内存库必须用 StaticPool，否则每条连接都是**独立的空库**（表建了也查不到）
        if ":memory:" in settings.sqlalchemy_url:
            from sqlalchemy.pool import StaticPool

            kwargs["poolclass"] = StaticPool
    else:
        kwargs["pool_size"] = 10
        kwargs["max_overflow"] = 20
        kwargs["pool_recycle"] = 1800
    return kwargs


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(settings.sqlalchemy_url, **_engine_kwargs())
        logger.debug("db.engine.created", url=_safe_url(settings.sqlalchemy_url))
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(), expire_on_commit=False, autoflush=False
        )
    return _sessionmaker


def reset_engine() -> None:
    """丢弃缓存的引擎/工厂（测试换库、或配置热更新时用）。"""
    global _engine, _sessionmaker
    _engine = None
    _sessionmaker = None


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：每个请求一个会话，异常回滚。"""
    session = get_sessionmaker()()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def init_db() -> None:
    """开发期建表。生产请用 Alembic，并把 AUTO_CREATE_TABLES 关掉。"""
    # 必须导入模型包，否则 Base.metadata 里没有表定义
    import app.db.models  # noqa: F401  （副作用导入）

    if not settings.auto_create_tables:
        logger.info("db.init.skipped", reason="auto_create_tables=false")
        return

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("db.init.done", tables=len(Base.metadata.tables))


async def dispose_engine() -> None:
    """应用关闭时释放连接池。"""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        logger.debug("db.engine.disposed")


def _safe_url(url: str) -> str:
    """日志里不能出现密码。"""
    if "@" not in url:
        return url
    head, tail = url.split("@", 1)
    scheme = head.split("://", 1)[0]
    return f"{scheme}://***@{tail}"
