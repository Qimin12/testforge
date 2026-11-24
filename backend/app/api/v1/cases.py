"""单条用例的读写（TG-05：手动编辑 AI 生成的用例）。"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.api.serializers import case_out
from app.db.models import Project
from app.schemas.case import CaseOut, CaseUpdate
from app.services import case_service

router = APIRouter(prefix="/cases", tags=["测试用例"])


async def _owned_case(db: DbSession, case_id: UUID, user: CurrentUser):
    case = await case_service.get_case(db, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用例不存在")
    project = await db.get(Project, case.project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用例不存在")
    return case


@router.get("/{case_id}", response_model=CaseOut)
async def get_case(case_id: UUID, user: CurrentUser, db: DbSession) -> CaseOut:
    case = await _owned_case(db, case_id, user)
    return case_out(case)


@router.patch("/{case_id}", response_model=CaseOut)
async def update_case(
    case_id: UUID, payload: CaseUpdate, user: CurrentUser, db: DbSession
) -> CaseOut:
    case = await _owned_case(db, case_id, user)
    data = payload.model_dump(exclude_unset=True)
    if "assertions" in data and data["assertions"] is not None:
        data["assertions"] = [
            item.model_dump() if hasattr(item, "model_dump") else item for item in data["assertions"]
        ]
    case = await case_service.update_case(db, case, data)
    return case_out(case)


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_case(case_id: UUID, user: CurrentUser, db: DbSession) -> None:
    case = await _owned_case(db, case_id, user)
    await case_service.delete_case(db, case)
