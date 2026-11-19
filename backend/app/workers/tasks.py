"""Celery 任务。

两个任务：
* ``testforge.run_execution`` —— 跑一条已创建的执行记录（异步模式用）
* ``testforge.scan_schedules`` —— 定时扫描，把到点的项目丢进队列（TE-04）
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from app.core.logging import configure_logging, get_logger
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="testforge.run_execution", bind=True, max_retries=0)
def run_execution_task(self: Any, execution_id: str, mode: str = "full") -> dict[str, Any]:
    """在 worker 进程里跑一次执行。

    注意：worker 是长驻进程但每个任务都新建事件循环，
    所以进入前必须把绑定在旧循环上的引擎/图单例重置掉。
    """
    return asyncio.run(_run_execution(execution_id, mode))


async def _run_execution(execution_id: str, mode: str) -> dict[str, Any]:
    from app.agents.checkpointer import close_saver
    from app.agents.graph import reset_graph
    from app.db.models import Execution, Project
    from app.db.session import dispose_engine, get_sessionmaker, reset_engine
    from app.services.execution_runner import ExecutionError, run_project_execution

    configure_logging()
    reset_engine()
    reset_graph()

    try:
        async with get_sessionmaker()() as db:
            execution = await db.get(Execution, UUID(execution_id))
            if execution is None:
                return {"ok": False, "error": "执行记录不存在"}

            project = await db.get(Project, execution.project_id)
            if project is None:
                return {"ok": False, "error": "项目不存在"}

            try:
                finished = await run_project_execution(
                    db,
                    project,
                    mode=mode,
                    trigger_type=execution.trigger_type,
                    thread_id=execution.graph_thread_id,
                    execution=execution,
                )
            except ExecutionError as exc:
                await db.commit()
                return {"ok": False, "error": exc.message}
            except Exception as exc:
                await db.commit()
                logger.exception("task.run_execution.failed", execution_id=execution_id)
                return {"ok": False, "error": str(exc)}

            await db.commit()
            return {
                "ok": True,
                "execution_id": str(finished.id),
                "status": finished.status,
                "total": finished.total_cases,
                "failed": finished.failed_cases,
            }
    finally:
        await close_saver()
        reset_graph()
        await dispose_engine()
        reset_engine()


@celery_app.task(name="testforge.scan_schedules")
def scan_schedules_task() -> dict[str, Any]:
    return asyncio.run(_scan_schedules())


async def _scan_schedules() -> dict[str, Any]:
    from sqlalchemy import select

    from app.db.models import Project
    from app.db.session import dispose_engine, get_sessionmaker, reset_engine
    from app.services import execution_service

    reset_engine()
    try:
        async with get_sessionmaker()() as db:
            now = datetime.now(UTC)
            rows = list(
                await db.scalars(
                    select(Project).where(
                        Project.schedule_enabled.is_(True),
                        Project.schedule_interval_minutes.is_not(None),
                        Project.status == "active",
                    )
                )
            )

            dispatched: list[str] = []
            for project in rows:
                interval = project.schedule_interval_minutes or 0
                if interval <= 0:
                    continue

                last = project.last_scheduled_at
                if last is not None and last.tzinfo is None:  # SQLite 读出来是 naive
                    last = last.replace(tzinfo=UTC)
                if last is not None and now - last < timedelta(minutes=interval):
                    continue

                project.last_scheduled_at = now
                execution = await execution_service.create_execution(
                    db, project_id=project.id, trigger_type="cron", mode="full"
                )
                await db.commit()

                run_execution_task.delay(str(execution.id), "full")
                dispatched.append(str(execution.id))

            logger.info("scheduler.scanned", projects=len(rows), dispatched=len(dispatched))
            return {"ok": True, "scanned": len(rows), "dispatched": len(dispatched), "ids": dispatched}
    finally:
        await dispose_engine()
        reset_engine()
