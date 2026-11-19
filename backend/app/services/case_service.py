"""用例服务：ORM 与「图内部用例 dict」之间的双向转换 + 增删改查。

图的输入输出是普通 dict（不依赖 ORM，方便单测），数据库这边是
``test_cases.request`` / ``test_cases.assertions`` 两列 JSON。
这里负责把两边对齐，避免转换逻辑散落各处。

字段约定（request 列）::

    {"method": "GET", "path": "/users", "headers": {...},
     "params": {...}, "body": {...} | null, "expected_status": 200}
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import CaseSource, CaseType, TestCase

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# 双向转换
# --------------------------------------------------------------------------- #
def to_graph_case(case: TestCase) -> dict[str, Any]:
    """ORM → 图可消费的 dict（带 id，执行结果才能回填 case_id）。"""
    request = case.request or {}
    ai_meta = case.ai_meta or {}
    return {
        "id": str(case.id),
        "name": case.name,
        "category": ai_meta.get("category"),
        "method": (request.get("method") or "GET").upper(),
        "path": request.get("path") or "/",
        "headers": request.get("headers") or {},
        "params": request.get("params") or {},
        "body": request.get("body"),
        "expected_status": int(request.get("expected_status") or 200),
        "assertions": case.assertions or [],
        "source": case.source,
        "rationale": ai_meta.get("rationale", ""),
    }


def from_graph_case(project_id: UUID, case: dict[str, Any], *, source: str = CaseSource.AI.value) -> TestCase:
    """图生成的 dict → ORM 对象。"""
    return TestCase(
        project_id=project_id,
        name=(case.get("name") or "未命名用例")[:200],
        description=(case.get("rationale") or None),
        type=CaseType.API.value,
        request={
            "method": (case.get("method") or "GET").upper(),
            "path": case.get("path") or "/",
            "headers": case.get("headers") or {},
            "params": case.get("params") or {},
            "body": case.get("body"),
            "expected_status": int(case.get("expected_status") or 200),
        },
        assertions=case.get("assertions") or [],
        source=source,
        ai_meta={
            "category": case.get("category"),
            "rationale": case.get("rationale", ""),
            "generated": True,
        },
    )


# --------------------------------------------------------------------------- #
# 增删改查
# --------------------------------------------------------------------------- #
async def list_cases(
    db: AsyncSession,
    *,
    project_id: UUID | str,
    case_type: str | None = None,
    keyword: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[TestCase], int]:
    conditions = [TestCase.project_id == _as_uuid(project_id)]
    if case_type:
        conditions.append(TestCase.type == case_type)
    if keyword:
        conditions.append(TestCase.name.ilike(f"%{keyword}%"))

    total = await db.scalar(select(func.count()).select_from(TestCase).where(*conditions))
    stmt = (
        select(TestCase)
        .where(*conditions)
        .order_by(TestCase.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(await db.scalars(stmt)), int(total or 0)


async def bulk_create(
    db: AsyncSession,
    *,
    project_id: UUID | str,
    cases: list[dict[str, Any]],
    source: str = CaseSource.AI.value,
    skip_duplicates: bool = True,
) -> list[TestCase]:
    """批量落库；默认按 (project_id, name) 去重，重复生成不会堆垃圾数据。"""
    pid = _as_uuid(project_id)
    existing: set[str] = set()
    if skip_duplicates:
        rows = await db.scalars(select(TestCase.name).where(TestCase.project_id == pid))
        existing = {name for name in rows}

    created: list[TestCase] = []
    for item in cases:
        name = (item.get("name") or "未命名用例")[:200]
        if name in existing:
            continue
        obj = from_graph_case(pid, item, source=source)
        db.add(obj)
        created.append(obj)
        existing.add(name)

    await db.flush()
    logger.info("cases.bulk_created", project_id=str(pid), created=len(created), received=len(cases))
    return created


async def get_case(db: AsyncSession, case_id: UUID | str) -> TestCase | None:
    return await db.get(TestCase, _as_uuid(case_id))


async def update_case(db: AsyncSession, case: TestCase, data: dict[str, Any]) -> TestCase:
    if data.get("name"):
        case.name = data["name"][:200]
    if data.get("description") is not None:
        case.description = data["description"]
    if data.get("request") is not None:
        case.request = data["request"]
    if data.get("assertions") is not None:
        case.assertions = data["assertions"]
    case.source = CaseSource.MANUAL.value if data.get("source") == "manual" else case.source
    case.version = (case.version or 1) + 1
    await db.flush()
    return case


async def delete_case(db: AsyncSession, case: TestCase) -> None:
    await db.delete(case)


async def count_by_project(db: AsyncSession, project_id: UUID | str) -> int:
    total = await db.scalar(
        select(func.count()).select_from(TestCase).where(TestCase.project_id == _as_uuid(project_id))
    )
    return int(total or 0)


def _as_uuid(value: Any) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))
