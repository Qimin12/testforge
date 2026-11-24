"""图运行接口：把 LangGraph 暴露成 HTTP。

两个入口：
* ``POST /graph/run``    跑一次图；带 ``project_id`` 时会落库成执行记录
* ``POST /graph/resume`` 用人工决策把挂起的图继续跑完

> 常规业务请用 ``POST /projects/{id}/run``（自动读取项目的 api_spec 与目标地址）；
> 这个接口适合调试：直接塞 api_spec / cases 看图的反应。
"""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, status
from langgraph.types import Command

from app.agents.graph import extract_interrupt, get_graph, thread_config
from app.agents.state import GRAPH_MODES, new_state, summarize
from app.api.deps import CurrentUser, DbSession
from app.core.logging import get_logger
from app.db.models import Project
from app.schemas.graph import GraphResumeRequest, GraphRunRequest, GraphRunResponse
from app.services import execution_service

logger = get_logger(__name__)

# 422 直接写数字：starlette 正在 HTTP_422_UNPROCESSABLE_ENTITY →
# HTTP_422_UNPROCESSABLE_CONTENT 改名，写常量名会在版本升级时报警。
router = APIRouter(prefix="/graph", tags=["AI 编排"])


@router.post("/run", response_model=GraphRunResponse)
async def run_graph(
    payload: GraphRunRequest, user: CurrentUser, db: DbSession
) -> GraphRunResponse:
    if payload.mode not in GRAPH_MODES:
        raise HTTPException(status_code=422, detail="不支持的运行模式")
    if payload.mode in {"full", "generate"} and not payload.api_spec:
        raise HTTPException(status_code=422, detail="full / generate 模式必须提供 api_spec")
    if payload.mode in {"execute_only", "analyze_only"} and not payload.cases:
        raise HTTPException(status_code=422, detail="execute_only / analyze_only 模式必须提供 cases")

    project: Project | None = None
    if payload.project_id:
        try:
            project = await db.get(Project, UUID(payload.project_id))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="project_id 不是合法 UUID") from exc
        if project is None or project.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    graph = await get_graph()
    thread_id = payload.thread_id or f"run-{uuid4().hex}"

    execution = None
    if project is not None:
        execution = await execution_service.create_execution(
            db,
            project_id=project.id,
            trigger_type="api",
            mode=payload.mode,
            thread_id=thread_id,
        )

    state = new_state(
        mode=payload.mode,
        run_id=str(execution.id) if execution else "",
        project_id=str(project.id) if project else "",
        target_base_url=payload.target_base_url,
        api_spec=payload.api_spec,
        cases=payload.cases,
    )

    try:
        result = await graph.ainvoke(state, thread_config(thread_id))
    except Exception as exc:  # 图内部异常不应变成 500 裸奔
        logger.exception("graph.run.failed", thread_id=thread_id)
        if execution is not None:
            await execution_service.mark_failed(db, execution, str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"图执行失败: {exc}"
        ) from exc

    if execution is not None:
        await execution_service.persist_state(db, execution, result)

    pending = extract_interrupt(result)
    return GraphRunResponse(
        thread_id=thread_id,
        execution_id=str(execution.id) if execution else None,
        interrupted=pending is not None,
        pending=pending,
        summary=summarize(result),
    )


@router.post("/resume", response_model=GraphRunResponse)
async def resume_graph(payload: GraphResumeRequest, user: CurrentUser) -> GraphRunResponse:
    graph = await get_graph()
    try:
        result = await graph.ainvoke(
            Command(resume=payload.decision.model_dump()), thread_config(payload.thread_id)
        )
    except Exception as exc:
        logger.exception("graph.resume.failed", thread_id=payload.thread_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"恢复执行失败: {exc}"
        ) from exc

    pending = extract_interrupt(result)
    return GraphRunResponse(
        thread_id=payload.thread_id,
        interrupted=pending is not None,
        pending=pending,
        summary=summarize(result),
    )
