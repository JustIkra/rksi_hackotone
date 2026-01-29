"""
Celery tasks for PDF-based report extraction.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import selectinload, sessionmaker

from app.core.celery_app import celery_app
from app.core.config import Settings
from app.core.logging import log_context
from app.db.models import Report
from app.services.docx_to_pdf import convert_docx_bytes_to_pdf_bytes
from app.services.storage import LocalReportStorage

logger = logging.getLogger(__name__)

settings = Settings()


def _build_extract_warning(
    unknown_labels: list[str],
    ambiguous: list[dict],
) -> tuple[str | None, dict | None]:
    """
    Build warning message and details for unmapped metrics.

    Args:
        unknown_labels: Labels that couldn't be mapped to any metric
        ambiguous: List of dicts with 'label' and 'candidates' for ambiguous mappings

    Returns:
        Tuple of (warning_message, warning_details) or (None, None) if no issues
    """
    if not unknown_labels and not ambiguous:
        return None, None

    parts = []
    details: dict = {}

    if unknown_labels:
        parts.append(f"Не удалось сопоставить {len(unknown_labels)} метрик")
        details["unknown_count"] = len(unknown_labels)
        details["unknown_labels"] = unknown_labels[:10]  # Limit to first 10

    if ambiguous:
        parts.append(f"Неоднозначное сопоставление для {len(ambiguous)} метрик")
        details["ambiguous_count"] = len(ambiguous)
        details["ambiguous"] = [
            {"label": a["label"], "candidates": [c.get("code") for c in a.get("candidates", [])[:3]]}
            for a in ambiguous[:10]  # Limit to first 10
        ]

    message = ". ".join(parts) + ". Пожалуйста, сообщите администрации."
    return message, details

# Background loop for nested execution (tests running inside existing loop)
_TASK_LOOP: asyncio.AbstractEventLoop | None = None
_TASK_LOOP_THREAD: threading.Thread | None = None
_TASK_LOOP_LOCK = threading.Lock()


def _start_background_loop(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    loop.run_forever()


def _get_background_loop() -> asyncio.AbstractEventLoop:
    global _TASK_LOOP, _TASK_LOOP_THREAD
    if _TASK_LOOP and _TASK_LOOP.is_running():
        return _TASK_LOOP

    with _TASK_LOOP_LOCK:
        if _TASK_LOOP and _TASK_LOOP.is_running():
            return _TASK_LOOP

        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=_start_background_loop, args=(loop,), daemon=True)
        thread.start()
        _TASK_LOOP = loop
        _TASK_LOOP_THREAD = thread
        return loop


def _run_coroutine_blocking(coro: Coroutine[Any, Any, Any]) -> Any:
    """
    Run coroutine even if current thread already has a running event loop.

    When pytest runs async tests, there's already an event loop in the main thread,
    so we execute the coroutine inside a background thread with its own loop while
    preserving context variables for structured logging.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    loop = _get_background_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()


@celery_app.task(
    name="app.tasks.extraction.extract_metrics_from_report_pdf",
    bind=True,
    max_retries=3,
)
def extract_metrics_from_report_pdf(self, report_id: str, request_id: str | None = None) -> dict:
    """
    Extract metrics from a DOCX report using PDF-based LLM extraction.

    This task:
    1. Loads the report from database
    2. Reads DOCX file from storage
    3. Converts DOCX to PDF using LibreOffice
    4. Sends PDF to LLM for metric extraction
    5. Saves extracted metrics to database
    6. Updates report status to EXTRACTED or FAILED
    """

    async def _async_extract() -> dict:
        from app.core.ai_factory import create_ai_client
        from app.services.report_pdf_extraction import ReportPdfExtractionService

        async_engine = create_async_engine(
            settings.postgres_dsn,
            echo=False,
            pool_pre_ping=True,
        )
        AsyncSessionLocal = sessionmaker(
            async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        report_uuid = uuid.UUID(report_id)

        logger.info("task_report_lookup", extra={"report_id": report_id})

        ai_client = None
        async with AsyncSessionLocal() as session:
            try:
                # 1. Load report
                stmt = (
                    select(Report)
                    .where(Report.id == report_uuid)
                    .options(selectinload(Report.file_ref))
                )
                result = await session.execute(stmt)
                report = result.scalar_one_or_none()

                if not report:
                    logger.error("task_report_missing", extra={"report_id": report_id})
                    raise ValueError(f"Report {report_id} not found")

                if report.status not in ("UPLOADED", "PROCESSING"):
                    logger.warning(
                        "task_report_skipped",
                        extra={"report_id": report_id, "status": report.status},
                    )
                    return {
                        "status": "skipped",
                        "reason": f"Report status is {report.status}, expected UPLOADED or PROCESSING",
                    }

                # 2. Get file path and read DOCX bytes
                storage = LocalReportStorage(settings.file_storage_base)
                file_path = storage.resolve_path(report.file_ref.key)

                if not file_path.exists():
                    logger.error(
                        "task_report_file_missing",
                        extra={"report_id": report_id, "path": str(file_path)},
                    )
                    raise FileNotFoundError(f"Report file not found: {file_path}")

                docx_bytes = file_path.read_bytes()
                logger.info(
                    "task_report_docx_loaded",
                    extra={"report_id": report_id, "size_bytes": len(docx_bytes)},
                )

                # 3. Convert DOCX to PDF
                pdf_bytes = convert_docx_bytes_to_pdf_bytes(docx_bytes)
                logger.info(
                    "task_report_pdf_converted",
                    extra={"report_id": report_id, "pdf_size_bytes": len(pdf_bytes)},
                )

                # 4. Extract metrics using PDF LLM extraction
                ai_client = create_ai_client()
                extraction_service = ReportPdfExtractionService(session, ai_client)

                metrics_result = await extraction_service.extract_and_save(
                    report_id=report_uuid,
                    participant_id=report.participant_id,
                    pdf_bytes=pdf_bytes,
                )

                logger.info(
                    "task_metrics_extracted",
                    extra={
                        "report_id": report_id,
                        "metrics_extracted": metrics_result.get("metrics_extracted", 0),
                        "metrics_saved": metrics_result.get("metrics_saved", 0),
                        "errors": len(metrics_result.get("errors", [])),
                    },
                )

                # 5. Update report status based on metrics_saved
                metrics_saved = metrics_result.get("metrics_saved", 0)

                # Save warnings (even if extraction succeeded with some metrics)
                extract_warning = metrics_result.get("extract_warning")
                extract_warning_details = metrics_result.get("extract_warning_details")

                if metrics_saved > 0:
                    report.status = "EXTRACTED"
                    report.extracted_at = datetime.now(UTC)
                    report.extract_error = None
                    report.extract_warning = extract_warning
                    report.extract_warning_details = extract_warning_details
                    logger.info(
                        "task_report_status_extracted",
                        extra={
                            "report_id": report_id,
                            "metrics_saved": metrics_saved,
                            "has_warning": extract_warning is not None,
                        },
                    )
                else:
                    report.status = "FAILED"
                    errors = metrics_result.get("errors", [])
                    error_msg = errors[0].get("error", "No metrics found") if errors else "No metrics found"
                    report.extract_error = f"PDF extraction failed: {error_msg}"
                    report.extract_warning = extract_warning
                    report.extract_warning_details = extract_warning_details
                    logger.error(
                        "task_report_status_failed",
                        extra={"report_id": report_id, "error": error_msg},
                    )

                await session.commit()

                return {
                    "status": "success" if metrics_saved > 0 else "failed",
                    "report_id": report_id,
                    "metrics_extracted": metrics_result.get("metrics_extracted", 0),
                    "metrics_saved": metrics_saved,
                    "errors": metrics_result.get("errors", []),
                }

            except RuntimeError as exc:
                # Handle conversion/extraction errors
                logger.error(
                    "task_report_extraction_error",
                    extra={"report_id": report_id, "error": str(exc)},
                    exc_info=True,
                )
                await session.rollback()
                report = await session.get(Report, report_uuid)
                if report:
                    report.status = "FAILED"
                    report.extract_error = f"Extraction error: {str(exc)}"
                    await session.commit()

                return {
                    "status": "failed",
                    "report_id": report_id,
                    "error": str(exc),
                }

            except Exception as exc:
                logger.error(
                    "task_report_unexpected_error",
                    extra={"report_id": report_id, "error": str(exc)},
                    exc_info=True,
                )
                await session.rollback()
                report = await session.get(Report, report_uuid)
                if report:
                    report.status = "FAILED"
                    report.extract_error = f"Unexpected error: {str(exc)}"
                    await session.commit()

                return {
                    "status": "failed",
                    "report_id": report_id,
                    "error": str(exc),
                }

            finally:
                if ai_client:
                    try:
                        await ai_client.close()
                    except Exception as close_exc:
                        logger.warning(
                            "task_ai_client_close_failed",
                            extra={"report_id": report_id, "error": str(close_exc)},
                        )
                await async_engine.dispose()

    task_id = getattr(self.request, "id", None)
    start = time.perf_counter()

    with log_context(request_id=request_id, task_id=task_id):
        logger.info(
            "task_started",
            extra={
                "event": "task_started",
                "task_name": "extract_metrics_from_report_pdf",
                "report_id": report_id,
            },
        )
        try:
            result = _run_coroutine_blocking(_async_extract())
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.exception(
                "task_failed",
                extra={
                    "event": "task_failed",
                    "task_name": "extract_metrics_from_report_pdf",
                    "report_id": report_id,
                    "duration_ms": duration_ms,
                },
            )
            raise

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "task_completed",
            extra={
                "event": "task_completed",
                "task_name": "extract_metrics_from_report_pdf",
                "report_id": report_id,
                "duration_ms": duration_ms,
                "status": result.get("status"),
            },
        )
        return result
