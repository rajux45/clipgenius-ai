from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from ..config import settings

celery_app = Celery(
    "clipgenius",
    broker=settings.broker_url,
    backend=settings.result_backend,
    include=["app.tasks.video_tasks", "app.tasks.posting_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    broker_connection_retry_on_startup=True,
)

celery_app.conf.beat_schedule = {
    "publish-due-posts-every-minute": {
        "task": "app.tasks.posting_tasks.publish_due_posts",
        "schedule": crontab(minute="*"),
    },
    "refresh-analytics-every-30m": {
        "task": "app.tasks.posting_tasks.refresh_analytics",
        "schedule": crontab(minute="*/30"),
    },
}
