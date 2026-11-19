"""Celery 应用（配置全部来自 .env，不硬编码 broker 地址）。

启动 worker：
    celery -A app.workers.celery_app worker -l info -P solo    # Windows 用 solo
    celery -A app.workers.celery_app beat -l info              # 定时调度

开发期 ``CELERY_EAGER=true`` 时任务不经过 broker，直接在调用方同步执行，
所以不启动 Redis 也能跑通（但定时调度需要真正的 worker 才有意义）。
"""

from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery("testforge")

celery_app.conf.update(
    broker_url=settings.celery_broker_url,
    result_backend=settings.celery_result_backend,
    task_always_eager=settings.celery_eager,
    task_eager_propagates=False,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    worker_hijack_root_logger=False,
    # TE-04：每分钟扫描一次「到点该跑的定时项目」
    beat_schedule={
        "testforge-scan-schedules": {
            "task": "testforge.scan_schedules",
            "schedule": 60.0,
        },
    },
)

celery_app.autodiscover_tasks(["app.workers"])

__all__ = ["celery_app"]
