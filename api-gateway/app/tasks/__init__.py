"""
Celery tasks for background processing.
"""

# Import tasks to register with Celery
from app.tasks.embedding import index_all_metrics_task, index_metric_task  # noqa: F401
from app.tasks.extraction import extract_metrics_from_report_pdf  # noqa: F401
from app.tasks.metric_generation import generate_metrics_from_document  # noqa: F401

__all__ = [
    "extract_metrics_from_report_pdf",
    "generate_metrics_from_document",
    "index_metric_task",
    "index_all_metrics_task",
]
