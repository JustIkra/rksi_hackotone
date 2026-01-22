"""
Pydantic schemas for AI metric generation from PDF/DOCX reports.

Defines request/response models for:
- File upload and generation task creation
- Task status tracking with progress
- Generated metric results
- Moderation (approve/reject) workflow
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Status of metric generation task."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ModerationStatus(str, Enum):
    """Moderation status for AI-generated metrics."""

    APPROVED = "APPROVED"
    PENDING = "PENDING"
    REJECTED = "REJECTED"


# ==================== Request Schemas ====================


class MetricGenerateRequest(BaseModel):
    """Request to start metric generation (file is sent via form-data)."""

    # File is handled separately via UploadFile
    pass


class MetricModerationRequest(BaseModel):
    """Request to moderate (approve/reject) a metric."""

    action: str = Field(
        ...,
        description="Moderation action: 'approve' or 'reject'",
        pattern="^(approve|reject)$",
    )
    reason: str | None = Field(
        None,
        max_length=500,
        description="Optional reason for rejection",
    )


# ==================== Response Schemas ====================


class GenerationTaskResponse(BaseModel):
    """Response when starting a metric generation task."""

    task_id: str = Field(..., description="Celery task ID for tracking progress")
    message: str = Field(default="Task started", description="Status message")


class TaskProgressResponse(BaseModel):
    """Response with task progress information."""

    task_id: str = Field(..., description="Celery task ID")
    status: TaskStatus = Field(..., description="Current task status")
    progress: int = Field(
        default=0, ge=0, le=100, description="Progress percentage (0-100)"
    )
    current_step: str | None = Field(
        None, description="Current processing step description"
    )
    total_pages: int | None = Field(None, description="Total pages in document")
    processed_pages: int | None = Field(None, description="Pages processed so far")
    metrics_found: int | None = Field(
        None, description="Number of metrics extracted so far"
    )
    error: str | None = Field(None, description="Error message if failed")
    result: dict[str, Any] | None = Field(
        None, description="Final result when completed"
    )


class AIRationale(BaseModel):
    """AI extraction rationale for a generated metric."""

    quotes: list[str] = Field(
        default_factory=list, description="Quotes from document supporting the metric"
    )
    page_numbers: list[int] | None = Field(
        None, description="Page numbers where evidence was found"
    )
    confidence: float = Field(
        default=0.5, ge=0.0, le=1.0, description="AI confidence score (not shown in UI)"
    )


class GeneratedMetricResponse(BaseModel):
    """Single generated metric response."""

    id: UUID = Field(..., description="Metric definition ID")
    code: str = Field(..., description="Metric code (auto-generated)")
    name: str = Field(..., description="Metric name (Russian)")
    name_ru: str | None = Field(None, description="Metric name in Russian")
    description: str | None = Field(None, description="Metric description")
    value: float | None = Field(
        None, ge=1, le=10, description="Suggested value (1-10)"
    )
    category_code: str | None = Field(None, description="Category code")
    category_name: str | None = Field(None, description="Category name")
    synonyms: list[str] = Field(
        default_factory=list, description="Suggested synonyms"
    )
    moderation_status: ModerationStatus = Field(
        default=ModerationStatus.PENDING, description="Current moderation status"
    )
    ai_rationale: AIRationale | None = Field(
        None, description="AI extraction rationale"
    )
    created_at: datetime | None = Field(None, description="Creation timestamp")

    model_config = {"from_attributes": True}


class PendingMetricsResponse(BaseModel):
    """Response with list of metrics pending moderation."""

    items: list[GeneratedMetricResponse] = Field(
        default_factory=list, description="List of pending metrics"
    )
    total: int = Field(default=0, description="Total count of pending metrics")


class ModerationResultResponse(BaseModel):
    """Response after moderating a metric."""

    id: UUID = Field(..., description="Metric definition ID")
    code: str = Field(..., description="Metric code")
    name: str = Field(..., description="Metric name")
    moderation_status: ModerationStatus = Field(..., description="New moderation status")
    message: str = Field(..., description="Result message")


class GenerationResultResponse(BaseModel):
    """Final result of metric generation task."""

    task_id: str = Field(..., description="Celery task ID")
    status: TaskStatus = Field(..., description="Final status")
    metrics_created: int = Field(default=0, description="Number of new metrics created")
    metrics_matched: int = Field(
        default=0, description="Number of metrics matched to existing definitions"
    )
    categories_created: int = Field(
        default=0, description="Number of new categories created"
    )
    synonyms_suggested: int = Field(
        default=0, description="Number of synonyms suggested"
    )
    errors: list[str] = Field(
        default_factory=list, description="Any errors encountered"
    )
    warnings: list[str] = Field(
        default_factory=list, description="Warnings (e.g., duplicates skipped)"
    )


# ==================== Internal Schemas (for service layer) ====================


class ExtractedMetricData(BaseModel):
    """Internal schema for extracted metric from AI."""

    name: str = Field(..., description="Metric name (Russian)")
    description: str | None = Field(None, description="Metric description")
    value: float | None = Field(None, ge=1, le=10, description="Suggested value (1-10)")
    category: str | None = Field(None, description="Category name or code")
    synonyms: list[str] = Field(default_factory=list, description="Suggested synonyms")
    rationale: AIRationale | None = Field(None, description="Extraction rationale")


class AIExtractionResult(BaseModel):
    """Result from AI extraction pass."""

    metrics: list[ExtractedMetricData] = Field(
        default_factory=list, description="Extracted metrics"
    )
    document_summary: str | None = Field(
        None, description="Brief summary of the document"
    )
    total_pages_processed: int = Field(default=0, description="Pages processed")


class AIReviewResult(BaseModel):
    """Result from AI review pass (deduplication and validation)."""

    metrics: list[ExtractedMetricData] = Field(
        default_factory=list, description="Reviewed and deduplicated metrics"
    )
    removed_duplicates: int = Field(
        default=0, description="Number of duplicates removed"
    )
    corrections_made: int = Field(default=0, description="Number of corrections made")
