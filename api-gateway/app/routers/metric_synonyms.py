"""
REST API endpoints for metric synonyms management.

Provides CRUD operations for metric synonyms.
All endpoints require authentication (ADMIN role).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_admin
from app.db.models import User
from app.db.session import get_db
from app.repositories.metric import MetricDefRepository
from app.repositories.metric_synonym import MetricSynonymRepository
from app.schemas.metric_synonym import (
    SynonymCreate,
    SynonymListResponse,
    SynonymResponse,
    SynonymUpdate,
)

router = APIRouter(prefix="/api", tags=["metric-synonyms"])


@router.get("/metric-defs/{metric_def_id}/synonyms", response_model=SynonymListResponse)
async def get_metric_synonyms(
    metric_def_id: UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> SynonymListResponse:
    """
    Get all synonyms for a metric definition.

    Requires: ADMIN role.

    Args:
        metric_def_id: UUID of the metric definition

    Returns:
        List of synonyms for the metric definition.
    """
    # Verify metric_def exists
    metric_repo = MetricDefRepository(db)
    metric_def = await metric_repo.get_by_id(metric_def_id)
    if not metric_def:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Metric definition not found",
        )

    repo = MetricSynonymRepository(db)
    synonyms = await repo.get_by_metric_def_id(metric_def_id)

    return SynonymListResponse(
        items=[SynonymResponse.model_validate(s) for s in synonyms],
        total=len(synonyms),
    )


@router.post(
    "/metric-defs/{metric_def_id}/synonyms",
    response_model=SynonymResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_metric_synonym(
    metric_def_id: UUID,
    request: SynonymCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> SynonymResponse:
    """
    Create a new synonym for a metric definition.

    Requires: ADMIN role.

    Args:
        metric_def_id: UUID of the metric definition
        request: Synonym creation request

    Returns:
        Created synonym.

    Raises:
        404: Metric definition not found
        409: Synonym already exists (globally unique constraint)
    """
    # Verify metric_def exists
    metric_repo = MetricDefRepository(db)
    metric_def = await metric_repo.get_by_id(metric_def_id)
    if not metric_def:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Metric definition not found",
        )

    repo = MetricSynonymRepository(db)

    # Check for duplicate synonym (global uniqueness) with enriched response
    existing_synonym, existing_metric = await repo.find_existing_synonym_with_metric(
        request.synonym
    )
    if existing_synonym and existing_metric:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Synonym already exists for another metric",
                "existing_metric": {
                    "id": str(existing_metric.id),
                    "code": existing_metric.code,
                    "name_ru": existing_metric.name_ru or existing_metric.name,
                },
            },
        )

    # Check if synonym conflicts with metric names
    if await repo.check_conflicts_with_metric_names(request.synonym):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Synonym conflicts with an existing metric name",
        )

    synonym = await repo.create(
        metric_def_id=metric_def_id,
        synonym=request.synonym,
        created_by_id=current_user.id,
    )

    return SynonymResponse.model_validate(synonym)


@router.put("/metric-synonyms/{synonym_id}", response_model=SynonymResponse)
async def update_metric_synonym(
    synonym_id: int,
    request: SynonymUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> SynonymResponse:
    """
    Update an existing synonym.

    Requires: ADMIN role.

    Args:
        synonym_id: ID of the synonym to update
        request: Synonym update request

    Returns:
        Updated synonym.

    Raises:
        404: Synonym not found
        409: New synonym text already exists (globally unique constraint)
    """
    repo = MetricSynonymRepository(db)

    # Check if synonym exists
    existing = await repo.get_by_id(synonym_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Synonym not found",
        )

    # Check for duplicate synonym (excluding current one)
    if await repo.check_synonym_exists(request.synonym, exclude_id=synonym_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Synonym already exists for another metric",
        )

    # Check if new synonym conflicts with metric names
    if await repo.check_conflicts_with_metric_names(request.synonym):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Synonym conflicts with an existing metric name",
        )

    updated = await repo.update(synonym_id, request.synonym)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Synonym not found",
        )

    return SynonymResponse.model_validate(updated)


@router.delete("/metric-synonyms/{synonym_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_metric_synonym(
    synonym_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> None:
    """
    Delete a synonym.

    Requires: ADMIN role.

    Args:
        synonym_id: ID of the synonym to delete

    Raises:
        404: Synonym not found
    """
    repo = MetricSynonymRepository(db)

    success = await repo.delete(synonym_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Synonym not found",
        )
