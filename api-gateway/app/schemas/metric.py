"""
Pydantic schemas for Metric operations.

Schemas for metric definitions and extracted metrics with validation.
"""

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.metric_localization import get_metric_display_name_ru

# MetricDef Schemas

class MetricDefBase(BaseModel):
    """Base schema for metric definition."""

    code: str = Field(..., min_length=1, max_length=50, description="Unique metric code")
    name: str = Field(..., min_length=1, max_length=255, description="Metric name")
    name_ru: str | None = Field(
        None, min_length=1, max_length=255, description="Metric name in Russian"
    )
    description: str | None = Field(None, description="Metric description")
    unit: str | None = Field(None, max_length=50, description="Measurement unit")
    min_value: Decimal | None = Field(None, description="Minimum allowed value")
    max_value: Decimal | None = Field(None, description="Maximum allowed value")
    active: bool = Field(True, description="Whether metric is active")
    category_id: UUID | None = Field(None, description="Category ID for grouping")
    sort_order: int = Field(0, ge=0, description="Sort order within category")


class MetricDefCreateRequest(MetricDefBase):
    """Request schema for creating a new metric definition."""

    @field_validator("min_value", "max_value")
    @classmethod
    def validate_range(cls, v: Decimal | None, info) -> Decimal | None:
        """Validate that min_value <= max_value if both are provided."""
        if (
            v is not None
            and info.data.get("min_value") is not None
            and info.data.get("max_value") is not None
        ):
            if info.field_name == "max_value" and info.data["min_value"] > v:
                raise ValueError("min_value must be less than or equal to max_value")
        return v


class MetricDefUpdateRequest(BaseModel):
    """Request schema for updating a metric definition."""

    name: str | None = Field(None, min_length=1, max_length=255)
    name_ru: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    unit: str | None = Field(None, max_length=50)
    min_value: Decimal | None = None
    max_value: Decimal | None = None
    active: bool | None = None
    category_id: UUID | None = Field(None, description="Category ID for grouping")
    sort_order: int | None = Field(None, ge=0, description="Sort order within category")


class MetricDefResponse(BaseModel):
    """Response schema for metric definition."""

    id: UUID
    code: str
    name: str
    name_ru: str | None
    description: str | None
    unit: str | None
    min_value: Decimal | None
    max_value: Decimal | None
    active: bool
    category_id: UUID | None = None
    sort_order: int = 0

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def ensure_name_ru(cls, values: dict[str, object]) -> dict[str, object]:
        """Populate Russian display name fallback if missing in DB."""
        if isinstance(values, dict):
            name_ru = values.get("name_ru")
            code = values.get("code")
            if (name_ru is None or (isinstance(name_ru, str) and not name_ru.strip())) and isinstance(
                code, str
            ):
                fallback = get_metric_display_name_ru(code)
                if fallback:
                    values["name_ru"] = fallback
        return values


class MetricDefListResponse(BaseModel):
    """Response schema for list of metric definitions."""

    items: list[MetricDefResponse]
    total: int


class MetricUsageResponse(BaseModel):
    """Response schema for metric usage statistics."""

    metric_id: UUID
    extracted_metrics_count: int = Field(..., description="Number of extracted metric values")
    participant_metrics_count: int = Field(0, description="Number of participant metric values")
    scoring_results_count: int = Field(0, description="Number of scoring results affected")
    weight_tables_count: int = Field(..., description="Number of weight tables using this metric")
    reports_affected: int = Field(..., description="Number of unique reports with this metric")


# ExtractedMetric Schemas

class ExtractedMetricBase(BaseModel):
    """Base schema for extracted metric."""

    metric_def_id: UUID = Field(..., description="Metric definition ID")
    value: Decimal = Field(..., description="Extracted value")
    source: Literal["OCR", "LLM", "MANUAL"] = Field("MANUAL", description="Extraction source")
    confidence: Decimal | None = Field(None, ge=0, le=1, description="Confidence score (0-1)")
    notes: str | None = Field(None, description="Additional notes")


class ExtractedMetricCreateRequest(ExtractedMetricBase):
    """Request schema for creating/updating an extracted metric."""

    @field_validator("value")
    @classmethod
    def validate_value_range(cls, v: Decimal) -> Decimal:
        """
        Validate that value is in the expected range [1..10] for most metrics.
        This is a soft validation; actual range checks should be done against metric_def.
        """
        if v < 0:
            raise ValueError("Value must be non-negative")
        return v


class ExtractedMetricUpdateRequest(BaseModel):
    """Request schema for updating an extracted metric."""

    value: Decimal = Field(..., description="Updated value")
    notes: str | None = Field(None, description="Additional notes")


class ExtractedMetricResponse(BaseModel):
    """Response schema for extracted metric."""

    id: UUID
    report_id: UUID
    metric_def_id: UUID
    value: Decimal
    source: str
    confidence: Decimal | None
    notes: str | None

    model_config = {"from_attributes": True}


class ExtractedMetricWithDefResponse(ExtractedMetricResponse):
    """Response schema for extracted metric with metric definition included."""

    metric_def: MetricDefResponse


class ExtractedMetricListResponse(BaseModel):
    """Response schema for list of extracted metrics."""

    items: list[ExtractedMetricWithDefResponse]
    total: int


class ExtractedMetricBulkCreateRequest(BaseModel):
    """Request schema for bulk creating/updating extracted metrics for a report."""

    metrics: list[ExtractedMetricCreateRequest] = Field(
        ..., description="List of metrics to create/update"
    )


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str


class TopCompetency(BaseModel):
    """Top competency item for final report - sorted by contribution (value × weight)."""

    metric_code: str = Field(..., description="Metric code")
    metric_name: str = Field(..., description="Metric name in English")
    metric_name_ru: str = Field(..., description="Metric name in Russian")
    value: Decimal = Field(..., description="Metric value (1-10)")
    weight: Decimal = Field(..., description="Weight (0-1)")
    contribution: Decimal = Field(..., description="Contribution to score (value × weight)")


# Metric Template Schemas

class MetricTemplateItem(BaseModel):
    """Schema for a metric template item (metric definition with optional value)."""

    metric_def: MetricDefResponse = Field(..., description="Metric definition")
    value: Decimal | None = Field(None, description="Current value (if already filled)")
    source: str | None = Field(None, description="Source of extraction (if value exists)")
    confidence: Decimal | None = Field(None, description="Confidence score (if value exists)")
    notes: str | None = Field(None, description="Additional notes (if value exists)")


class MetricTemplateResponse(BaseModel):
    """Response schema for metric template - list of all active metrics with optional values."""

    items: list[MetricTemplateItem]
    total: int
    filled_count: int = Field(..., description="Number of metrics that have values")
    missing_count: int = Field(..., description="Number of metrics without values")


# Metric Mapping Schemas

class MetricMappingResponse(BaseModel):
    """Response schema for unified metric label-to-code mapping."""

    mappings: dict[str, str] = Field(
        ..., description="Dictionary of label (uppercase) -> metric_code mappings"
    )
    total: int = Field(..., description="Total number of mappings")


# Bulk Operations Schemas


class MetricDefBulkMoveRequest(BaseModel):
    """Request schema for bulk moving metric definitions to a category."""

    metric_ids: list[UUID] = Field(
        ..., min_length=1, description="List of metric definition IDs to move"
    )
    target_category_id: UUID | None = Field(
        None, description="Target category ID (null for uncategorized)"
    )


class MetricDefBulkDeleteRequest(BaseModel):
    """Request schema for bulk deleting metric definitions."""

    metric_ids: list[UUID] = Field(
        ..., min_length=1, description="List of metric definition IDs to delete"
    )


class BulkMoveUsageWarning(BaseModel):
    """Usage warning for bulk move operation."""

    weight_tables_affected: int = Field(0, description="Number of weight tables affected")
    extracted_metrics_affected: int = Field(0, description="Number of extracted metrics affected")


class BulkOperationResult(BaseModel):
    """Response schema for bulk operations."""

    success: bool = Field(..., description="Whether the operation was successful")
    affected_count: int = Field(..., description="Number of items affected")
    errors: list[dict] = Field(default_factory=list, description="List of error objects if any")
    usage_warning: dict | None = Field(None, description="Usage warning for move operations")
