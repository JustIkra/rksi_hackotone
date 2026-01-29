"""
Service layer for report uploads and downloads.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import FileRef, Report
from app.repositories.metric import ExtractedMetricRepository
from app.repositories.report import ReportRepository
from app.repositories.report_image import ReportImageRepository
from app.schemas.report import ReportResponse, ReportUploadResponse
from app.services.storage import FileTooLargeError, LocalReportStorage, StorageError


@dataclass(slots=True)
class ReportDownloadContext:
    """Resolved context for serving a report file."""

    report: Report
    path: Path
    mime: str
    etag: str
    filename: str


class ReportService:
    """Business logic for report management."""

    ALLOWED_MIME_TYPES = {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    }
    DEFAULT_FILENAME = "original.docx"

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ReportRepository(db)
        self.storage = LocalReportStorage(settings.file_storage_base)

        if settings.file_storage != "LOCAL":
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Only LOCAL storage is supported in this version.",
            )

    async def upload_report(
        self,
        participant_id: uuid.UUID,
        upload: UploadFile,
    ) -> ReportUploadResponse:
        """Handle report upload pipeline."""
        if not await self.repo.participant_exists(participant_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Participant not found"
            )

        await self._validate_file(upload)

        report_id = uuid.uuid4()
        file_ref_id = uuid.uuid4()

        key = self.storage.report_key(str(participant_id), str(report_id))

        mime = (
            upload.content_type
            or "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

        try:
            stored = await self.storage.save_report(upload, key, settings.report_max_size_bytes)
        except FileTooLargeError as exc:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Report file exceeds maximum allowed size",
            ) from exc
        except StorageError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to store report file: {exc}",
            ) from exc

        file_ref = FileRef(
            id=file_ref_id,
            storage="LOCAL",
            bucket="local",
            key=stored.key,
            filename=upload.filename,
            mime=mime,
            size_bytes=stored.size_bytes,
        )
        report = Report(
            id=report_id,
            participant_id=participant_id,
            status="UPLOADED",
            file_ref_id=file_ref_id,
        )

        try:
            saved_report = await self.repo.create(report, file_ref)
        except IntegrityError as exc:
            await self.db.rollback()
            self.storage.delete_file(stored.path)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Failed to create report due to constraint violation",
            ) from exc
        except Exception:
            await self.db.rollback()
            self.storage.delete_file(stored.path)
            raise

        response = ReportResponse.model_validate(saved_report)
        return ReportUploadResponse(**response.model_dump(), etag=stored.etag)

    async def get_report_by_id(self, report_id: uuid.UUID) -> Report:
        """Get report by ID, raise 404 if not found."""
        report = await self.repo.get_with_file_ref(report_id)
        if not report:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
        return report

    async def get_participant_reports(self, participant_id: uuid.UUID) -> list[Report]:
        """Get all reports for a participant."""
        if not await self.repo.participant_exists(participant_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Participant not found"
            )
        return await self.repo.get_all_by_participant(participant_id)

    async def get_download_context(self, report_id: uuid.UUID) -> ReportDownloadContext:
        """Resolve report and file path for download."""
        report = await self.repo.get_with_file_ref(report_id)
        if not report:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

        if report.file_ref.storage != "LOCAL":
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Only LOCAL storage is supported in this version.",
            )

        path = self.storage.resolve_path(report.file_ref.key)
        if not path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report file not found",
            )

        try:
            etag = await self.storage.compute_etag(path)
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to read report file: {exc}",
            ) from exc

        return ReportDownloadContext(
            report=report,
            path=path,
            mime=report.file_ref.mime,
            etag=etag,
            filename=self.DEFAULT_FILENAME,
        )

    async def _validate_file(self, upload: UploadFile) -> None:
        """Validate incoming upload for MIME type and filename."""
        if upload.filename is None or not upload.filename.lower().endswith(".docx"):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Only .docx files are supported",
            )

        content_type = (upload.content_type or "").lower()
        if content_type not in {m.lower() for m in self.ALLOWED_MIME_TYPES}:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Unsupported MIME type for report upload",
            )

    @staticmethod
    def format_etag(etag: str) -> str:
        """Wrap ETag hash in quotes for HTTP headers."""
        return f'"{etag}"'

    @staticmethod
    def matches_etag(if_none_match: str | None, etag: str) -> bool:
        """Check If-None-Match header against supplied ETag."""
        if not if_none_match:
            return False

        candidates = [token.strip() for token in if_none_match.split(",") if token.strip()]
        for candidate in candidates:
            if candidate == "*":
                return True
            if candidate.startswith("W/"):
                candidate = candidate[2:]
            candidate = candidate.strip('"')
            if candidate == etag:
                return True
        return False

    async def delete_report(self, report_id: uuid.UUID) -> None:
        """
        Delete report and all related entities and files.
        - Removes extracted metrics for the report
        - Removes report images and their files
        - Removes original report file
        - Deletes report and its file_ref
        """
        # Load report with file_ref or 404
        report = await self.get_report_by_id(report_id)

        # Delete extracted metrics
        metrics_repo = ExtractedMetricRepository(self.db)
        await metrics_repo.delete_by_report(report.id)

        # Delete report images' files, then DB records
        image_repo = ReportImageRepository(self.db)
        images_with_files = await image_repo.get_by_report(report.id)
        for image in images_with_files:
            if image.file_ref and image.file_ref.storage == "LOCAL":
                image_path = self.storage.resolve_path(image.file_ref.key)
                self.storage.delete_file(image_path)
        await image_repo.delete_by_report_id(report.id)

        # Delete original report file
        if report.file_ref and report.file_ref.storage == "LOCAL":
            report_path = self.storage.resolve_path(report.file_ref.key)
            self.storage.delete_file(report_path)

        # Delete report and associated file_ref in a single commit
        file_ref = report.file_ref
        await self.db.delete(report)
        await self.db.flush()
        if file_ref is not None:
            await self.db.delete(file_ref)
        await self.db.commit()
