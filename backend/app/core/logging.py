"""结构化日志（PRD §8.5：JSON 格式）。

开发期输出带颜色的可读行，生产期输出 JSON 供采集。
"""

from __future__ import annotations

import logging
import sys

import structlog

from app.core.config import settings


def configure_logging(level: int | None = None) -> None:
    """配置 stdlib logging 与 structlog 的桥接，可重复调用。"""
    log_level = level or (logging.DEBUG if settings.debug else logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
        force=True,
    )

    # 这些库在 DEBUG 下噪音极大
    for noisy in ("httpx", "httpcore", "openai", "asyncio", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.app_env == "prod":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name or "testforge")
