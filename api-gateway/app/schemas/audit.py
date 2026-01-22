"""
Pydantic schemas for audit log API.

Defines request/response models for audit log endpoints.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuditLogUserInfo(BaseModel):
    """Minimal user info for audit log display."""

    id: UUID
    email: str
    full_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class AuditLogEntry(BaseModel):
    """Single audit log entry response."""

    id: int
    user_id: UUID | None
    user: AuditLogUserInfo | None = None
    action: str
    metric_codes: list[str]
    affected_counts: dict | None = None
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditLogListResponse(BaseModel):
    """Paginated list of audit log entries."""

    items: list[AuditLogEntry]
    total: int
    limit: int
    offset: int


class AuditLogFilters(BaseModel):
    """Query parameters for filtering audit logs."""

    start_date: datetime | None = Field(None, description="Filter from this date (inclusive)")
    end_date: datetime | None = Field(None, description="Filter until this date (inclusive)")
    action: str | None = Field(None, description="Filter by action type")
    limit: int = Field(50, ge=1, le=100, description="Maximum items to return")
    offset: int = Field(0, ge=0, description="Number of items to skip")


class ActionTypesResponse(BaseModel):
    """List of available action types for filtering."""

    actions: list[str]
