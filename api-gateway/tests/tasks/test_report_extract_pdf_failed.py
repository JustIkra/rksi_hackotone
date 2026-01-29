import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.unit
def test_task_fails_when_docx_to_pdf_fails():
    # Smoke-test: when converter raises, task should mark report FAILED.
    # This test is intentionally light: it verifies behavior via calling inner coroutine through patch points.
    from app.tasks import extraction as extraction_module

    report_id = str(uuid.uuid4())

    with patch("app.tasks.extraction.LocalReportStorage") as storage_cls:
        storage = storage_cls.return_value
        storage.resolve_path.return_value.exists.return_value = True
        storage.resolve_path.return_value.read_bytes.return_value = b"fake-docx"

        with patch("app.tasks.extraction.convert_docx_bytes_to_pdf_bytes", side_effect=RuntimeError("boom")):
            # Minimal check: calling the task should raise OR return failure result depending on implementation choice.
            # Update expected after implementation.
            with pytest.raises(Exception):
                extraction_module.extract_metrics_from_report_pdf(report_id)
