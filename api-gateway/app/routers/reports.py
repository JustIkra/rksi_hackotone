"""
Report upload and download endpoints.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.report import (
    ReportListResponse,
    ReportResponse,
    ReportUploadResponse,
)
from app.services.report import ReportService
from app.tasks.extraction import extract_metrics_from_report_pdf

router = APIRouter(tags=["reports"])


@router.get(
    "/participants/{participant_id}/reports",
    response_model=ReportListResponse,
)
async def get_participant_reports(
    participant_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ReportListResponse:
    """
    Get all reports for a participant.

    Returns list of reports with their current status (UPLOADED, EXTRACTED, FAILED).

    Requires active authentication.
    """
    service = ReportService(db)
    reports = await service.get_participant_reports(participant_id)
    items = [ReportResponse.model_validate(r) for r in reports]
    return ReportListResponse(items=items, total=len(items))


@router.post(
    "/participants/{participant_id}/reports",
    response_model=ReportUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_report(
    participant_id: UUID,
    file: UploadFile = File(..., description="DOCX report file"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ReportUploadResponse:
    """
    Upload a DOCX report for a participant.

    Requires active authentication.
    """
    service = ReportService(db)
    return await service.upload_report(participant_id, file)


@router.get("/reports/{report_id}/download")
async def download_report(
    report_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Download original DOCX report.

    Returns 304 when If-None-Match matches stored ETag.
    """
    service = ReportService(db)
    context = await service.get_download_context(report_id)

    if ReportService.matches_etag(request.headers.get("if-none-match"), context.etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)

    headers = {"ETag": ReportService.format_etag(context.etag)}

    return FileResponse(
        path=context.path,
        media_type=context.mime,
        filename=context.filename,
        headers=headers,
    )

@router.delete(
    "/reports/{report_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_report(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Response:
    """
    Delete report with all related data and files.
    Returns 204 No Content on success, 404 if not found.
    """
    service = ReportService(db)
    await service.delete_report(report_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/reports/{report_id}/extract",
    status_code=status.HTTP_202_ACCEPTED,
)
async def extract_report(
    report_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """
    Start extraction of images from a DOCX report.

    Returns immediately with task ID. Extraction happens asynchronously.
    Report status will be updated to EXTRACTED or FAILED when complete.

    Requires active authentication.
    """
    service = ReportService(db)

    # Verify report exists and belongs to accessible participant
    report = await service.get_report_by_id(report_id)

    # Update report status to PROCESSING
    report.status = "PROCESSING"
    await db.commit()

    # Queue extraction task
    request_id = getattr(request.state, "request_id", None)
    task = extract_metrics_from_report_pdf.delay(str(report_id), request_id=request_id)

    return {
        "report_id": str(report_id),
        "task_id": task.id,
        "status": "accepted",
        "message": "Extraction task started",
    }
