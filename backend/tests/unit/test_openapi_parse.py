"""OpenAPI 解析的纯逻辑测试（PM-03）。"""

from __future__ import annotations

import pytest

from app.services.project_service import (
    OpenAPIError,
    extract_operations,
    parse_openapi,
)


@pytest.mark.unit
def test_parse_valid_openapi3(sample_spec: dict) -> None:
    parsed = parse_openapi(sample_spec)
    assert parsed["operation_count"] == 3
    assert parsed["spec"]["openapi"] == "3.0.0"
    methods = {(op["method"], op["path"]) for op in parsed["operations"]}
    assert ("GET", "/users") in methods
    assert ("POST", "/users") in methods
    assert ("GET", "/users/{id}") in methods


@pytest.mark.unit
def test_parse_extracts_server_base_url() -> None:
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "x", "version": "1"},
        "servers": [{"url": "http://api.example.com/v1/"}],
        "paths": {"/a": {"get": {"summary": "a"}}},
    }
    assert parse_openapi(spec)["base_url"] == "http://api.example.com/v1"


@pytest.mark.unit
def test_swagger2_is_coerced(sample_spec: dict) -> None:
    """Swagger 2.0 文档也应能导入（转成 OpenAPI 3 形状）。"""
    swagger = {
        "swagger": "2.0",
        "info": {"title": "legacy", "version": "1.0"},
        "host": "legacy.example.com",
        "basePath": "/api",
        "schemes": ["https"],
        "paths": {"/pets": {"get": {"summary": "list"}}},
    }
    parsed = parse_openapi(swagger)
    assert parsed["spec"]["openapi"] == "3.0.0"
    assert parsed["base_url"] == "https://legacy.example.com/api"
    assert parsed["operation_count"] == 1


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"info": {"title": "x"}},
        {"openapi": "3.0.0", "info": {"title": "x", "version": "1"}, "paths": {}},
    ],
)
def test_parse_rejects_bad_documents(bad: dict) -> None:
    with pytest.raises(OpenAPIError):
        parse_openapi(bad)


@pytest.mark.unit
def test_extract_operations_ignores_non_method_keys() -> None:
    spec = {
        "paths": {
            "/a": {"get": {"summary": "x"}, "parameters": [], "description": "y"},
        }
    }
    ops = extract_operations(spec)
    assert len(ops) == 1
    assert ops[0]["method"] == "GET"
