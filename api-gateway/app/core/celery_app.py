"""
Celery application instance for background tasks.
"""

from celery import Celery

from app.core.config import Settings

settings = Settings()

celery_app = Celery(
    "workers_prof",
    broker=settings.rabbitmq_url,
    backend=settings.redis_url,
    include=["app.tasks.extraction"],
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,  # 10 minutes max per task
    task_soft_time_limit=540,  # 9 minutes soft limit
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    # Task routing
    task_routes={
        "app.tasks.extraction.*": {"queue": "extraction"},
    },
    # For testing
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=settings.celery_eager_propagates_exceptions,
)
