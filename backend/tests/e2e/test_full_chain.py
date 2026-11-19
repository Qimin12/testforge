"""端到端全链路（PRD §14.1 A1~A6 的最小验证）。

一条测试覆盖完整用户旅程：
    注册 → 登录 → 建 API Key → 跑图(生成→执行→分析→缺陷→报告) → 校验产物
"""

from __future__ import annotations

import pytest

BASE = "http://testserver"


@pytest.mark.e2e
def test_full_user_journey(client, api_prefix, user_payload, sample_spec, fake_api) -> None:
    # --- 1. 注册 ---
    registered = client.post(f"{api_prefix}/auth/register", json=user_payload)
    assert registered.status_code == 201

    # --- 2. 登录 ---
    login = client.post(
        f"{api_prefix}/auth/login",
        json={"email": user_payload["email"], "password": user_payload["password"]},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # --- 3. 建 API Key（CI/CD 集成用，CD-01）---
    key = client.post(f"{api_prefix}/auth/api-keys", headers=headers, json={"name": "ci"})
    assert key.status_code == 201
    assert key.json()["full_key"].startswith("tfg_")

    # --- 4. 跑完整图 ---
    run = client.post(
        f"{api_prefix}/graph/run",
        headers=headers,
        json={"mode": "full", "api_spec": sample_spec, "target_base_url": BASE},
    )
    assert run.status_code == 200
    summary = run.json()["summary"]

    # --- 5. 产物校验（A2 用例生成 / A3 执行 / A4 报告 / A6 缺陷分析）---
    assert summary["cases"] > 0, "A2: 应生成用例"
    assert summary["results"] == summary["cases"], "A3: 每条用例都要有结果"
    assert summary["passed"] + summary["failed"] == summary["results"]

    report = summary["report"]
    assert report["total"] == summary["results"]
    assert report["summary"], "A4: 报告必须有结论文字"

    if summary["failed"] > 0:
        assert summary["defects"] > 0, "A6: 有失败就必须有缺陷分析产物"
