"""测试公共夹具。

重要：环境变量必须在 **导入 app 之前** 设置，因为 ``app.core.config`` 在
导入时就会实例化 Settings 并缓存。所以本文件顶部的 os.environ 更新必须先于
任何 ``from app.* import ...``。
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

import httpx
import pytest

# --------------------------------------------------------------------------- #
# 1. 先固定环境（顺序不可调整）
# --------------------------------------------------------------------------- #
_TMP_DIR = Path(tempfile.mkdtemp(prefix="testforge-tests-"))
_TEST_DB = _TMP_DIR / "testforge.db"

# 用内存库而不是文件库：
#   1) 测试之间互不残留；
#   2) 无文件系统权限问题（CI 容器、受限沙箱里都能跑）；
#   3) 内存库 + StaticPool 由 app/db/session.py 自动处理。
# 想用文件库调试时，把这一行换成 f"sqlite+aiosqlite:///{_TEST_DB.as_posix()}" 即可。
_TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

os.environ.update(
    {
        "APP_ENV": "test",
        "DEBUG": "false",
        "SECRET_KEY": "test-secret-key-not-for-production",
        "DATABASE_URL": _TEST_DB_URL,
        "AUTO_CREATE_TABLES": "true",
        "DB_ECHO": "false",
        "LANGGRAPH_CHECKPOINTER": "memory",
        "CHECKPOINT_SQLITE_PATH": (_TMP_DIR / "ckpt.db").as_posix(),
        # 测试永远不开真实模型：既省钱也要确定性
        "LLM_MOCK": "true",
        "LLM_API_KEY": "",
        # 默认不中断，需要测中断的用例自己 monkeypatch
        "REQUIRE_REVIEW": "false",
        "HTTP_TIMEOUT_SECONDS": "5",
    }
)

from app.agents.nodes.executor import set_http_transport  # noqa: E402
from app.core.config import settings  # noqa: E402

# --------------------------------------------------------------------------- #
# 2. 夹具
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def app_module():
    """延迟导入，确保上面的环境变量已经生效。"""
    from app.main import app

    return app


@pytest.fixture()
def client(app_module):
    """同步测试客户端，会触发 lifespan（建表 + 初始化 checkpointer）。

    每个 TestClient 都在自己的事件循环里跑，所以进循环前必须丢掉上一个
    循环创建的引擎与图单例，否则会撞上 “Future attached to a different loop”。
    """
    from fastapi.testclient import TestClient

    from app.agents.graph import reset_graph
    from app.db.session import reset_engine

    reset_engine()
    reset_graph()

    with TestClient(app_module) as test_client:
        yield test_client


@pytest.fixture()
def api_prefix() -> str:
    return settings.api_v1_prefix


@pytest.fixture()
def user_payload() -> dict[str, str]:
    return {
        "email": f"u{uuid.uuid4().hex[:12]}@example.com",
        "password": "Passw0rd!",
        "nickname": "tester",
    }


@pytest.fixture()
def auth_headers(client, api_prefix, user_payload) -> dict[str, str]:
    """注册并登录，返回带 Bearer 的请求头。"""
    reg = client.post(f"{api_prefix}/auth/register", json=user_payload)
    assert reg.status_code == 201, reg.text

    login = client.post(
        f"{api_prefix}/auth/login",
        json={"email": user_payload["email"], "password": user_payload["password"]},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------- #
# 3. 假 API：让执行器测试完全脱离网络
# --------------------------------------------------------------------------- #
def _fake_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    method = request.method.upper()

    if path == "/health":
        return httpx.Response(200, json={"status": "ok"})

    if path == "/users" and method == "GET":
        return httpx.Response(200, json={"items": [{"id": 1, "name": "alice"}]})

    if path == "/users" and method == "POST":
        body = request.content
        if not body or body == b"{}":
            return httpx.Response(422, json={"detail": "name is required"})
        return httpx.Response(201, json={"id": 1, "name": "alice"})

    if path.startswith("/users/"):
        tail = path.rsplit("/", 1)[-1]
        if tail in {"0", "999"}:
            return httpx.Response(404, json={"detail": "not found"})
        return httpx.Response(200, json={"id": int(tail) if tail.isdigit() else 1, "name": "alice"})

    if path == "/boom":
        return httpx.Response(500, json={"detail": "internal error"})

    return httpx.Response(200, json={"ok": True})


@pytest.fixture()
def fake_api():
    """安装假 transport，测试结束后自动摘除。"""
    transport = httpx.MockTransport(_fake_handler)
    set_http_transport(transport)
    yield transport
    set_http_transport(None)


@pytest.fixture()
def sample_spec() -> dict:
    """一份最小可用的 OpenAPI 文档。"""
    return {
        "openapi": "3.0.0",
        "info": {"title": "Demo API", "version": "1.0.0"},
        "paths": {
            "/users": {
                "get": {"summary": "列出用户"},
                "post": {"summary": "创建用户"},
            },
            "/users/{id}": {
                "get": {"summary": "获取用户"},
            },
        },
    }
