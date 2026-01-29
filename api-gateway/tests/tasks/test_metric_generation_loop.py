# tests/tasks/test_metric_generation_loop.py
"""Test that metric_generation task uses Celery-safe patterns."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


def test_metric_generation_imports_celery_session():
    """Test that task imports get_celery_session_factory, not AsyncSessionLocal."""
    import app.tasks.metric_generation as module

    # Should have get_celery_session_factory imported
    assert hasattr(module, 'get_celery_session_factory'), (
        "metric_generation.py must import get_celery_session_factory from app.db.celery_session"
    )


def test_metric_generation_uses_async_to_sync():
    """Test that task uses async_to_sync instead of manual loop management."""
    import app.tasks.metric_generation as module

    # Should have async_to_sync imported
    assert hasattr(module, 'async_to_sync'), (
        "metric_generation.py must import async_to_sync from asgiref.sync"
    )


def test_generate_metrics_task_uses_async_to_sync_in_code():
    """Test that the Celery task code uses async_to_sync pattern."""
    import inspect
    from app.tasks.metric_generation import generate_metrics_from_document

    # Get the source code of the task function
    source = inspect.getsource(generate_metrics_from_document)

    # Verify async_to_sync is used in the implementation
    assert 'async_to_sync' in source, (
        "generate_metrics_from_document must use async_to_sync to call async function"
    )

    # Verify no manual event loop creation
    assert 'asyncio.new_event_loop' not in source, (
        "generate_metrics_from_document should not use asyncio.new_event_loop"
    )
    assert 'loop.run_until_complete' not in source, (
        "generate_metrics_from_document should not use loop.run_until_complete"
    )
