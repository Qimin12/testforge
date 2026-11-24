"""项目服务：增删改查 + OpenAPI 文档导入与解析。

PM-03 的关键不是「存一段 JSON」，而是**导入时就要解析出接口清单**，
否则后面生成用例时模型拿不到结构化输入。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import Project, ProjectStatus

logger = get_logger(__name__)

_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


class OpenAPIError(ValueError):
    """文档不合法。"""


async def create_project(
    db: AsyncSession,
    *,
    user_id: UUID,
    name: str,
    description: str | None = None,
    repo_url: str | None = None,
    target_base_url: str | None = None,
) -> Project:
    project = Project(
        user_id=user_id,
        name=name,
        description=description,
        repo_url=repo_url,
        target_config={"base_url": target_base_url} if target_base_url else None,
        status=ProjectStatus.ACTIVE.value,
    )
    db.add(project)
    await db.flush()
    logger.info("project.created", project_id=str(project.id), name=name)
    return project


async def get_project(
    db: AsyncSession, project_id: UUID | str, *, user_id: UUID | None = None
) -> Project | None:
    project = await db.get(Project, _as_uuid(project_id))
    if project is None:
        return None
    if user_id is not None and project.user_id != user_id:
        return None
    return project


async def list_projects(
    db: AsyncSession,
    *,
    user_id: UUID,
    status: str | None = None,
    keyword: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Project], int]:
    conditions = [Project.user_id == user_id]
    if status:
        conditions.append(Project.status == status)
    if keyword:
        like = f"%{keyword}%"
        conditions.append(or_(Project.name.ilike(like), Project.description.ilike(like)))

    total = await db.scalar(select(func.count()).select_from(Project).where(*conditions))
    stmt = (
        select(Project)
        .where(*conditions)
        .order_by(Project.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(await db.scalars(stmt)), int(total or 0)


async def update_project(db: AsyncSession, project: Project, data: dict[str, Any]) -> Project:
    for field in ("name", "description", "repo_url", "status"):
        if field in data and data[field] is not None:
            setattr(project, field, data[field])

    # TE-04：schedule_interval_minutes 允许为 0（等于关闭），所以不能用 is not None 之外的过滤
    for field in ("schedule_enabled", "schedule_interval_minutes"):
        if field in data and data[field] is not None:
            setattr(project, field, data[field])

    if data.get("target_base_url") is not None:
        config = dict(project.target_config or {})
        config["base_url"] = data["target_base_url"]
        project.target_config = config
    await db.flush()
    return project


# --------------------------------------------------------------------------- #
# OpenAPI 导入（PM-03）
# --------------------------------------------------------------------------- #
def parse_openapi(raw: dict[str, Any]) -> dict[str, Any]:
    """校验并提取接口清单。

    校验用 openapi-spec-validator；如果该包缺失则退化为结构检查，
    不让「少装一个包」把导入功能整个堵死。
    """
    if not isinstance(raw, dict) or not raw:
        raise OpenAPIError("OpenAPI 文档必须是一个非空 JSON 对象")
    if not (raw.get("openapi") or raw.get("swagger")):
        raise OpenAPIError("缺少 openapi / swagger 版本字段")

    spec = _coerce_to_openapi3(raw)

    errors = _validate(spec)
    if errors:
        raise OpenAPIError("OpenAPI 校验失败: " + "; ".join(errors[:3]))

    operations = extract_operations(spec)
    if not operations:
        raise OpenAPIError("文档中没有可测试的接口（paths 为空）")

    return {
        "spec": spec,
        "operations": operations,
        "operation_count": len(operations),
        "base_url": _base_url(spec),
    }


def extract_operations(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """把 paths 摊平成 [{method, path, summary, operation_id}]。"""
    out: list[dict[str, Any]] = []
    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if method.lower() not in _HTTP_METHODS or not isinstance(op, dict):
                continue
            out.append(
                {
                    "method": method.upper(),
                    "path": path,
                    "summary": op.get("summary") or "",
                    "operation_id": op.get("operationId") or "",
                    "tags": op.get("tags") or [],
                }
            )
    return out


def _validate(spec: dict[str, Any]) -> list[str]:
    try:
        from openapi_spec_validator import validate as validate_spec
    except ImportError:  # pragma: no cover - 依赖缺失时的降级
        logger.warning("openapi.validator_missing")
        return []

    try:
        validate_spec(spec)
    except Exception as exc:
        return [f"{type(exc).__name__}: {exc}"]
    return []


def _base_url(spec: dict[str, Any]) -> str:
    servers = spec.get("servers") or []
    if isinstance(servers, list) and servers:
        first = servers[0]
        if isinstance(first, dict) and first.get("url"):
            return str(first["url"]).rstrip("/")
    host = spec.get("host")
    if host:
        scheme = (spec.get("schemes") or ["http"])[0]
        base = spec.get("basePath") or ""
        return f"{scheme}://{host}{base}".rstrip("/")
    return ""


def _coerce_to_openapi3(raw: dict[str, Any]) -> dict[str, Any]:
    """把 Swagger 2.0 粗略转成 OpenAPI 3 结构，失败时原样返回。

    只做校验/解析需要的最小转换，不改接口语义；真正的测试生成由模型读文档完成。
    """
    if raw.get("openapi"):
        return raw

    spec = dict(raw)
    spec["openapi"] = "3.0.0"
    spec.pop("swagger", None)

    if "host" in spec or "basePath" in spec:
        scheme = (spec.get("schemes") or ["http"])[0]
        host = spec.get("host") or "localhost"
        base = spec.get("basePath") or ""
        spec.setdefault("servers", [{"url": f"{scheme}://{host}{base}"}])

    # Swagger2 的 body 参数 → requestBody（仅形状对齐，不追求完备）
    for item in (spec.get("paths") or {}).values():
        if not isinstance(item, dict):
            continue
        for op in item.values():
            if not isinstance(op, dict):
                continue
            params = op.get("parameters")
            if not isinstance(params, list):
                continue
            body = next((p for p in params if isinstance(p, dict) and p.get("in") == "body"), None)
            if body:
                op["requestBody"] = {
                    "content": {"application/json": {"schema": body.get("schema") or {"type": "object"}}}
                }
                op["parameters"] = [p for p in params if p is not body]
    return spec


def _as_uuid(value: Any) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))
