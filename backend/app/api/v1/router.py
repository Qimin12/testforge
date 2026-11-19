"""v1 路由聚合。"""

from fastapi import APIRouter

from app.api.v1 import auth, cases, ci, executions, graph, projects, usage

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(projects.router)
api_router.include_router(cases.router)
api_router.include_router(executions.router)
api_router.include_router(ci.router)
api_router.include_router(usage.router)
api_router.include_router(graph.router)

__all__ = ["api_router"]
