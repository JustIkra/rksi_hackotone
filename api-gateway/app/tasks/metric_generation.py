"""
Celery task for AI-powered metric generation from PDF/DOCX reports.

Handles asynchronous processing of documents with progress tracking.
"""

from __future__ import annotations

import asyncio
import logging

from redis import Redis

from app.core.celery_app import celery_app
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.services.metric_generation import MetricGenerationService

logger = logging.getLogger(__name__)


def get_redis_client() -> Redis | None:
    """Get Redis client for progress tracking."""
    try:
        return Redis.from_url(settings.redis_url, decode_responses=True)
    except Exception as e:
        logger.warning(f"Failed to connect to Redis: {e}")
        return None


@celery_app.task(
    bind=True,
    name="tasks.generate_metrics_from_document",
    max_retries=0,  # No automatic retries - show error to user
    soft_time_limit=600,  # 10 minutes
    time_limit=660,  # Hard limit 11 minutes
)
def generate_metrics_from_document(
    self,
    file_data_b64: str,
    filename: str,
) -> dict:
    """
    Celery task to generate metrics from uploaded document.

    Args:
        file_data_b64: Base64-encoded file content
        filename: Original filename

    Returns:
        Result summary with created/matched metrics
    """
    import base64

    task_id = self.request.id
    logger.info(f"Starting metric generation task {task_id} for {filename}")

    # Decode file data
    file_data = base64.b64decode(file_data_b64)

    # Run async processing
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(
            _process_document_async(task_id, file_data, filename)
        )
        return result
    except Exception as e:
        logger.exception(f"Metric generation task {task_id} failed: {e}")
        # Update progress with error
        redis = get_redis_client()
        if redis:
            import json
            redis.setex(
                f"metric_gen:{task_id}",
                3600,
                json.dumps({
                    "status": "failed",
                    "progress": 0,
                    "error": str(e),
                }),
            )
        raise
    finally:
        loop.close()


async def _process_document_async(
    task_id: str,
    file_data: bytes,
    filename: str,
) -> dict:
    """Async wrapper for document processing."""
    redis = get_redis_client()

    async with AsyncSessionLocal() as db:
        service = MetricGenerationService(db=db, redis=redis)
        try:
            result = await service.process_document(task_id, file_data, filename)
            return result
        finally:
            await service.close()


@celery_app.task(
    name="tasks.get_metric_generation_status",
)
def get_metric_generation_status(task_id: str) -> dict:
    """
    Get status of metric generation task.

    Args:
        task_id: Celery task ID

    Returns:
        Task status with progress
    """
    import json

    redis = get_redis_client()
    if not redis:
        return {"status": "unknown", "error": "Redis unavailable"}

    data = redis.get(f"metric_gen:{task_id}")
    if data:
        return json.loads(data)

    # Check Celery task state
    result = celery_app.AsyncResult(task_id)
    if result.state == "PENDING":
        return {"status": "pending", "progress": 0}
    elif result.state == "STARTED":
        return {"status": "processing", "progress": 0}
    elif result.state == "SUCCESS":
        return {"status": "completed", "progress": 100, "result": result.result}
    elif result.state == "FAILURE":
        return {"status": "failed", "error": str(result.result)}
    else:
        return {"status": result.state.lower(), "progress": 0}
