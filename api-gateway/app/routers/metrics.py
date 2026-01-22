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
    BulkOperationResult,
    ExtractedMetricBulkCreateRequest,
    ExtractedMetricCreateRequest,
    ExtractedMetricListResponse,
    ExtractedMetricResponse,
    ExtractedMetricUpdateRequest,
    ExtractedMetricWithDefResponse,
    MessageResponse,
    MetricDefBulkDeleteRequest,
    MetricDefBulkMoveRequest,
    MetricDefCreateRequest,
    MetricDefListResponse,
    MetricDefResponse,
    MetricDefUpdateRequest,
    MetricMappingResponse,
    MetricTemplateItem,
    MetricTemplateResponse,
    MetricUsageResponse,
)
from app.schemas.metric_import import (
    ExportMetricItem,
    ExportResponse,
    ImportResultResponse,
)
from app.schemas.metric_import import (
    ImportError as ImportErrorSchema,
)
from app.services.metric_mapping import get_metric_mapping_service

router = APIRouter(prefix="/api", tags=["metrics"])


# MetricDef Endpoints

@router.post("/metric-defs", response_model=MetricDefResponse, status_code=status.HTTP_201_CREATED)
async def create_metric_def(
    request: MetricDefCreateRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> MetricDefResponse:
    """
    Create a new metric definition.

    Requires: ADMIN role.

    Request body:
    - code: Unique metric code (required, 1-50 chars)
    - name: Metric name (required, 1-255 chars)
    - description: Description (optional)
    - unit: Measurement unit (optional, max 50 chars)
    - min_value: Minimum value (optional)
    - max_value: Maximum value (optional, must be >= min_value)
    - active: Whether metric is active (default: True)
    - category_id: Category ID for grouping (optional)
    - sort_order: Sort order within category (default: 0)

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
        category_id=request.category_id,
        sort_order=request.sort_order,
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


# IMPORTANT: Fixed routes MUST be defined BEFORE parameterized routes
# to avoid FastAPI matching "bulk-move" or "bulk-delete" as a UUID parameter


@router.patch("/metric-defs/bulk-move", response_model=BulkOperationResult)
async def bulk_move_metric_defs(
    request: MetricDefBulkMoveRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> BulkOperationResult:
    """
    Move multiple metric definitions to a category (atomic operation).

    Requires: ADMIN role.

    Request body:
    - metric_ids: List of metric definition UUIDs to move (all must exist)
    - target_category_id: Target category UUID (null to remove from category)

    All-or-nothing: if any metric_id is not found, the entire operation fails.

    Returns: Operation result with affected count and usage_warning.
    """
    repo = MetricDefRepository(db)

    # Validate target category exists if provided
    if request.target_category_id is not None:
        from app.repositories.metric_category import MetricCategoryRepository

        category_repo = MetricCategoryRepository(db)
        category = await category_repo.get_by_id(request.target_category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Target category {request.target_category_id} not found",
            )

    # Pre-validate all metric IDs exist (atomic check)
    errors = []
    for metric_id in request.metric_ids:
        metric = await repo.get_by_id(metric_id)
        if not metric:
            errors.append({"metric_id": str(metric_id), "error": "Metric not found"})

    if errors:
        return BulkOperationResult(
            success=False,
            affected_count=0,
            errors=errors,
        )

    # Gather usage stats for warning
    total_weight_tables = 0
    total_extracted = 0
    for metric_id in request.metric_ids:
        stats = await repo.get_usage_stats(metric_id)
        total_weight_tables += stats["weight_tables_count"]
        total_extracted += stats["extracted_metrics_count"]

    # Perform atomic move
    affected_count, move_errors = await repo.bulk_move_to_category(
        metric_ids=request.metric_ids,
        target_category_id=request.target_category_id,
    )

    usage_warning = None
    if total_weight_tables > 0 or total_extracted > 0:
        usage_warning = {
            "weight_tables_affected": total_weight_tables,
            "extracted_metrics_affected": total_extracted,
        }

    return BulkOperationResult(
        success=len(move_errors) == 0,
        affected_count=affected_count,
        errors=move_errors,
        usage_warning=usage_warning,
    )


@router.delete("/metric-defs/bulk-delete", response_model=BulkOperationResult)
async def bulk_delete_metric_defs(
    request: MetricDefBulkDeleteRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> BulkOperationResult:
    """
    Delete multiple metric definitions with CASCADE.

    Requires: ADMIN role.

    Request body:
    - metric_ids: List of metric definition UUIDs to delete

    Cascade behavior:
    - Synonyms: automatically deleted
    - Extracted metrics: automatically deleted
    - Weight tables: metric removed from JSONB, marked as needs_review

    Returns: Operation result with deleted count, affected counts, and any errors.
    """
    from app.repositories.metric_audit import MetricAuditLogRepository

    repo = MetricDefRepository(db)

    # Get metric codes before deletion for audit log
    metric_codes = []
    for metric_id in request.metric_ids:
        metric_def = await repo.get_by_id(metric_id)
        if metric_def:
            metric_codes.append(metric_def.code)

    deleted_count, errors, affected_counts = await repo.bulk_delete(
        metric_ids=request.metric_ids
    )

    # Log audit entry if any metrics were deleted
    if deleted_count > 0:
        audit_repo = MetricAuditLogRepository(db)
        await audit_repo.create(
            user_id=admin.id,
            action="bulk_delete",
            metric_codes=metric_codes[:deleted_count],  # Only log successfully deleted
            affected_counts=affected_counts,
        )

    usage_warning = None
    if any(affected_counts.values()):
        usage_warning = {
            "cascaded_extracted_metrics": affected_counts["extracted_metrics"],
            "cascaded_synonyms": affected_counts["synonyms"],
            "weight_tables_affected": affected_counts["weight_tables"],
        }

    return BulkOperationResult(
        success=len(errors) == 0,
        affected_count=deleted_count,
        errors=errors,
        usage_warning=usage_warning,
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
    _admin: User = Depends(require_admin),
) -> MetricDefResponse:
    """
    Update a metric definition.

    Requires: ADMIN role.

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
        category_id=request.category_id,
        sort_order=request.sort_order,
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
    _admin: User = Depends(require_admin),
) -> MessageResponse:
    """
    Delete a metric definition.

    Requires: ADMIN role.

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


@router.get("/metric-defs/{metric_def_id}/usage", response_model=MetricUsageResponse)
async def get_metric_usage_stats(
    metric_def_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> MetricUsageResponse:
    """
    Get usage statistics for a metric definition.

    Requires: ACTIVE user (any role).

    Use this before deleting a metric to understand the impact.

    Returns: Usage statistics including:
    - extracted_metrics_count: Number of extracted metric values
    - weight_tables_count: Number of weight tables using this metric
    - reports_affected: Number of unique reports with this metric
    """
    repo = MetricDefRepository(db)

    # Verify metric exists
    metric_def = await repo.get_by_id(metric_def_id)
    if not metric_def:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Metric definition not found"
        )

    stats = await repo.get_usage_stats(metric_def_id)
    return MetricUsageResponse(
        metric_id=stats["metric_id"],
        extracted_metrics_count=stats["extracted_metrics_count"],
        participant_metrics_count=stats["participant_metrics_count"],
        scoring_results_count=stats["scoring_results_count"],
        weight_tables_count=stats["weight_tables_count"],
        reports_affected=stats["reports_affected"],
    )


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


# Import/Export Endpoints


@router.get("/admin/metrics/export", response_model=ExportResponse)
async def export_metrics(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> ExportResponse:
    """
    Export all metric definitions as JSON.

    Requires: ADMIN role.

    Returns: JSON with all metrics suitable for backup/import.
    """
    repo = MetricDefRepository(db)
    metrics = await repo.list_all(active_only=False)

    export_items = [
        ExportMetricItem(
            code=m.code,
            name=m.name,
            name_ru=m.name_ru,
            description=m.description,
            unit=m.unit,
            min_value=float(m.min_value) if m.min_value is not None else None,
            max_value=float(m.max_value) if m.max_value is not None else None,
            active=m.active,
        )
        for m in metrics
    ]

    return ExportResponse(metrics=export_items, total=len(export_items))


@router.post("/admin/metrics/import", response_model=ImportResultResponse)
async def import_metrics(
    data: ExportResponse,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> ImportResultResponse:
    """
    Import metric definitions from JSON (upsert).

    Requires: ADMIN role.

    Request body: JSON with metrics array (same format as export).

    Behavior:
    - If metric code exists: update fields
    - If metric code doesn't exist: create new

    Returns: Import result with created/updated counts.
    """
    from decimal import Decimal

    repo = MetricDefRepository(db)
    created = 0
    updated = 0
    errors: list[ImportErrorSchema] = []

    for idx, metric_data in enumerate(data.metrics, start=1):
        try:
            # Check if metric exists
            existing = await repo.get_by_code(metric_data.code)

            min_val = Decimal(str(metric_data.min_value)) if metric_data.min_value is not None else None
            max_val = Decimal(str(metric_data.max_value)) if metric_data.max_value is not None else None

            if existing:
                # Update existing metric
                await repo.update(
                    metric_def_id=existing.id,
                    name=metric_data.name,
                    name_ru=metric_data.name_ru,
                    description=metric_data.description,
                    unit=metric_data.unit,
                    min_value=min_val,
                    max_value=max_val,
                    active=metric_data.active,
                )
                updated += 1
            else:
                # Create new metric
                await repo.create(
                    code=metric_data.code,
                    name=metric_data.name,
                    name_ru=metric_data.name_ru,
                    description=metric_data.description,
                    unit=metric_data.unit,
                    min_value=min_val,
                    max_value=max_val,
                    active=metric_data.active,
                )
                created += 1
        except Exception as e:
            errors.append(ImportErrorSchema(row=idx, error=str(e)))

    return ImportResultResponse(created=created, updated=updated, errors=errors)
