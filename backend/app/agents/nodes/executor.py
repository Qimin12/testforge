"""Executor 节点（TE-01 / TE-03）：真实发 HTTP 请求并判定结果。

设计要点：
* 用 ``httpx.AsyncClient``，可在测试里注入 ``MockTransport`` 走本地假服务，
  完全不需要联网；
* 单个用例失败不影响其它用例（异常被收敛成 ``error`` 结果）。
"""

import asyncio
import time
from typing import Any

import httpx
from langchain_core.runnables import RunnableConfig

from app.agents.state import is_failed_result
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# 测试注入点：设为 httpx.MockTransport(...) 即可脱离网络
_http_transport: httpx.AsyncBaseTransport | None = None

MAX_BODY_CHARS = 4000


def set_http_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    """注入自定义 transport（测试用）。传 None 恢复真实网络。"""
    global _http_transport
    _http_transport = transport


def build_client(base_url: str = "") -> httpx.AsyncClient:
    kwargs: dict[str, Any] = {
        "timeout": httpx.Timeout(settings.http_timeout_seconds),
        "follow_redirects": True,
        "transport": _http_transport,
    }
    if base_url:
        kwargs["base_url"] = base_url
    return httpx.AsyncClient(**kwargs)


async def executor(
    state: dict[str, Any], config: RunnableConfig | None = None
) -> dict[str, Any]:
    cases = state.get("cases") or []
    base_url = state.get("target_base_url") or ""

    if not cases:
        return {"results": [], "errors": ["没有可执行的用例"]}

    selected = cases[: settings.max_cases_per_run]
    concurrency = max(1, settings.executor_concurrency)
    semaphore = asyncio.Semaphore(concurrency)

    async with build_client(base_url) as client:

        async def run_one(case: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                try:
                    return await run_case(client, case)
                except Exception as exc:  # 兜底：单条用例的意外不能中断整批
                    logger.warning("executor.case_crashed", case=case.get("name"), error=str(exc))
                    return {
                        "case_id": case.get("id"),
                        "case_name": case.get("name") or "未命名用例",
                        "category": case.get("category"),
                        "status": "error",
                        "expected": f"HTTP {case.get('expected_status', 200)}",
                        "actual": type(exc).__name__,
                        "error": str(exc),
                        "duration_ms": 0,
                        "assertions": [],
                        "request": {
                            "method": (case.get("method") or "GET").upper(),
                            "path": case.get("path") or "/",
                        },
                    }

        results = await asyncio.gather(*(run_one(case) for case in selected))

    failed = sum(1 for r in results if is_failed_result(r))
    logger.info(
        "executor.done", total=len(results), failed=failed, concurrency=concurrency
    )
    return {"results": list(results)}


async def run_case(client: httpx.AsyncClient, case: dict[str, Any]) -> dict[str, Any]:
    """执行单条用例，返回结果字典（不抛异常）。"""
    name = case.get("name") or "未命名用例"
    method = (case.get("method") or "GET").upper()
    path = case.get("path") or "/"
    expected_status = int(case.get("expected_status") or 200)
    assertions = case.get("assertions") or []
    params = dict(case.get("params") or {})
    path = _resolve_path_params(path, params)

    started = time.perf_counter()
    try:
        response = await client.request(
            method,
            path,
            headers=case.get("headers") or None,
            params=params or None,
            json=case.get("body"),
        )
    except httpx.HTTPError as exc:
        duration = int((time.perf_counter() - started) * 1000)
        return {
            "case_id": case.get("id"),
            "case_name": name,
            "category": case.get("category"),
            "status": "error",
            "expected": f"HTTP {expected_status}",
            "actual": type(exc).__name__,
            "error": str(exc),
            "duration_ms": duration,
            "assertions": [],
            "request": {"method": method, "path": path},
        }

    duration = int((time.perf_counter() - started) * 1000)
    body_text = response.text or ""

    checks: list[dict[str, Any]] = [
        {
            "mode": "status_code",
            "target": "",
            "expected": expected_status,
            "actual": response.status_code,
            "passed": response.status_code == expected_status,
        }
    ]
    for assertion in assertions:
        checks.append(_check_assertion(assertion, response))

    passed = all(c["passed"] for c in checks)
    failure = next((c for c in checks if not c["passed"]), None)

    return {
        "case_id": case.get("id"),
        "case_name": name,
        "category": case.get("category"),
        "status": "passed" if passed else "failed",
        "expected": _describe(failure["expected"]) if failure else f"HTTP {expected_status}",
        "actual": _describe(failure["actual"]) if failure else f"HTTP {response.status_code}",
        "error": None if passed else _describe_failure(failure),
        "duration_ms": duration,
        "assertions": checks,
        "request": {"method": method, "path": path},
        "response": {
            "status": response.status_code,
            "body": body_text[:MAX_BODY_CHARS],
        },
    }


def _resolve_path_params(path: str, params: dict[str, Any]) -> str:
    """把 path 里的 {param} 占位符替换为 params 中同名参数的值。

    AI 生成的用例常写成 path="/users/{user_id}" + params={"user_id": 1}，
    若不替换直接请求，会命中字面量路径 /users/{user_id} 导致 422。
    已被替换的键从 params 中移除，剩余键继续作为 query 参数传递。
    """
    import re

    resolved = path
    for name in re.findall(r"\{(\w+)\}", path):
        value = params.get(name)
        if value is None:
            continue
        resolved = resolved.replace("{" + name + "}", str(value))
        params.pop(name, None)
    return resolved


def _check_assertion(assertion: dict[str, Any], response: httpx.Response) -> dict[str, Any]:
    mode = assertion.get("mode") or "status_code"
    target = assertion.get("target") or ""
    expected = assertion.get("expected")
    actual: Any = None
    passed = False

    try:
        if mode == "status_code":
            actual = response.status_code
            passed = _loose_equal(actual, expected)
        elif mode == "json_path":
            value = _resolve_json_path(response.json(), target)
            actual = value
            passed = _loose_equal(value, expected) or _type_equal(value, expected)
        elif mode == "header":
            actual = response.headers.get(target)
            passed = _loose_equal(actual, expected)
        elif mode == "contains":
            actual = expected in (response.text or "")
            passed = bool(actual)
            expected, actual = f"包含 {expected}", actual
        else:
            actual = f"未知断言类型 {mode}"
            passed = False
    except Exception as exc:  # JSON 解析失败等
        actual = f"{type(exc).__name__}: {exc}"
        passed = False

    return {
        "mode": mode,
        "target": target,
        "expected": expected,
        "actual": actual,
        "passed": passed,
    }


def _resolve_json_path(data: Any, path: str) -> Any:
    """支持 ``data.items.0.id`` 点号路径，也兼容 ``$.detail`` 这类 JSONPath 写法。"""
    if not path:
        return data
    clean = path.strip()
    if clean.startswith("$"):
        clean = clean[1:].lstrip(".")
    if not clean:
        return data
    current = data
    for part in clean.split("."):
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            raise KeyError(f"路径 {path} 在 {part} 处无法继续")
    return current


def _type_equal(actual: Any, expected: Any) -> bool:
    """支持断言期望为 "object"/"integer" 这类类型名时的类型比对。"""
    if not isinstance(expected, str):
        return False
    name = expected.strip().lower()
    types: dict[str, type | tuple[type, ...]] = {
        "object": dict,
        "array": list,
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "null": type(None),
        "any": object,
    }
    typ = types.get(name)
    if typ is None:
        return False
    return isinstance(actual, typ)


def _loose_equal(actual: Any, expected: Any) -> bool:
    """容忍 ``"200"`` 与 ``200`` 这类类型差异，但不做模糊匹配。"""
    if actual == expected:
        return True
    try:
        return str(actual) == str(expected)
    except Exception:
        return False


def _describe(value: Any) -> str:
    text = str(value)
    return text[:500] + "…" if len(text) > 500 else text


def _describe_failure(check: dict[str, Any] | None) -> str:
    if not check:
        return "断言失败"
    return (
        f"{check['mode']}({check['target']}) 期望 {_describe(check['expected'])}，"
        f"实际 {_describe(check['actual'])}"
    )