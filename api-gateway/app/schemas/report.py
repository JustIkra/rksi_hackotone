"""
Pydantic schemas for report upload and retrieval.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class ReportStatus(str, Enum):
    """Lifecycle states for report processing."""

    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    EXTRACTED = "EXTRACTED"
    FAILED = "FAILED"


class FileRefResponse(BaseModel):
    """File reference metadata."""

    id: UUID
    storage: str
    bucket: str
    key: str
    filename: str | None
    mime: str
    size_bytes: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ReportResponse(BaseModel):
    """Report details with file metadata."""

    id: UUID
    participant_id: UUID
    status: ReportStatus
    uploaded_at: datetime
    extracted_at: datetime | None
    extract_error: str | None
    extract_warning: str | None = None
    extract_warning_details: dict | None = None
    file_ref: FileRefResponse

    model_config = {"from_attributes": True}


class ReportUploadResponse(ReportResponse):
    """Response for successful report upload."""

    etag: str = Field(..., description="Content hash for If-None-Match headers")


class ReportListResponse(BaseModel):
    """List of reports for a participant."""

    items: list[ReportResponse]
    total: int
