"""
Celery tasks for background processing.
"""

# Import tasks to register with Celery
from app.tasks.extraction import extract_images_from_report  # noqa: F401
from app.tasks.metric_generation import generate_metrics_from_document  # noqa: F401
from app.tasks.embedding import index_metric_task, index_all_metrics_task  # noqa: F401

__all__ = [
    "extract_images_from_report",
    "generate_metrics_from_document",
    "index_metric_task",
    "index_all_metrics_task",
]
