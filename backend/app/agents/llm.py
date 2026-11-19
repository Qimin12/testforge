"""LLM 工厂：一套代码切硅基流动 / DeepSeek / 通义千问。

关键点：**所有供应商都走 OpenAI 兼容协议**，所以只需要改
``LLM_BASE_URL`` / ``LLM_API_KEY`` / ``LLM_MODEL_*``，不用换适配器。
"""

from __future__ import annotations

from typing import Any, Literal, TypeVar

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

TierName = Literal["large", "small"]
SchemaT = TypeVar("SchemaT", bound=BaseModel)


def is_mock_mode() -> bool:
    """没配置 Key 时自动降级为桩模式，避免一启动就炸。"""
    return settings.llm_mock or not settings.llm_api_key


def resolve_model_name(tier: TierName = "large") -> str:
    return settings.llm_model_large if tier == "large" else settings.llm_model_small


def get_chat_model(tier: TierName = "large") -> BaseChatModel:
    """按档位取模型（CO-02 模型分级：简单任务走 small，贵的走 large）。"""
    if is_mock_mode():
        # 桩模型只为让 import / 编译通过，节点在 mock 模式下不会真正调用它
        from langchain_core.language_models.fake_chat_models import FakeListChatModel

        return FakeListChatModel(responses=["{}"])

    from langchain_openai import ChatOpenAI

    model = resolve_model_name(tier)
    logger.debug("llm.client.created", provider=settings.llm_provider, model=model, tier=tier)
    return ChatOpenAI(
        model=model,
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )


def structured_model(schema: type[SchemaT], tier: TierName = "large", *, include_raw: bool = False):
    """返回一个「输入 messages → 输出 schema 实例」的 Runnable。

    仅在非 mock 模式下使用；mock 模式请直接走各节点的确定性桩。
    ``include_raw=True`` 时返回 ``{"raw": AIMessage, "parsed": ..., "parsing_error": ...}``，
    这样可以顺带拿到 token 用量（CO-01）。
    """
    return get_chat_model(tier).with_structured_output(schema, include_raw=include_raw)


def extract_usage(message: Any, scope: str) -> dict[str, int]:
    """从 AIMessage 的 usage_metadata 里抽 token 用量，键名带上节点前缀。"""
    meta = getattr(message, "usage_metadata", None) or {}
    usage: dict[str, int] = {}
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        value = meta.get(key)
        if isinstance(value, int) and value > 0:
            usage[f"{scope}.{key}"] = value
    return usage


async def structured_invoke(
    schema: type[SchemaT],
    messages: Any,
    *,
    tier: TierName = "large",
    scope: str,
) -> tuple[SchemaT, dict[str, int]]:
    """调用模型并解析结构化输出，同时返回 token 用量。

    返回 ``(解析后的模型对象, {"<scope>.total_tokens": n, ...})``。
    解析失败会抛 ``ValueError``，由调用方决定是否降级。
    """
    runner = structured_model(schema, tier, include_raw=True)
    result = await runner.ainvoke(messages)

    parsed = result.get("parsed") if isinstance(result, dict) else result
    if parsed is None:
        error = result.get("parsing_error") if isinstance(result, dict) else None
        raise ValueError(f"模型结构化输出解析失败: {error}")

    raw = result.get("raw") if isinstance(result, dict) else None
    return parsed, extract_usage(raw, scope)
