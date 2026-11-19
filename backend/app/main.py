"""TestForge 后端入口。

启动：``uvicorn app.main:app --reload --host 0.0.0.0 --port 8000``
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.agents.checkpointer import checkpointer_info, close_saver
from app.agents.graph import reset_graph
from app.agents.llm import is_mock_mode
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.session import dispose_engine, init_db

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    logger.info(
        "app.starting",
        env=settings.app_env,
        db="sqlite" if settings.is_sqlite else "postgres",
        checkpointer=settings.langgraph_checkpointer,
        llm_mock=is_mock_mode(),
    )
    await init_db()
    # 提前把 checkpointer 建起来，把配置错误暴露在启动时而不是首个请求里
    from app.agents.checkpointer import get_saver

    await get_saver()
    yield
    logger.info("app.shutting_down")
    await close_saver()
    reset_graph()
    await dispose_engine()


app = FastAPI(
    title=f"{settings.app_name} API",
    version=__version__,
    description="AI 驱动的全链路自动化测试平台 —— 后端接口",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", tags=["元信息"], include_in_schema=False)
async def root() -> dict[str, str]:
    return {"name": settings.app_name, "version": __version__, "docs": "/docs"}


@app.get("/health", tags=["元信息"])
async def health() -> dict[str, Any]:
    """健康检查：同时反映依赖的真实状态，方便部署探针定位问题。"""
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": __version__,
        "env": settings.app_env,
        "database": {
            "driver": "sqlite" if settings.is_sqlite else "postgresql",
            "auto_create_tables": settings.auto_create_tables,
        },
        "checkpointer": checkpointer_info(),
        "llm": {
            "provider": settings.llm_provider,
            "mock": is_mock_mode(),
            "model_large": settings.llm_model_large,
            "model_small": settings.llm_model_small,
        },
        "celery": {
            "eager": settings.celery_eager,
            "broker": _mask_broker(settings.celery_broker_url),
        },
        "review_required": settings.require_review,
    }


def _mask_broker(url: str) -> str:
    """broker 地址可能带密码，健康检查里只回显主机端口。"""
    if "@" not in url:
        return url
    _, tail = url.rsplit("@", 1)
    return f"***@{tail}"
