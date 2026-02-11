"""
Pydantic schemas for Organization and Department CRUD.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# --- Organization ---

class OrganizationCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)


class OrganizationUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)


class OrganizationResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    created_at: datetime
    departments_count: int = 0
    participants_count: int = 0

    model_config = {"from_attributes": True}


class OrganizationDetailResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    created_at: datetime
    departments: list["DepartmentResponse"] = []

    model_config = {"from_attributes": True}


class OrganizationListResponse(BaseModel):
    items: list[OrganizationResponse]
    total: int
    page: int
    size: int
    pages: int


# --- Department ---

class DepartmentCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)


class DepartmentUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)


class DepartmentResponse(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    description: str | None
    created_at: datetime
    participants_count: int = 0
    weight_table_id: UUID | None = None
    weight_table_name: str | None = None

    model_config = {"from_attributes": True}


class DepartmentListResponse(BaseModel):
    items: list[DepartmentResponse]
    total: int


# --- Participant attachment ---

class AttachParticipantsRequest(BaseModel):
    participant_ids: list[UUID] = Field(..., min_length=1)


class DetachParticipantRequest(BaseModel):
    participant_id: UUID


# --- Weight table attachment ---

class AttachWeightTableRequest(BaseModel):
    weight_table_id: UUID | None = None


class ParticipantWithSuitabilityResponse(BaseModel):
    id: UUID
    full_name: str
    birth_date: datetime | None = None
    external_id: str | None = None
    department_id: UUID | None = None
    created_at: datetime
    suitability_pct: float | None = None
    final_score: float | None = None
    has_metrics: bool = False
    metrics_coverage: float | None = None

    model_config = {"from_attributes": True}
