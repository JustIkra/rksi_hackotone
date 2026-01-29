# tests/tasks/test_metric_generation_integration.py
"""
Integration test for metric generation task event loop handling.

Tests that running multiple tasks sequentially doesn't cause
"Future attached to a different loop" errors.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import base64


def test_multiple_task_runs_no_loop_error():
    """
    Test that running the task multiple times doesn't cause event loop conflicts.

    This simulates what happens when Celery runs multiple tasks in the same worker.
    """
    from app.tasks.metric_generation import generate_metrics_from_document

    # Mock the async processing to avoid actual API calls
    mock_result = {"metrics_created": 5, "metrics_matched": 3}

    with patch('app.tasks.metric_generation._process_document_async', new_callable=AsyncMock) as mock_async:
        mock_async.return_value = mock_result

        with patch('app.tasks.metric_generation.get_redis_client', return_value=None):
            file_data = base64.b64encode(b"test pdf content").decode()

            # Run task multiple times - this should NOT raise event loop errors
            for i in range(3):
                # Use Celery's push_request to set up proper request context
                generate_metrics_from_document.push_request(id=f"task-{i}")
                try:
                    # Call the task's run method directly (bypasses Celery machinery)
                    result = generate_metrics_from_document.run(file_data, f"test_{i}.pdf")
                    assert result == mock_result
                finally:
                    generate_metrics_from_document.pop_request()

    # If we got here without "Future attached to different loop" error, test passes
    assert mock_async.call_count == 3
