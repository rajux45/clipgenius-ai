"""Celery worker entry point. Run with:
    celery -A app.worker.celery_app worker --loglevel=info -Q default
    celery -A app.worker.celery_app beat --loglevel=info
"""
from .tasks import celery_app  # noqa: F401
