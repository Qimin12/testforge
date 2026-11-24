"""Case Generator 节点（TG-01 / TG-02 / TG-03）。

输入：``api_spec``
输出：``cases``（统一结构的可执行用例）
"""

from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agents.llm import is_mock_mode, structured_invoke
from app.agents.prompts import CASE_GEN_SYSTEM, build_case_gen_prompt
from app.agents.schemas import CaseGenOutput, GeneratedCase
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


async def case_gen(
    state: dict[str, Any], config: RunnableConfig | None = None
) -> dict[str, Any]:
    spec = state.get("api_spec") or {}
    base_url = state.get("target_base_url") or ""

    if not isinstance(spec, dict) or not spec.get("paths"):
        return {
            "cases": [],
            "errors": ["api_spec 为空或缺少 paths 字段，无法生成测试用例"],
        }

    try:
        usage: dict[str, int] = {}
        if is_mock_mode():
            output = _mock_output(spec)
            logger.info("case_gen.mock", paths=len(spec.get("paths") or {}))
        else:
            prompt = build_case_gen_prompt(spec, base_url)
            output, usage = await structured_invoke(
                CaseGenOutput,
                [("system", CASE_GEN_SYSTEM), ("human", prompt)],
                tier="large",
                scope="case_gen",
            )
    except Exception as exc:  # 网络/模型/解析失败都不应该让整张图崩溃
        logger.warning("case_gen.failed", error=str(exc))
        return {"cases": [], "errors": [f"用例生成失败: {exc}"]}

    cases = [_normalize(c) for c in output.cases]
    cases = cases[: settings.max_cases_per_run]

    errors: list[str] = []
    if not cases:
        errors.append("模型未返回任何用例")
    if output.notes:
        logger.debug("case_gen.notes", notes=output.notes)

    return {"cases": cases, "errors": errors, "token_usage": usage}


def _normalize(case: GeneratedCase) -> dict[str, Any]:
    """把模型输出整理成执行器能直接消费的结构。"""
    path = case.path.strip()
    if path and not path.startswith("/"):
        path = "/" + path

    return {
        "name": case.name,
        "category": case.category,
        "method": case.method.upper(),
        "path": path,
        "headers": dict(case.headers or {}),
        "params": dict(case.params or {}),
        "body": case.body,
        "expected_status": int(case.expected_status),
        "assertions": [a.model_dump() for a in case.assertions],
        "rationale": case.rationale,
        "source": "ai",
    }


def _mock_output(spec: dict[str, Any]) -> CaseGenOutput:
    """无 API Key 时的确定性桩：按接口清单生成正向/边界/异常用例。

    它同时也是「图能跑通」的证明——不依赖任何外部服务。
    """
    cases: list[GeneratedCase] = []
    paths = spec.get("paths") or {}

    for path, ops in paths.items():
        if not isinstance(ops, dict):
            continue
        for method, op in ops.items():
            if method.lower() not in _METHODS or not isinstance(op, dict):
                continue

            cases.append(
                GeneratedCase(
                    name=f"{method.upper()} {path} 正常路径",
                    category="happy",
                    method=method.upper(),
                    path=path,
                    expected_status=200 if method.lower() != "post" else 201,
                    assertions=[],
                    rationale="冒烟：验证接口在合法输入下可用",
                )
            )

            if method.lower() in {"post", "put", "patch"}:
                cases.append(
                    GeneratedCase(
                        name=f"{method.upper()} {path} 缺少必填字段",
                        category="negative",
                        method=method.upper(),
                        path=path,
                        body={},
                        expected_status=422,
                        rationale="异常：空 body 应被参数校验拒绝",
                    )
                )

            if method.lower() == "get":
                cases.append(
                    GeneratedCase(
                        name=f"GET {path} 不存在的资源",
                        category="boundary",
                        method="GET",
                        path=path,
                        params={"id": "0"},
                        expected_status=404,
                        rationale="边界：ID 取最小值应返回未找到",
                    )
                )

            if len(cases) >= settings.max_cases_per_run:
                break
        if len(cases) >= settings.max_cases_per_run:
            break

    return CaseGenOutput(cases=cases, notes="mock 桩数据：未调用真实模型")
