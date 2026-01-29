"""
Celery tasks for metric embedding operations.

Provides background tasks for:
- Single metric indexing (triggered on metric create/update)
- Batch reindexing of all metrics
"""

import logging
from uuid import UUID

from asgiref.sync import async_to_sync

from app.core.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _index_metric_async(metric_id: UUID) -> dict:
    """Async helper for indexing a single metric."""
    from app.db.celery_session import get_celery_session_factory
    from app.services.embedding import EmbeddingService

    # Create session factory in current event loop context
    AsyncSessionLocal = get_celery_session_factory()

    async with AsyncSessionLocal() as db:
        service = EmbeddingService(db)
        try:
            await service.index_metric(metric_id)
            await db.commit()
            logger.info(f"Successfully indexed metric {metric_id}")
            return {"status": "success", "metric_id": str(metric_id)}
        except Exception as e:
            logger.error(f"Failed to index metric {metric_id}: {e}")
            return {"status": "error", "metric_id": str(metric_id), "error": str(e)}
        finally:
            await service.close()


async def _index_all_metrics_async() -> dict:
    """Async helper for indexing all metrics."""
    from app.db.celery_session import get_celery_session_factory
    from app.services.embedding import EmbeddingService

    # Create session factory in current event loop context
    AsyncSessionLocal = get_celery_session_factory()

    async with AsyncSessionLocal() as db:
        service = EmbeddingService(db)
        try:
            result = await service.index_all_metrics()
            logger.info(
                f"Completed full reindex: {result['indexed']}/{result['total']} metrics"
            )
            return {
                "status": "success",
                "indexed": result["indexed"],
                "errors": result["errors"],
                "total": result["total"],
            }
        except Exception as e:
            logger.error(f"Failed to index all metrics: {e}")
            return {"status": "error", "error": str(e)}
        finally:
            await service.close()


@celery_app.task(
    name="app.tasks.embedding.index_metric",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 5},
)
def index_metric_task(self, metric_id_str: str) -> dict:
    """
    Celery task for indexing a single metric.

    Used for auto-indexing when a metric is created or updated.
    Can be called directly or as background task.

    Args:
        metric_id_str: UUID string of the metric to index

    Returns:
        Dict with status and metric_id

    Example:
        index_metric_task.delay(str(metric.id))
    """
    metric_id = UUID(metric_id_str)
    # Use async_to_sync to avoid event loop conflicts in Celery workers
    return async_to_sync(_index_metric_async)(metric_id)


@celery_app.task(
    name="app.tasks.embedding.index_all_metrics",
    bind=True,
    time_limit=3600,  # 1 hour timeout for large datasets
)
def index_all_metrics_task(self) -> dict:
    """
    Celery task for full reindex of all APPROVED metrics.

    Use this for:
    - Initial setup
    - After bulk imports
    - Rebuilding index after model change

    Returns:
        Dict with indexed count, errors, and total

    Example:
        index_all_metrics_task.delay()
    """
    # Use async_to_sync to avoid event loop conflicts in Celery workers
    return async_to_sync(_index_all_metrics_async)()
