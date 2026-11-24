"""执行编排：项目 → LangGraph → 落库。

被三处复用，所以单独成模块：
* ``POST /projects/{id}/run``        人工发起
* ``POST /ci/run``                   CI 流水线发起（质量门禁）
* Celery 任务                        异步 / 定时发起

调用方只关心「传项目 + 模式」，不重复关心状态组装与落库细节。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import get_graph, thread_config
from app.agents.state import new_state
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import Execution, ExecutionStatus, Project
from app.services import case_service, execution_service

logger = get_logger(__name__)


class ExecutionError(Exception):
    """业务上不能执行（缺文档、缺地址…）。调用方负责映射成 HTTP 状态码。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


async def run_project_execution(
    db: AsyncSession,
    project: Project,
    *,
    mode: str = "full",
    trigger_type: str = "manual",
    thread_id: str | None = None,
    execution: Execution | None = None,
) -> Execution:
    """跑一次完整/部分链路并落库，返回执行记录。

    ``execution`` 传入时复用已有记录（异步模式先建 pending 记录再排队）。
    失败时抛 :class:`ExecutionError`；图内部异常会先落一条 failed 执行记录再抛出。
    """
    config = project.target_config or {}
    target_base_url = config.get("base_url") or ""

    if mode in {"full", "generate"} and not project.api_spec:
        raise ExecutionError("项目还没有导入 OpenAPI 文档，请先调用 /projects/{id}/openapi")
    if mode != "generate" and not target_base_url:
        raise ExecutionError("项目缺少被测服务地址（target_base_url），请先设置")

    thread_id = thread_id or (execution.graph_thread_id if execution else None) or f"run-{uuid4().hex}"

    if execution is None:
        execution = await execution_service.create_execution(
            db,
            project_id=project.id,
            trigger_type=trigger_type,
            mode=mode,
            thread_id=thread_id,
        )
    else:
        execution.status = ExecutionStatus.RUNNING.value
        execution.started_at = execution.started_at or datetime.now(UTC)
        execution.graph_thread_id = thread_id
        await db.flush()

    state = new_state(
        mode=mode,
        run_id=str(execution.id),
        project_id=str(project.id),
        target_base_url=target_base_url,
        api_spec=project.api_spec or {},
    )

    if mode == "execute_only":
        rows, _ = await case_service.list_cases(db, project_id=project.id, limit=500)
        if not rows:
            raise ExecutionError("项目下没有可执行的用例")
        state["cases"] = [case_service.to_graph_case(row) for row in rows]

    graph = await get_graph()
    try:
        result = await graph.ainvoke(state, thread_config(thread_id))
    except Exception as exc:
        await execution_service.mark_failed(db, execution, str(exc))
        logger.exception("execution.failed", project_id=str(project.id), execution_id=str(execution.id))
        raise

    await execution_service.persist_state(db, execution, result)

    if mode in {"full", "generate"} and result.get("cases"):
        await case_service.bulk_create(
            db, project_id=project.id, cases=result["cases"], source="ai"
        )

    logger.info(
        "execution.done",
        project_id=str(project.id),
        execution_id=str(execution.id),
        status=execution.status,
        total=execution.total_cases,
        failed=execution.failed_cases,
    )
    return execution


async def run_or_enqueue(
    db: AsyncSession,
    project: Project,
    *,
    mode: str = "full",
    trigger_type: str = "manual",
    async_mode: bool = False,
) -> tuple[Execution, str]:
    """同步执行或丢给 Celery。

    返回 ``(execution, "done" | "queued")``。
    ``CELERY_EAGER=true``（开发默认）时即使请求异步也直接跑完，
    避免「没起 Redis 却要排队」这种自我为难。
    """
    if not async_mode or settings.celery_eager:
        execution = await run_project_execution(
            db, project, mode=mode, trigger_type=trigger_type
        )
        return execution, "done"

    execution = await execution_service.create_execution(
        db, project_id=project.id, trigger_type=trigger_type, mode=mode
    )
    # 先提交，worker 才能查到这条记录
    await db.commit()

    try:
        from app.workers.tasks import run_execution_task

        run_execution_task.delay(str(execution.id), mode)
    except Exception as exc:
        await execution_service.mark_failed(db, execution, f"任务入队失败: {exc}")
        await db.commit()
        raise ExecutionError(f"任务队列不可用，请检查 Redis / Celery: {exc}") from exc

    logger.info("execution.queued", execution_id=str(execution.id), mode=mode)
    return execution, "queued"
