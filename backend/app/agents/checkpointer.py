"""LangGraph 检查点存储：memory / sqlite / postgres 三选一。

为什么要这个文件：图的状态必须持久化，否则
1) 进程重启后执行中的图全丢；
2) ``interrupt()`` 人工中断无法恢复（TG-04）。
开发期用 memory/sqlite 摆脱对虚拟机里 PG 的依赖，联调/生产切 postgres。
"""

from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_saver: BaseCheckpointSaver | None = None
_stack: AsyncExitStack | None = None
_pool: Any = None  # psycopg AsyncConnectionPool


def reset_saver() -> None:
    """丢弃缓存（测试换存储后端时用）。不负责关闭，关闭请用 close_saver。"""
    global _saver, _stack, _pool
    _saver = None
    _stack = None
    _pool = None


async def get_saver() -> BaseCheckpointSaver:
    """返回单例检查点存储。

    单例很重要：memory 模式下如果每次请求都新建 MemorySaver，中断状态就丢了。
    """
    global _saver, _stack, _pool

    if _saver is not None:
        return _saver

    kind = settings.langgraph_checkpointer

    if kind == "memory":
        _saver = MemorySaver()
        logger.info("checkpointer.ready", kind="memory", note="进程重启后状态丢失，仅开发用")

    elif kind == "sqlite":
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        _stack = AsyncExitStack()
        _saver = await _stack.enter_async_context(
            AsyncSqliteSaver.from_conn_string(settings.checkpoint_sqlite_path)
        )
        setup = getattr(_saver, "setup", None)
        if setup is not None:
            await setup()
        logger.info("checkpointer.ready", kind="sqlite", path=settings.checkpoint_sqlite_path)

    elif kind == "postgres":
        if not settings.checkpoint_db_url:
            raise RuntimeError(
                "LANGGRAPH_CHECKPOINTER=postgres 时必须配置 CHECKPOINT_DB_URL"
            )
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        _pool = AsyncConnectionPool(
            conninfo=settings.sync_dsn,
            open=False,
            max_size=10,
            kwargs={
                "autocommit": True,
                "row_factory": dict_row,
                # 池化连接下必须关掉 prepared statement 缓存
                "prepare_threshold": 0,
            },
        )
        await _pool.open()
        _saver = AsyncPostgresSaver(_pool)
        await _saver.setup()
        logger.info("checkpointer.ready", kind="postgres")

    else:  # pragma: no cover - 配置校验已限定取值
        raise RuntimeError(f"未知的 LANGGRAPH_CHECKPOINTER: {kind}")

    return _saver


async def close_saver() -> None:
    """应用关闭时释放资源。"""
    global _saver, _stack, _pool

    if _stack is not None:
        await _stack.aclose()
    if _pool is not None:
        await _pool.close()
    _saver = None
    _stack = None
    _pool = None
    logger.debug("checkpointer.closed")


def checkpointer_info() -> dict[str, Any]:
    kind = settings.langgraph_checkpointer
    info: dict[str, Any] = {"kind": kind, "ready": _saver is not None}
    if kind == "sqlite":
        info["path"] = settings.checkpoint_sqlite_path
    elif kind == "postgres":
        info["dsn_configured"] = bool(settings.checkpoint_db_url)
    return info
