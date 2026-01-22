"""
Pydantic schemas for metric import/export operations.
"""

from pydantic import BaseModel, Field


class ImportPreviewItem(BaseModel):
    """Item in import preview response."""

    code: str = Field(..., description="Metric code")
    name: str | None = Field(None, description="Metric name")
    changes: dict[str, str] | None = Field(
        None, description="Changes to be applied (field: 'old -> new')"
    )


class ImportError(BaseModel):
    """Error encountered during import."""

    row: int = Field(..., description="Row number where error occurred")
    error: str = Field(..., description="Error description")


class ImportPreviewResponse(BaseModel):
    """Response for import preview endpoint."""

    to_create: list[ImportPreviewItem] = Field(
        default_factory=list, description="Metrics that will be created"
    )
    to_update: list[ImportPreviewItem] = Field(
        default_factory=list, description="Metrics that will be updated"
    )
    errors: list[ImportError] = Field(
        default_factory=list, description="Errors found during parsing"
    )


class ImportResultResponse(BaseModel):
    """Response for import endpoint."""

    created: int = Field(..., description="Number of metrics created")
    updated: int = Field(..., description="Number of metrics updated")
    errors: list[ImportError] = Field(
        default_factory=list, description="Errors encountered during import"
    )


class ExportMetricItem(BaseModel):
    """Metric item for export."""

    code: str
    name: str
    name_ru: str | None = None
    description: str | None = None
    unit: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    active: bool = True
    category_code: str | None = None


class ExportResponse(BaseModel):
    """Response for JSON export."""

    metrics: list[ExportMetricItem] = Field(
        default_factory=list, description="List of exported metrics"
    )
    total: int = Field(..., description="Total number of metrics")
