"""
REST API endpoints for metrics management.

Provides CRUD for metric definitions and extracted metrics.
All endpoints require authentication (ACTIVE user).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, require_admin
from app.db.models import User
from app.db.session import get_db
from app.repositories.metric import ExtractedMetricRepository, MetricDefRepository
from app.repositories.report import ReportRepository
from app.schemas.metric import (
    ExtractedMetricBulkCreateRequest,
    ExtractedMetricCreateRequest,
    ExtractedMetricListResponse,
    ExtractedMetricResponse,
    ExtractedMetricUpdateRequest,
    ExtractedMetricWithDefResponse,
    MessageResponse,
    MetricDefCreateRequest,
    MetricDefListResponse,
    MetricDefResponse,
    MetricDefUpdateRequest,
    MetricMappingResponse,
    MetricTemplateItem,
    MetricTemplateResponse,
)
from app.services.metric_mapping import get_metric_mapping_service

router = APIRouter(prefix="/api", tags=["metrics"])


# MetricDef Endpoints

@router.post("/metric-defs", response_model=MetricDefResponse, status_code=status.HTTP_201_CREATED)
async def create_metric_def(
    request: MetricDefCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> MetricDefResponse:
    """
    Create a new metric definition.

    Requires: ACTIVE user (any role).

    Request body:
    - code: Unique metric code (required, 1-50 chars)
    - name: Metric name (required, 1-255 chars)
    - description: Description (optional)
    - unit: Measurement unit (optional, max 50 chars)
    - min_value: Minimum value (optional)
    - max_value: Maximum value (optional, must be >= min_value)
    - active: Whether metric is active (default: True)

    Returns: Created metric definition with UUID.
    """
    repo = MetricDefRepository(db)

    # Check if code already exists
    existing = await repo.get_by_code(request.code)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Metric definition with code '{request.code}' already exists",
        )

    # Validate range
    if request.min_value is not None and request.max_value is not None:
        if request.min_value > request.max_value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="min_value must be less than or equal to max_value",
            )

    metric_def = await repo.create(
        code=request.code,
        name=request.name,
        name_ru=request.name_ru,
        description=request.description,
        unit=request.unit,
        min_value=request.min_value,
        max_value=request.max_value,
        active=request.active,
    )
    return MetricDefResponse.model_validate(metric_def)


@router.get("/metric-defs", response_model=MetricDefListResponse)
async def list_metric_defs(
    active_only: bool = Query(False, description="Return only active metrics"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> MetricDefListResponse:
    """
    List all metric definitions.

    Requires: ACTIVE user (any role).

    Query parameters:
    - active_only: If true, return only active metrics (default: false)

    Returns: List of metric definitions sorted by code.
    """
    repo = MetricDefRepository(db)
    metrics = await repo.list_all(active_only=active_only)
    return MetricDefListResponse(
        items=[MetricDefResponse.model_validate(m) for m in metrics], total=len(metrics)
    )


@router.get("/metric-defs/{metric_def_id}", response_model=MetricDefResponse)
async def get_metric_def(
    metric_def_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> MetricDefResponse:
    """
    Get a metric definition by ID.

    Requires: ACTIVE user (any role).

    Returns: Metric definition details.
    """
    repo = MetricDefRepository(db)
    metric_def = await repo.get_by_id(metric_def_id)
    if not metric_def:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Metric definition not found"
        )
    return MetricDefResponse.model_validate(metric_def)


@router.put("/metric-defs/{metric_def_id}", response_model=MetricDefResponse)
async def update_metric_def(
    metric_def_id: UUID,
    request: MetricDefUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> MetricDefResponse:
    """
    Update a metric definition.

    Requires: ACTIVE user (any role).

    Request body: All fields are optional, only provided fields will be updated.

    Returns: Updated metric definition.
    """
    repo = MetricDefRepository(db)
    metric_def = await repo.update(
        metric_def_id=metric_def_id,
        name=request.name,
        name_ru=request.name_ru,
        description=request.description,
        unit=request.unit,
        min_value=request.min_value,
        max_value=request.max_value,
        active=request.active,
    )
    if not metric_def:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Metric definition not found"
        )
    return MetricDefResponse.model_validate(metric_def)


@router.delete("/metric-defs/{metric_def_id}", response_model=MessageResponse)
async def delete_metric_def(
    metric_def_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> MessageResponse:
    """
    Delete a metric definition.

    Requires: ACTIVE user (any role).

    Note: Will fail if there are extracted metrics referencing this definition (due to RESTRICT FK).

    Returns: Success message.
    """
    repo = MetricDefRepository(db)
    success = await repo.delete(metric_def_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Metric definition not found"
        )
    return MessageResponse(message="Metric definition deleted successfully")


# ExtractedMetric Endpoints

@router.get("/reports/{report_id}/metrics/template", response_model=MetricTemplateResponse)
async def get_metric_template(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> MetricTemplateResponse:
    """
    Get metric template for a report - all active metric definitions with current values.

    This endpoint returns a complete list of all active metric definitions,
    with values filled in if they have been extracted or manually entered for this report.
    Use this to display a form for manual metric entry.

    Requires: ACTIVE user (any role).

    Returns: Template with all active metrics and their current values (if any).
    """
    # Verify report exists
    report_repo = ReportRepository(db)
    report = await report_repo.get_with_file_ref(report_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    # Get all active metric definitions
    metric_def_repo = MetricDefRepository(db)
    all_metric_defs = await metric_def_repo.list_all(active_only=True)

    # Get existing extracted metrics for this report
    extracted_metric_repo = ExtractedMetricRepository(db)
    extracted_metrics = await extracted_metric_repo.list_by_report(report_id)

    # Create a map of metric_def_id -> extracted_metric for quick lookup
    extracted_map = {m.metric_def_id: m for m in extracted_metrics}

    # Build template items
    template_items = []
    filled_count = 0

    for metric_def in all_metric_defs:
        extracted = extracted_map.get(metric_def.id)

        if extracted:
            filled_count += 1
            template_items.append(
                MetricTemplateItem(
                    metric_def=MetricDefResponse.model_validate(metric_def),
                    value=extracted.value,
                    source=extracted.source,
                    confidence=extracted.confidence,
                    notes=extracted.notes,
                )
            )
        else:
            template_items.append(
                MetricTemplateItem(
                    metric_def=MetricDefResponse.model_validate(metric_def),
                    value=None,
                    source=None,
                    confidence=None,
                    notes=None,
                )
            )

    return MetricTemplateResponse(
        items=template_items,
        total=len(template_items),
        filled_count=filled_count,
        missing_count=len(template_items) - filled_count,
    )


@router.get("/reports/{report_id}/metrics", response_model=ExtractedMetricListResponse)
async def list_extracted_metrics(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ExtractedMetricListResponse:
    """
    List all extracted metrics for a report (only filled metrics).

    Requires: ACTIVE user (any role).

    Returns: List of extracted metrics with metric definitions.
    """
    # Verify report exists
    report_repo = ReportRepository(db)
    report = await report_repo.get_with_file_ref(report_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    repo = ExtractedMetricRepository(db)
    metrics = await repo.list_by_report(report_id)
    return ExtractedMetricListResponse(
        items=[ExtractedMetricWithDefResponse.model_validate(m) for m in metrics],
        total=len(metrics),
    )


@router.post(
    "/reports/{report_id}/metrics",
    response_model=ExtractedMetricResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_or_update_extracted_metric(
    report_id: UUID,
    request: ExtractedMetricCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ExtractedMetricResponse:
    """
    Create or update an extracted metric for a report.

    If (report_id, metric_def_id) already exists, the value will be updated.
    Otherwise, a new extracted metric will be created.

    Requires: ACTIVE user (any role).

    Request body:
    - metric_def_id: Metric definition ID (required)
    - value: Extracted value (required)
    - source: Source of extraction (default: MANUAL)
    - confidence: Confidence score 0-1 (optional)
    - notes: Additional notes (optional)

    Returns: Created or updated extracted metric.
    """
    # Verify report exists
    report_repo = ReportRepository(db)
    report = await report_repo.get_with_file_ref(report_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    # Verify metric_def exists
    metric_def_repo = MetricDefRepository(db)
    metric_def = await metric_def_repo.get_by_id(request.metric_def_id)
    if not metric_def:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Metric definition not found"
        )

    # Validate value against metric_def range
    if metric_def.min_value is not None and request.value < metric_def.min_value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Value {request.value} is below minimum allowed value {metric_def.min_value} for metric '{metric_def.code}'",
        )
    if metric_def.max_value is not None and request.value > metric_def.max_value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Value {request.value} is above maximum allowed value {metric_def.max_value} for metric '{metric_def.code}'",
        )

    repo = ExtractedMetricRepository(db)
    extracted_metric = await repo.create_or_update(
        report_id=report_id,
        metric_def_id=request.metric_def_id,
        value=request.value,
        source=request.source,
        confidence=request.confidence,
        notes=request.notes,
    )
    return ExtractedMetricResponse.model_validate(extracted_metric)


@router.post("/reports/{report_id}/metrics/bulk", response_model=MessageResponse)
async def bulk_create_extracted_metrics(
    report_id: UUID,
    request: ExtractedMetricBulkCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> MessageResponse:
    """
    Bulk create or update extracted metrics for a report.

    Requires: ACTIVE user (any role).

    Request body:
    - metrics: List of extracted metrics to create/update

    Returns: Success message with count of created/updated metrics.
    """
    # Verify report exists
    report_repo = ReportRepository(db)
    report = await report_repo.get_with_file_ref(report_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    repo = ExtractedMetricRepository(db)
    metric_def_repo = MetricDefRepository(db)

    created_count = 0
    for metric_req in request.metrics:
        # Verify metric_def exists
        metric_def = await metric_def_repo.get_by_id(metric_req.metric_def_id)
        if not metric_def:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Metric definition {metric_req.metric_def_id} not found",
            )

        # Validate value
        if metric_def.min_value is not None and metric_req.value < metric_def.min_value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Value {metric_req.value} is below minimum for metric '{metric_def.code}'",
            )
        if metric_def.max_value is not None and metric_req.value > metric_def.max_value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Value {metric_req.value} is above maximum for metric '{metric_def.code}'",
            )

        await repo.create_or_update(
            report_id=report_id,
            metric_def_id=metric_req.metric_def_id,
            value=metric_req.value,
            source=metric_req.source,
            confidence=metric_req.confidence,
            notes=metric_req.notes,
        )
        created_count += 1

    return MessageResponse(message=f"Successfully created/updated {created_count} metrics")


@router.put("/reports/{report_id}/metrics/{metric_def_id}", response_model=ExtractedMetricResponse)
async def update_extracted_metric(
    report_id: UUID,
    metric_def_id: UUID,
    request: ExtractedMetricUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ExtractedMetricResponse:
    """
    Update an extracted metric by report_id and metric_def_id.

    Requires: ACTIVE user (any role).

    Request body:
    - value: Updated value (required)
    - notes: Additional notes (optional)

    Returns: Updated extracted metric.
    """
    repo = ExtractedMetricRepository(db)
    extracted_metric = await repo.get_by_report_and_metric(report_id, metric_def_id)
    if not extracted_metric:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Extracted metric not found"
        )

    # Validate value against metric_def range
    metric_def = extracted_metric.metric_def
    if metric_def.min_value is not None and request.value < metric_def.min_value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Value {request.value} is below minimum allowed value {metric_def.min_value} for metric '{metric_def.code}'",
        )
    if metric_def.max_value is not None and request.value > metric_def.max_value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Value {request.value} is above maximum allowed value {metric_def.max_value} for metric '{metric_def.code}'",
        )

    # Update
    extracted_metric.value = request.value
    if request.notes is not None:
        extracted_metric.notes = request.notes
    await db.commit()
    await db.refresh(extracted_metric)

    return ExtractedMetricResponse.model_validate(extracted_metric)


@router.delete("/extracted-metrics/{extracted_metric_id}", response_model=MessageResponse)
async def delete_extracted_metric(
    extracted_metric_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> MessageResponse:
    """
    Delete an extracted metric by ID.

    Requires: ACTIVE user (any role).

    Returns: Success message.
    """
    repo = ExtractedMetricRepository(db)
    success = await repo.delete(extracted_metric_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Extracted metric not found"
        )
    return MessageResponse(message="Extracted metric deleted successfully")


@router.delete("/reports/{report_id}/metrics/{metric_def_id}", response_model=MessageResponse)
async def delete_extracted_metric_by_report_and_def(
    report_id: UUID,
    metric_def_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> MessageResponse:
    """
    Delete an extracted metric by report_id and metric_def_id.

    Used when user wants to clear/reset a metric value.

    Requires: ACTIVE user (any role).

    Returns: Success message.
    """
    repo = ExtractedMetricRepository(db)
    extracted_metric = await repo.get_by_report_and_metric(report_id, metric_def_id)
    if not extracted_metric:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Extracted metric not found"
        )
    success = await repo.delete(extracted_metric.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Failed to delete metric"
        )
    return MessageResponse(message="Metric value cleared successfully")


# Metric Mapping Endpoints

@router.get("/metrics/mapping", response_model=MetricMappingResponse)
async def get_metric_mapping(
    current_user: User = Depends(require_admin),
) -> MetricMappingResponse:
    """
    Get unified metric label-to-code mapping.

    Requires: ADMIN user.

    This endpoint returns the YAML configuration mapping for extracting
    metrics from documents. The mapping is unified for all report types.
    Useful for debugging and validation.

    Returns:
        Mapping configuration with label -> metric_code dictionary
    """
    mapping_service = get_metric_mapping_service()

    # Get unified mapping
    mappings = mapping_service.get_mapping()

    return MetricMappingResponse(mappings=mappings, total=len(mappings))
