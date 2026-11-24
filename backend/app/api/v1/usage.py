"""成本接口（CO-01 / CO-04）：本月 token 用量与预算告警。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.ci import UsageOut
from app.services import usage_service

router = APIRouter(tags=["成本"])


@router.get("/usage", response_model=UsageOut)
async def get_usage(user: CurrentUser, db: DbSession) -> UsageOut:
    data = await usage_service.monthly_usage(db, user.id)
    return UsageOut(**data)
