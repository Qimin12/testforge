"""报告导出（PRD RP-05）：JSON / Markdown / CSV / XLSX。

PDF 暂不做——生成 PDF 需要 reportlab/weasyprint 之类重依赖，
而 Markdown 已经能直接粘进 Confluence / 飞书，优先级更高。
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Literal

from app.db.models import Execution

ExportFormat = Literal["json", "markdown", "csv", "xlsx"]

CONTENT_TYPES: dict[str, str] = {
    "json": "application/json; charset=utf-8",
    "markdown": "text/markdown; charset=utf-8",
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def build_payload(execution: Execution) -> dict[str, Any]:
    """导出用的一份完整快照（不含 ORM 对象，方便序列化）。"""
    report = execution.report or {}
    return {
        "execution": {
            "id": str(execution.id),
            "project_id": str(execution.project_id),
            "status": execution.status,
            "trigger_type": execution.trigger_type,
            "mode": execution.graph_mode,
            "total_cases": execution.total_cases,
            "passed_cases": execution.passed_cases,
            "failed_cases": execution.failed_cases,
            "pass_rate": round(
                (execution.passed_cases or 0) / execution.total_cases * 100, 2
            )
            if execution.total_cases
            else 0.0,
            "duration_ms": execution.duration_ms,
            "started_at": _iso(execution.started_at),
            "finished_at": _iso(execution.finished_at),
        },
        "report": report,
        "token_usage": execution.token_usage or {},
        "results": [
            {
                "case_name": row.case_name,
                "status": row.status,
                "expected": row.expected_output,
                "actual": row.actual_output,
                "error": row.error_message,
                "duration_ms": row.duration_ms,
            }
            for row in (execution.results or [])
        ],
        "defects": [
            {
                "title": row.title,
                "description": row.description,
                "severity": row.severity,
                "category": row.category,
                "root_cause": row.root_cause,
                "fix_suggestion": row.fix_suggestion,
                "status": row.status,
                "fingerprint": row.fingerprint,
            }
            for row in (execution.defects or [])
        ],
    }


def to_json(execution: Execution) -> str:
    return json.dumps(build_payload(execution), ensure_ascii=False, indent=2, default=str)


def to_markdown(execution: Execution) -> str:
    payload = build_payload(execution)
    meta = payload["execution"]
    report = payload["report"] or {}
    defects = payload["defects"]
    results = payload["results"]

    lines: list[str] = [
        f"# 测试报告 · {meta['id'][:8]}",
        "",
        f"- 状态：**{meta['status']}**",
        f"- 模式：{meta['mode'] or '—'} / 触发：{meta['trigger_type']}",
        f"- 用例：{meta['total_cases']} 条，通过 {meta['passed_cases']}，失败 {meta['failed_cases']}",
        f"- 通过率：{meta['pass_rate']}%",
        f"- 耗时：{meta['duration_ms'] or 0} ms",
        f"- 开始：{meta['started_at'] or '—'}",
        "",
    ]

    if report.get("summary"):
        lines += ["## 结论", "", str(report["summary"]), ""]
    if report.get("risk_level"):
        lines.append(f"风险等级：**{report['risk_level']}**")
    for item in report.get("highlights") or []:
        lines.append(f"- {item}")
    if report:
        lines.append("")

    if defects:
        lines += ["## 缺陷", "", "| 等级 | 分类 | 标题 | 根因 |", "|---|---|---|---|"]
        for item in defects:
            lines.append(
                f"| {item['severity']} | {item['category']} | {_cell(item['title'])} "
                f"| {_cell(item['root_cause'])} |"
            )
        lines.append("")

    if results:
        lines += ["## 用例结果", "", "| 用例 | 状态 | 耗时 | 错误 |", "|---|---|---|---|"]
        for item in results:
            lines.append(
                f"| {_cell(item['case_name'])} | {item['status']} | {item['duration_ms'] or 0} ms "
                f"| {_cell(item['error'])} |"
            )
        lines.append("")

    return "\n".join(lines)


def to_csv(execution: Execution) -> str:
    payload = build_payload(execution)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["用例", "状态", "期望", "实际", "错误", "耗时(ms)"])
    for item in payload["results"]:
        writer.writerow(
            [
                item["case_name"],
                item["status"],
                item["expected"] or "",
                item["actual"] or "",
                item["error"] or "",
                item["duration_ms"] or 0,
            ]
        )
    return buffer.getvalue()


def to_xlsx(execution: Execution) -> bytes:
    """生成两个 sheet：汇总 + 用例结果。依赖 openpyxl。"""
    try:
        from openpyxl import Workbook
    except ImportError as exc:  # pragma: no cover - 依赖缺失
        raise RuntimeError("导出 XLSX 需要 openpyxl，请 pip install openpyxl") from exc

    payload = build_payload(execution)
    meta = payload["execution"]
    report = payload["report"] or {}

    workbook = Workbook()
    summary = workbook.active
    summary.title = "汇总"
    summary.append(["指标", "值"])
    rows: list[tuple[str, Any]] = [
        ("执行 ID", meta["id"]),
        ("状态", meta["status"]),
        ("模式", meta["mode"] or ""),
        ("触发方式", meta["trigger_type"]),
        ("用例总数", meta["total_cases"]),
        ("通过", meta["passed_cases"]),
        ("失败", meta["failed_cases"]),
        ("通过率(%)", meta["pass_rate"]),
        ("耗时(ms)", meta["duration_ms"] or 0),
        ("风险等级", report.get("risk_level", "")),
        ("报告结论", report.get("summary", "")),
    ]
    for key, value in rows:
        summary.append([key, value])
    summary.column_dimensions["A"].width = 16
    summary.column_dimensions["B"].width = 80

    sheet = workbook.create_sheet("用例结果")
    sheet.append(["用例", "状态", "期望", "实际", "错误", "耗时(ms)"])
    for item in payload["results"]:
        sheet.append(
            [
                item["case_name"],
                item["status"],
                item["expected"] or "",
                item["actual"] or "",
                item["error"] or "",
                item["duration_ms"] or 0,
            ]
        )
    sheet.column_dimensions["A"].width = 42
    sheet.column_dimensions["E"].width = 60

    defects_sheet = workbook.create_sheet("缺陷")
    defects_sheet.append(["等级", "分类", "标题", "根因", "修复建议", "状态"])
    for item in payload["defects"]:
        defects_sheet.append(
            [
                item["severity"],
                item["category"],
                item["title"],
                item["root_cause"] or "",
                item["fix_suggestion"] or "",
                item["status"],
            ]
        )

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def render(execution: Execution, fmt: str) -> tuple[bytes, str, str]:
    """返回 ``(内容, content-type, 文件名)``。"""
    stem = f"testforge-{execution.id.hex[:8]}"
    if fmt == "json":
        return to_json(execution).encode(), CONTENT_TYPES["json"], f"{stem}.json"
    if fmt == "markdown":
        return to_markdown(execution).encode(), CONTENT_TYPES["markdown"], f"{stem}.md"
    if fmt == "csv":
        return to_csv(execution).encode(), CONTENT_TYPES["csv"], f"{stem}.csv"
    if fmt == "xlsx":
        return to_xlsx(execution), CONTENT_TYPES["xlsx"], f"{stem}.xlsx"
    raise ValueError(f"不支持的导出格式: {fmt}")


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _cell(value: Any) -> str:
    """把任意值压成一行，避免表格被换行撑坏。"""
    if value is None:
        return ""
    return str(value).replace("\n", " ").replace("|", "\\|")
