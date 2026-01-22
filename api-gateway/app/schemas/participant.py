"""
Pydantic schemas for Participant CRUD and search operations.

All request/response DTOs for participant management.
"""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

# Request Schemas

class ParticipantCreateRequest(BaseModel):
    """Request schema for creating a new participant."""

    full_name: str = Field(
        ..., min_length=1, max_length=255, description="Full name of the participant"
    )
    birth_date: date | None = Field(None, description="Birth date (optional)")
    external_id: str | None = Field(None, max_length=100, description="External ID (optional)")


class ParticipantUpdateRequest(BaseModel):
    """Request schema for updating an existing participant."""

    full_name: str | None = Field(None, min_length=1, max_length=255, description="Full name")
    birth_date: date | None = Field(None, description="Birth date")
    external_id: str | None = Field(None, max_length=100, description="External ID")


class ParticipantSearchParams(BaseModel):
    """Query parameters for searching participants."""

    query: str | None = Field(None, description="Search by full_name (case-insensitive substring)")
    external_id: str | None = Field(None, description="Filter by exact external_id match")
    page: int = Field(1, ge=1, description="Page number (1-indexed)")
    size: int = Field(20, ge=1, le=100, description="Page size (max 100)")


# Response Schemas

class ParticipantResponse(BaseModel):
    """Response schema for a single participant."""

    id: UUID
    full_name: str
    birth_date: date | None
    external_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ParticipantListResponse(BaseModel):
    """Response schema for paginated participant list."""

    items: list[ParticipantResponse]
    total: int
    page: int
    size: int
    pages: int


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str


# Scoring History Schemas

class MetricItem(BaseModel):
    """Metric item for strengths/dev_areas in scoring history."""

    metric_code: str
    metric_name: str
    value: str  # Decimal as string
    weight: str  # Decimal as string


class ScoringHistoryItem(BaseModel):
    """Single scoring result item in history."""

    id: UUID
    prof_activity_code: str
    prof_activity_name: str
    score_pct: float
    strengths: list[MetricItem] | None = None
    dev_areas: list[MetricItem] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ScoringHistoryResponse(BaseModel):
    """Response schema for scoring history list."""

    results: list[ScoringHistoryItem]
    total: int


# Participant Metrics Schemas

class ParticipantMetricResponse(BaseModel):
    """Response schema for a single participant metric."""

    metric_code: str
    value: float
    confidence: float | None
    last_source_report_id: UUID | None
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def model_validate(cls, obj, **kwargs):
        """Override model_validate to handle Decimal conversion."""
        from decimal import Decimal

        # Convert Decimal to float if needed
        if hasattr(obj, 'value') and isinstance(obj.value, Decimal):
            obj_dict = {
                'metric_code': obj.metric_code,
                'value': float(obj.value),
                'confidence': float(obj.confidence) if obj.confidence is not None else None,
                'last_source_report_id': obj.last_source_report_id,
                'updated_at': obj.updated_at,
            }
            return super().model_validate(obj_dict, **kwargs)
        return super().model_validate(obj, **kwargs)


class ParticipantMetricsListResponse(BaseModel):
    """Response schema for list of participant metrics."""

    participant_id: UUID
    metrics: list[ParticipantMetricResponse]
    total: int


class ParticipantMetricUpdateRequest(BaseModel):
    """Request schema for updating a participant metric value manually."""

    value: float = Field(..., ge=1, le=10, description="Metric value (range 1-10)")
    confidence: float | None = Field(None, ge=0, le=1, description="Confidence score (0-1)")
