"""
Pydantic schemas for Metric Category operations.

Schemas for metric category management with validation.
"""

from uuid import UUID

from pydantic import BaseModel, Field


class MetricCategoryBase(BaseModel):
    """Base schema for metric category."""

    code: str = Field(..., min_length=1, max_length=50, description="Unique category code")
    name: str = Field(..., min_length=1, max_length=255, description="Category name")
    description: str | None = Field(None, description="Category description")
    sort_order: int = Field(0, ge=0, description="Sort order for display")


class MetricCategoryCreate(MetricCategoryBase):
    """Request schema for creating a new metric category."""

    pass


class MetricCategoryUpdate(BaseModel):
    """Request schema for updating a metric category."""

    name: str | None = Field(None, min_length=1, max_length=255, description="Updated name")
    description: str | None = Field(None, description="Updated description")
    sort_order: int | None = Field(None, ge=0, description="Updated sort order")


class MetricCategoryResponse(BaseModel):
    """Response schema for metric category."""

    id: UUID
    code: str
    name: str
    description: str | None
    sort_order: int
    metrics_count: int = Field(0, description="Number of metrics in this category")

    model_config = {"from_attributes": True}


class MetricCategoryListResponse(BaseModel):
    """Response schema for list of metric categories."""

    items: list[MetricCategoryResponse]
    total: int
    uncategorized_count: int = Field(0, description="Number of metrics without a category")


class MetricCategoryUsageResponse(BaseModel):
    """Response schema for category usage statistics."""

    category_id: UUID
    metrics_count: int = Field(..., description="Number of metrics in this category")
    extracted_metrics_count: int = Field(..., description="Number of extracted metric values")


class MetricCategoryReorderRequest(BaseModel):
    """Request schema for reordering a single category."""

    category_id: UUID = Field(..., description="ID of category to move")
    target_position: int = Field(
        ...,
        ge=0,
        description="Target position (0-based index)"
    )
