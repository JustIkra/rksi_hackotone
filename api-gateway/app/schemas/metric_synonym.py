from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class SynonymCreate(BaseModel):
    synonym: str = Field(..., max_length=255)

    @field_validator('synonym')
    @classmethod
    def normalize_synonym(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError('Синоним не может быть пустым')
        return stripped


class SynonymUpdate(BaseModel):
    synonym: str = Field(..., max_length=255)

    @field_validator('synonym')
    @classmethod
    def normalize_synonym(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError('Синоним не может быть пустым')
        return stripped


class SynonymResponse(BaseModel):
    id: int
    synonym: str
    metric_def_id: UUID
    created_at: datetime
    created_by_id: UUID | None

    model_config = {"from_attributes": True}


class SynonymListResponse(BaseModel):
    items: list[SynonymResponse]
    total: int
