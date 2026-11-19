"""Defect Classifier 节点（DA-04）：把分析结论归类成缺陷条目。

模型档位用 small —— 分类是简单任务，没必要花大模型的钱（CO-02）。
"""

import hashlib
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agents.llm import is_mock_mode, structured_invoke
from app.agents.prompts import DEFECT_SYSTEM, build_defect_prompt
from app.agents.schemas import DefectItem, DefectOutput
from app.core.logging import get_logger

logger = get_logger(__name__)


async def defect_classifier(
    state: dict[str, Any], config: RunnableConfig | None = None
) -> dict[str, Any]:
    analysis = state.get("analysis") or {}
    items = analysis.get("items") or []

    if not items:
        return {"defects": []}

    try:
        usage: dict[str, int] = {}
        if is_mock_mode():
            output = _mock_defects(items)
        else:
            output, usage = await structured_invoke(
                DefectOutput,
                [("system", DEFECT_SYSTEM), ("human", build_defect_prompt(analysis))],
                tier="small",
                scope="defect",
            )
    except Exception as exc:
        logger.warning("defect.failed", error=str(exc))
        output = _mock_defects(items)
        return {
            "defects": [_with_fingerprint(d) for d in output.defects],
            "errors": [f"缺陷分类失败，已退化为启发式归类: {exc}"],
        }

    return {"defects": [_with_fingerprint(d) for d in output.defects], "token_usage": usage}


def _with_fingerprint(item: DefectItem) -> dict[str, Any]:
    """DA-05 预留：同一条用例 + 同一类问题的稳定指纹，用来做重复缺陷检测。"""
    payload = f"{item.case_name}|{item.category}|{item.title}".encode()
    data = item.model_dump()
    data["fingerprint"] = hashlib.sha1(payload).hexdigest()[:16]
    return data


def _mock_defects(items: list[dict[str, Any]]) -> DefectOutput:
    defects: list[DefectItem] = []
    for item in items:
        root_cause = str(item.get("root_cause") or "")
        reason = str(item.get("failure_reason") or "")
        severity = str(item.get("severity") or "major")

        category = "functional"
        merged = f"{root_cause}{reason}"
        if any(k in merged for k in ("超时", "timeout", "慢", "性能")):
            category = "performance"
        elif any(k in merged for k in ("鉴权", "越权", "泄露", "注入", "security")):
            category = "security"

        defects.append(
            DefectItem(
                case_name=item.get("case_name") or "未命名用例",
                title=f"{item.get('case_name') or '用例'} 执行未达预期",
                description=reason or "执行结果与期望不一致",
                category=category,  # type: ignore[arg-type]
                severity=severity if severity in {"blocker", "critical", "major", "minor"} else "major",  # type: ignore[arg-type]
            )
        )
    return DefectOutput(defects=defects)
