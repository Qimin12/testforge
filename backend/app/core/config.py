"""应用配置：所有环境相关的值都在这里，代码中不得出现字面量地址。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# app/core/config.py -> parents[0]=core, [1]=app, [2]=backend
BACKEND_DIR = Path(__file__).resolve().parents[2]


def normalize_async_dsn(url: str) -> str:
    """把用户手写的 DSN 规范成 SQLAlchemy 异步驱动格式。

    允许用户写 ``postgresql://`` 或 ``sqlite://``（更符合直觉），
    由这里补上驱动名，避免“配置写对了却连不上”的常见事故。
    """
    url = url.strip()
    if url.startswith("postgresql+asyncpg://") or url.startswith("sqlite+aiosqlite://"):
        return url
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("sqlite://"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return url


def normalize_sync_dsn(url: str) -> str:
    """LangGraph 的 PostgresSaver 走 psycopg，需要同步 DSN 且不能带异步驱动名。"""
    url = url.strip()
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------- 应用 ----------
    app_name: str = "TestForge"
    app_env: Literal["dev", "test", "prod"] = "dev"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # ---------- 认证 ----------
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    max_login_failures: int = 5
    lockout_minutes: int = 15

    # ---------- 关系库 ----------
    database_url: str = "sqlite+aiosqlite:///./testforge.db"
    db_echo: bool = False
    auto_create_tables: bool = True

    # ---------- Redis / Celery ----------
    redis_url: str = "redis://127.0.0.1:6379/0"
    celery_broker_url: str = "redis://127.0.0.1:6379/1"
    celery_result_backend: str = "redis://127.0.0.1:6379/2"
    celery_eager: bool = True

    # ---------- LangGraph ----------
    langgraph_checkpointer: Literal["memory", "sqlite", "postgres"] = "sqlite"
    checkpoint_sqlite_path: str = "./testforge_checkpoints.db"
    checkpoint_db_url: str = ""

    # ---------- LLM ----------
    llm_provider: str = "siliconflow"
    llm_base_url: str = "https://api.siliconflow.cn/v1"
    llm_api_key: str = ""
    llm_model_large: str = "deepseek-ai/DeepSeek-V3"
    llm_model_small: str = "Qwen/Qwen2.5-7B-Instruct"
    llm_temperature: float = 0.2
    llm_timeout_seconds: int = 120
    llm_mock: bool = False
    llm_max_retries: int = 2

    # ---------- 图行为 ----------
    require_review: bool = False
    max_cases_per_run: int = 50
    http_timeout_seconds: float = 15.0
    # TE-03 并行执行：同时发出的请求数上限（防止把被测服务打挂）
    executor_concurrency: int = 5

    # ---------- 成本 ----------
    token_budget_monthly: int = 5_000_000
    llm_rate_limit_per_project: int = 10

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        """允许 ``CORS_ORIGINS=a,b`` 这种逗号分隔写法。"""
        if isinstance(v, str) and not v.strip().startswith("["):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @property
    def sqlalchemy_url(self) -> str:
        return normalize_async_dsn(self.database_url)

    @property
    def is_sqlite(self) -> bool:
        return self.sqlalchemy_url.startswith("sqlite")

    @property
    def sync_dsn(self) -> str:
        return normalize_sync_dsn(self.checkpoint_db_url or self.database_url)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
