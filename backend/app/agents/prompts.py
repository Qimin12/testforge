"""提示词。集中放在这里，方便调优和做 A/B，不散落在节点里。

PRD §10.3 有「单次分析最大 10000 行代码 / 片段长度限制」的要求，
所以这里的拼装函数都会做截断。
"""

from __future__ import annotations

import json
from typing import Any

# 单次塞进 prompt 的 OpenAPI 文本上限（字符数，粗估 token）
MAX_SPEC_CHARS = 24_000
MAX_RESULT_TEXT = 2_000

CASE_GEN_SYSTEM = """你是一名资深 API 测试工程师。
任务：根据给定的 OpenAPI/Swagger 文档设计可执行的 API 测试用例。

要求：
1. 每个接口至少覆盖三类：happy（正常路径）、boundary（边界值：空串、0、超长、最大/最小值）、
   negative（异常：缺少必填字段、类型错误、非法 ID、未授权）。
2. 断言必须具体：优先断言状态码，其次断言关键 JSON 字段。
3. path 只写相对路径，不要域名；路径参数保留 {name} 形式，并在 params 里给出具体值。
4. 不臆造文档里不存在的接口或字段。
5. 输出严格遵循给定的结构化 schema。
"""

ANALYZER_SYSTEM = """你是一名测试失败分析专家。
任务：判断每条失败用例的失败原因属于哪一类，并给出根因与修复方向。

分类口径：
- request_error：用例本身请求构造有问题（路径错、缺鉴权头、参数类型错）
- assertion_error：期望值与实际不符，可能断言写错，也可能是被测服务返回变了
- service_error：被测服务 5xx / 超时 / 连接失败
- data_error：测试数据不满足前置条件（如依赖的资源不存在）

要求：结论要有依据，不确定时调低 confidence，不要编造不存在的日志。
"""

DEFECT_SYSTEM = """你是一名缺陷管理专家。
任务：把失败分析结论归类成缺陷条目。

要求：
1. category 只能是 functional / performance / security。
2. 只有明显属于性能（超时、慢响应）或安全（越权、信息泄露、注入）时才归入对应类别，
   其余一律 functional。
3. 同一条失败用例只产生一条缺陷，不要重复。
4. title 要能直接作为缺陷单标题。
"""

REPORT_SYSTEM = """你是一名测试报告撰写人。
任务：基于本次执行的统计数据和缺陷列表，写一段面向研发负责人的结论。

要求：
1. 先给结论（能否发布/是否阻阻塞），再给依据。
2. 不夸大风险，也不隐瞒失败。
3. 3 句话以内说明风险等级判定理由。
"""


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[已截断，原文 {len(text)} 字符]"


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


def build_case_gen_prompt(api_spec: dict[str, Any], target_base_url: str = "") -> str:
    """把 OpenAPI 文档压成一份可读摘要喂给模型。"""
    paths = api_spec.get("paths") or {}
    info = api_spec.get("info") or {}

    lines = [
        f"API 标题: {info.get('title', '未命名')}",
        f"版本: {info.get('version', '未知')}",
        f"服务地址: {target_base_url or '未提供'}",
        "",
        f"接口总数: {len(paths)}",
        "",
        "接口清单：",
    ]
    for path, ops in paths.items():
        if not isinstance(ops, dict):
            continue
        for method, op in ops.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                continue
            if not isinstance(op, dict):
                continue
            summary = op.get("summary") or op.get("operationId") or ""
            lines.append(f"- {method.upper()} {path}  {summary}")

    raw = _dumps(api_spec)
    if len(raw) > MAX_SPEC_CHARS:
        lines.append("")
        lines.append("完整 schema（已截断）：")
        lines.append(_truncate(raw, MAX_SPEC_CHARS))
    else:
        lines.append("")
        lines.append("完整文档：")
        lines.append(raw)

    # max_cases 由调用方通过 settings 控制，这里只给一个上限提示
    lines.append("")
    lines.append("请设计覆盖上述接口的测试用例。")
    return "\n".join(lines)


def build_analyzer_prompt(failed_results: list[dict[str, Any]]) -> str:
    payload = []
    for item in failed_results:
        payload.append(
            {
                "case_name": item.get("case_name"),
                "status": item.get("status"),
                "expected": _truncate(str(item.get("expected", "")), MAX_RESULT_TEXT),
                "actual": _truncate(str(item.get("actual", "")), MAX_RESULT_TEXT),
                "error": _truncate(str(item.get("error") or ""), MAX_RESULT_TEXT),
                "duration_ms": item.get("duration_ms"),
            }
        )
    return "以下用例执行失败，请逐条分析：\n" + _dumps(payload)


def build_defect_prompt(analysis: dict[str, Any]) -> str:
    return "基于以下失败分析结论，输出缺陷条目：\n" + _dumps(analysis)


def build_report_prompt(stats: dict[str, Any], defects: list[dict[str, Any]]) -> str:
    payload = {"stats": stats, "defects": defects}
    return "请为本次测试执行撰写结论：\n" + _truncate(_dumps(payload), MAX_SPEC_CHARS)
