"""
Metric categories management router.

Administrative endpoints for managing metric categories.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, require_admin
from app.db.models import User
from app.db.session import get_db
from app.repositories.metric_category import MetricCategoryRepository
from app.schemas.metric_category import (
    MetricCategoryCreate,
    MetricCategoryListResponse,
    MetricCategoryReorderRequest,
    MetricCategoryResponse,
    MetricCategoryUpdate,
    MetricCategoryUsageResponse,
)

router = APIRouter(prefix="/admin/metric-categories", tags=["metric-categories"])


@router.get("", response_model=MetricCategoryListResponse, status_code=status.HTTP_200_OK)
async def list_metric_categories(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> MetricCategoryListResponse:
    """
    List all metric categories.

    Requires: ACTIVE user (any role) - categories are readable by all authenticated users.

    Returns: List of metric categories with metrics count.
    """
    repo = MetricCategoryRepository(db)
    categories_with_count = await repo.list_with_metrics_count()

    items = [
        MetricCategoryResponse(
            id=category.id,
            code=category.code,
            name=category.name,
            description=category.description,
            sort_order=category.sort_order,
            metrics_count=count,
        )
        for category, count in categories_with_count
    ]

    uncategorized_count = await repo.get_uncategorized_metrics_count()
    return MetricCategoryListResponse(
        items=items, total=len(items), uncategorized_count=uncategorized_count
    )


# IMPORTANT: Fixed routes MUST be defined BEFORE parameterized routes
# to avoid FastAPI matching "reorder" as a UUID parameter
@router.patch("/reorder", response_model=MetricCategoryListResponse, status_code=status.HTTP_200_OK)
async def reorder_metric_category(
    request: MetricCategoryReorderRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> MetricCategoryListResponse:
    """
    Reorder a single metric category.

    Requires: ADMIN role.

    Request body:
    - category_id: UUID of the category to move
    - target_position: Target position (0-based index), auto-corrected if out of bounds

    Updates sort_order for all affected categories using gap algorithm (increments of 10).

    Returns: Updated list of metric categories.
    """
    repo = MetricCategoryRepository(db)

    try:
        await repo.reorder_single(request.category_id, request.target_position)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from None

    # Return full list with metrics count
    categories_with_count = await repo.list_with_metrics_count()

    items = [
        MetricCategoryResponse(
            id=category.id,
            code=category.code,
            name=category.name,
            description=category.description,
            sort_order=category.sort_order,
            metrics_count=count,
        )
        for category, count in categories_with_count
    ]

    uncategorized_count = await repo.get_uncategorized_metrics_count()
    return MetricCategoryListResponse(
        items=items, total=len(items), uncategorized_count=uncategorized_count
    )


@router.get("/{category_id}", response_model=MetricCategoryResponse, status_code=status.HTTP_200_OK)
async def get_metric_category(
    category_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> MetricCategoryResponse:
    """
    Get a metric category by ID.

    Requires: ACTIVE user (any role).

    Returns: Metric category details.
    """
    repo = MetricCategoryRepository(db)
    category = await repo.get_by_id(category_id)

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Metric category not found",
        )

    metrics_count = await repo.get_metrics_count(category_id)

    return MetricCategoryResponse(
        id=category.id,
        code=category.code,
        name=category.name,
        description=category.description,
        sort_order=category.sort_order,
        metrics_count=metrics_count,
    )


@router.post("", response_model=MetricCategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_metric_category(
    request: MetricCategoryCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> MetricCategoryResponse:
    """
    Create a new metric category.

    Requires: ADMIN role.

    Request body:
    - code: Unique category code (required, 1-50 chars)
    - name: Category name (required, 1-255 chars)
    - description: Description (optional)
    - sort_order: Sort order for display (default: 0)

    Returns: Created metric category.
    """
    repo = MetricCategoryRepository(db)

    # Check if code already exists
    existing = await repo.get_by_code(request.code)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Metric category with code '{request.code}' already exists",
        )

    category = await repo.create(
        code=request.code,
        name=request.name,
        description=request.description,
        sort_order=request.sort_order,
    )

    return MetricCategoryResponse(
        id=category.id,
        code=category.code,
        name=category.name,
        description=category.description,
        sort_order=category.sort_order,
        metrics_count=0,
    )


@router.put("/{category_id}", response_model=MetricCategoryResponse, status_code=status.HTTP_200_OK)
async def update_metric_category(
    category_id: UUID,
    request: MetricCategoryUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> MetricCategoryResponse:
    """
    Update a metric category.

    Requires: ADMIN role.

    Request body: All fields are optional, only provided fields will be updated.

    Returns: Updated metric category.
    """
    repo = MetricCategoryRepository(db)

    category = await repo.update(
        category_id=category_id,
        name=request.name,
        description=request.description,
        sort_order=request.sort_order,
    )

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Metric category not found",
        )

    metrics_count = await repo.get_metrics_count(category_id)

    return MetricCategoryResponse(
        id=category.id,
        code=category.code,
        name=category.name,
        description=category.description,
        sort_order=category.sort_order,
        metrics_count=metrics_count,
    )


@router.get(
    "/{category_id}/usage",
    response_model=MetricCategoryUsageResponse,
    status_code=status.HTTP_200_OK,
)
async def get_category_usage_stats(
    category_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> MetricCategoryUsageResponse:
    """
    Get usage statistics for a metric category.

    Requires: ACTIVE user (any role).

    Use this before deleting a category to understand the impact.

    Returns: Usage statistics including metrics count and extracted metrics count.
    """
    repo = MetricCategoryRepository(db)

    # Verify category exists
    category = await repo.get_by_id(category_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Metric category not found",
        )

    stats = await repo.get_usage_stats(category_id)
    return MetricCategoryUsageResponse(
        category_id=stats["category_id"],
        metrics_count=stats["metrics_count"],
        extracted_metrics_count=stats["extracted_metrics_count"],
    )


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_metric_category(
    category_id: UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> None:
    """
    Delete a metric category.

    Requires: ADMIN role.

    Warning: This will CASCADE delete all metrics in this category!

    Returns: No content on success.
    """
    repo = MetricCategoryRepository(db)

    # Get metrics count to warn about cascade
    metrics_count = await repo.get_metrics_count(category_id)
    if metrics_count > 0:
        # Still allow deletion but it will cascade
        pass

    success = await repo.delete(category_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Metric category not found",
        )
