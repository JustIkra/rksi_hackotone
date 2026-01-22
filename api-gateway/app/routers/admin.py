"""
Admin router.

Administrative endpoints for user management, audit logs, and AI metric generation.
Requires ADMIN role for all operations.
"""

import base64
import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import require_admin
from app.db.models import MetricCategory, MetricDef, User
from app.db.session import get_db
from app.repositories.metric_audit import MetricAuditLogRepository
from app.schemas.audit import (
    ActionTypesResponse,
    AuditLogEntry,
    AuditLogListResponse,
    AuditLogUserInfo,
)
from app.schemas.auth import MessageResponse, UserResponse
from app.schemas.metric_generation import (
    AIRationale,
    GeneratedMetricResponse,
    GenerationTaskResponse,
    MetricModerationRequest,
    ModerationResultResponse,
    ModerationStatus,
    PendingMetricsResponse,
    TaskProgressResponse,
    TaskStatus,
)
from app.services.auth import (
    approve_user,
    delete_user,
    get_user_by_id,
    list_all_users,
    list_pending_users,
    make_user_admin,
    revoke_user_admin,
)
from app.tasks.metric_generation import generate_metrics_from_document

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/users", response_model=list[UserResponse])
async def get_all_users(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    List all users in the system.

    **Requires:** ADMIN role

    **Returns:** List of users ordered by registration date

    **Errors:**
    - 401: Not authenticated
    - 403: Not an admin
    """
    users = await list_all_users(db)
    return [UserResponse.model_validate(user) for user in users]


@router.get("/pending-users", response_model=list[UserResponse])
async def get_pending_users(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    List all users with PENDING status awaiting approval.

    **Requires:** ADMIN role

    **Returns:** List of pending users ordered by registration date

    **Errors:**
    - 401: Not authenticated
    - 403: Not an admin
    """
    users = await list_pending_users(db)
    return [UserResponse.model_validate(user) for user in users]


@router.post("/approve/{user_id}", response_model=UserResponse)
async def approve_user_endpoint(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Approve a pending user (change status to ACTIVE).

    **Requires:** ADMIN role

    **Flow:**
    1. Admin views pending users via `/admin/pending-users`
    2. Admin approves a user by their UUID
    3. User status changes from PENDING → ACTIVE
    4. User can now log in and access the system

    **Errors:**
    - 400: User not found, already approved, or disabled
    - 401: Not authenticated
    - 403: Not an admin
    """
    try:
        user = await approve_user(db, user_id)
        logger.info(f"Admin {admin.email} action: approve user {user_id} ({user.email})")
        return UserResponse.model_validate(user)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.post("/make-admin/{user_id}", response_model=UserResponse)
async def make_admin_endpoint(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Grant ADMIN role to a user.

    **Requires:** ADMIN role

    **Flow:**
    1. Admin views all users via `/admin/users`
    2. Admin selects a user and calls this endpoint
    3. User role changes from USER → ADMIN

    **Errors:**
    - 400: User not found or already admin
    - 401: Not authenticated
    - 403: Not an admin
    """
    try:
        user = await make_user_admin(db, user_id)
        logger.info(f"Admin {admin.email} action: make-admin user {user_id} ({user.email})")
        return UserResponse.model_validate(user)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.post("/revoke-admin/{user_id}", response_model=UserResponse)
async def revoke_admin_endpoint(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Revoke ADMIN role from a user (change to USER).

    **Requires:** ADMIN role

    **Flow:**
    1. Admin views all users via `/admin/users`
    2. Admin selects an admin user and calls this endpoint
    3. User role changes from ADMIN → USER

    **Notes:**
    - Admin cannot revoke their own admin rights to prevent accidental lockout

    **Errors:**
    - 400: User not found, not an admin, or trying to revoke self
    - 401: Not authenticated
    - 403: Not an admin
    """
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot revoke your own administrator privileges.",
        )

    try:
        user = await revoke_user_admin(db, user_id)
        logger.info(f"Admin {admin.email} action: revoke-admin user {user_id} ({user.email})")
        return UserResponse.model_validate(user)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.delete("/users/{user_id}", response_model=MessageResponse)
async def delete_user_endpoint(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Permanently delete a user from the system.

    **Requires:** ADMIN role

    **Notes:**
    - Admin cannot delete their own account to prevent accidental lockout

    **Errors:**
    - 400: User not found or trying to delete self
    - 401: Not authenticated
    - 403: Not an admin
    """
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own administrator account.",
        )

    try:
        user = await get_user_by_id(db, user_id)
        user_email = user.email if user else "unknown"
        await delete_user(db, user_id)
        logger.info(f"Admin {admin.email} action: delete user {user_id} ({user_email})")
        return MessageResponse(message="User deleted successfully")

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


# ==================== Audit Log Endpoints ====================


@router.get("/audit-log", response_model=AuditLogListResponse)
async def get_audit_log(
    start_date: datetime | None = Query(None, description="Filter from this date (inclusive)"),
    end_date: datetime | None = Query(None, description="Filter until this date (inclusive)"),
    action: str | None = Query(None, description="Filter by action type"),
    limit: int = Query(50, ge=1, le=100, description="Maximum items to return"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> AuditLogListResponse:
    """
    List audit log entries with optional filtering.

    **Requires:** ADMIN role

    **Query Parameters:**
    - start_date: Filter entries from this date
    - end_date: Filter entries until this date
    - action: Filter by action type (e.g., "bulk_delete")
    - limit: Maximum entries to return (1-100, default 50)
    - offset: Number of entries to skip for pagination

    **Returns:** Paginated list of audit log entries
    """
    repo = MetricAuditLogRepository(db)
    items, total = await repo.list_by_date_range(
        start=start_date,
        end=end_date,
        action=action,
        limit=limit,
        offset=offset,
    )

    # Convert to response format
    entries = []
    for item in items:
        user_info = None
        if item.user:
            user_info = AuditLogUserInfo(
                id=item.user.id,
                email=item.user.email,
                full_name=item.user.full_name,
            )

        entries.append(
            AuditLogEntry(
                id=item.id,
                user_id=item.user_id,
                user=user_info,
                action=item.action,
                metric_codes=item.metric_codes,
                affected_counts=item.affected_counts,
                timestamp=item.timestamp,
            )
        )

    return AuditLogListResponse(
        items=entries,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/audit-log/actions", response_model=ActionTypesResponse)
async def get_audit_action_types(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> ActionTypesResponse:
    """
    Get all distinct action types available for filtering.

    **Requires:** ADMIN role

    **Returns:** List of unique action types in the audit log
    """
    repo = MetricAuditLogRepository(db)
    actions = await repo.get_action_types()
    return ActionTypesResponse(actions=actions)


# ==================== Metric Generation Endpoints ====================


def _check_metric_generation_enabled() -> None:
    """Check if metric generation feature is enabled."""
    if not settings.enable_metric_generation:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Metric generation feature is disabled. Set ENABLE_METRIC_GENERATION=true in .env",
        )


@router.post("/metrics/generate", response_model=GenerationTaskResponse)
async def start_metric_generation(
    file: UploadFile = File(..., description="PDF or DOCX file to process"),
    _admin: User = Depends(require_admin),
) -> GenerationTaskResponse:
    """
    Start AI-powered metric generation from uploaded PDF/DOCX file.

    **Requires:** ADMIN role + ENABLE_METRIC_GENERATION=true

    **Flow:**
    1. Upload PDF/DOCX file
    2. Receive task_id for tracking progress
    3. Poll status endpoint until complete
    4. Review generated metrics in pending list

    **Supported formats:**
    - PDF (preferred)
    - DOCX (converted to PDF internally)

    **Returns:** Task ID for progress tracking
    """
    _check_metric_generation_enabled()

    # Validate file type
    filename = file.filename or "document"
    content_type = file.content_type or ""

    if not (
        filename.lower().endswith(".pdf")
        or filename.lower().endswith(".docx")
        or "pdf" in content_type.lower()
        or "docx" in content_type.lower()
        or "word" in content_type.lower()
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF and DOCX files are supported",
        )

    # Read file content
    file_data = await file.read()
    if not file_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file uploaded",
        )

    # Start Celery task
    file_data_b64 = base64.b64encode(file_data).decode("utf-8")
    task = generate_metrics_from_document.delay(file_data_b64, filename)

    logger.info(f"Started metric generation task {task.id} for {filename}")

    return GenerationTaskResponse(
        task_id=task.id,
        message=f"Processing started for {filename}",
    )


@router.get("/metrics/generate/{task_id}/status", response_model=TaskProgressResponse)
async def get_generation_status(
    task_id: str,
    _admin: User = Depends(require_admin),
) -> TaskProgressResponse:
    """
    Get status and progress of metric generation task.

    **Requires:** ADMIN role

    **Poll this endpoint** to track progress:
    - status: pending, processing, completed, failed
    - progress: 0-100 percentage
    - current_step: Human-readable step description
    - result: Final result when completed

    **Recommended polling interval:** 2-5 seconds
    """
    _check_metric_generation_enabled()

    from redis import Redis

    try:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        data = redis.get(f"metric_gen:{task_id}")

        if data:
            import json

            progress_data = json.loads(data)
            return TaskProgressResponse(
                task_id=task_id,
                status=TaskStatus(progress_data.get("status", "pending")),
                progress=progress_data.get("progress", 0),
                current_step=progress_data.get("current_step"),
                total_pages=progress_data.get("total_pages"),
                processed_pages=progress_data.get("processed_pages"),
                metrics_found=progress_data.get("metrics_found"),
                error=progress_data.get("error"),
                result=progress_data.get("result"),
            )
    except Exception as e:
        logger.warning(f"Failed to get progress from Redis: {e}")

    # Fallback to Celery task state
    from app.core.celery_app import celery_app

    result = celery_app.AsyncResult(task_id)

    if result.state == "PENDING":
        return TaskProgressResponse(task_id=task_id, status=TaskStatus.PENDING, progress=0)
    elif result.state == "STARTED":
        return TaskProgressResponse(
            task_id=task_id, status=TaskStatus.PROCESSING, progress=0
        )
    elif result.state == "SUCCESS":
        return TaskProgressResponse(
            task_id=task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            result=result.result,
        )
    elif result.state == "FAILURE":
        return TaskProgressResponse(
            task_id=task_id, status=TaskStatus.FAILED, error=str(result.result)
        )
    else:
        return TaskProgressResponse(task_id=task_id, status=TaskStatus.PENDING, progress=0)


@router.get("/metrics/pending", response_model=PendingMetricsResponse)
async def get_pending_metrics(
    limit: int = Query(50, ge=1, le=100, description="Maximum items to return"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> PendingMetricsResponse:
    """
    Get list of AI-generated metrics pending moderation.

    **Requires:** ADMIN role

    **Returns:** Paginated list of metrics with status=PENDING
    """
    _check_metric_generation_enabled()

    # Count total
    count_result = await db.execute(
        select(MetricDef)
        .where(MetricDef.moderation_status == "PENDING")
    )
    total = len(count_result.scalars().all())

    # Get paginated items
    result = await db.execute(
        select(MetricDef)
        .where(MetricDef.moderation_status == "PENDING")
        .order_by(MetricDef.sort_order.desc())
        .limit(limit)
        .offset(offset)
    )
    metrics = result.scalars().all()

    # Build response
    items = []
    for m in metrics:
        # Get category info
        category_code = None
        category_name = None
        if m.category_id:
            cat_result = await db.execute(
                select(MetricCategory).where(MetricCategory.id == m.category_id)
            )
            category = cat_result.scalars().first()
            if category:
                category_code = category.code
                category_name = category.name

        # Parse AI rationale
        ai_rationale = None
        if m.ai_rationale:
            ai_rationale = AIRationale(**m.ai_rationale)

        items.append(
            GeneratedMetricResponse(
                id=m.id,
                code=m.code,
                name=m.name,
                name_ru=m.name_ru,
                description=m.description,
                category_code=category_code,
                category_name=category_name,
                moderation_status=ModerationStatus(m.moderation_status),
                ai_rationale=ai_rationale,
            )
        )

    return PendingMetricsResponse(items=items, total=total)


@router.post("/metrics/{metric_id}/approve", response_model=ModerationResultResponse)
async def approve_metric(
    metric_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> ModerationResultResponse:
    """
    Approve a pending AI-generated metric.

    **Requires:** ADMIN role

    **Flow:**
    1. Metric status changes: PENDING → APPROVED
    2. Metric becomes active and visible in the system
    """
    _check_metric_generation_enabled()

    result = await db.execute(select(MetricDef).where(MetricDef.id == metric_id))
    metric = result.scalars().first()

    if not metric:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Metric not found",
        )

    if metric.moderation_status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Metric is not pending moderation (status: {metric.moderation_status})",
        )

    metric.moderation_status = "APPROVED"
    await db.commit()

    # Trigger background embedding indexing for the approved metric
    from app.tasks.embedding import index_metric_task

    index_metric_task.delay(str(metric.id))

    logger.info(f"Admin {admin.email} approved metric {metric.code}")

    return ModerationResultResponse(
        id=metric.id,
        code=metric.code,
        name=metric.name,
        moderation_status=ModerationStatus.APPROVED,
        message="Metric approved successfully (indexing in background)",
    )


@router.post("/metrics/{metric_id}/reject", response_model=ModerationResultResponse)
async def reject_metric(
    metric_id: UUID,
    body: MetricModerationRequest | None = None,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> ModerationResultResponse:
    """
    Reject a pending AI-generated metric.

    **Requires:** ADMIN role

    **Flow:**
    1. Metric status changes: PENDING → REJECTED
    2. Metric is hidden from active list

    **Body (optional):**
    - reason: Reason for rejection (stored for audit)
    """
    _check_metric_generation_enabled()

    result = await db.execute(select(MetricDef).where(MetricDef.id == metric_id))
    metric = result.scalars().first()

    if not metric:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Metric not found",
        )

    if metric.moderation_status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Metric is not pending moderation (status: {metric.moderation_status})",
        )

    metric.moderation_status = "REJECTED"
    metric.active = False

    # Store rejection reason in notes if provided
    if body and body.reason:
        if metric.ai_rationale:
            metric.ai_rationale["rejection_reason"] = body.reason
        else:
            metric.ai_rationale = {"rejection_reason": body.reason}

    await db.commit()

    logger.info(f"Admin {admin.email} rejected metric {metric.code}")

    return ModerationResultResponse(
        id=metric.id,
        code=metric.code,
        name=metric.name,
        moderation_status=ModerationStatus.REJECTED,
        message="Metric rejected",
    )


# ==================== Embedding / Semantic Search Endpoints ====================


@router.post("/metrics/reindex", summary="Full reindex of all metrics")
async def reindex_all_metrics(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict:
    """
    Reindex all APPROVED metrics for semantic search.

    **Requires:** ADMIN role

    **Use cases:**
    - Initial setup after enabling semantic search
    - After bulk import of metrics
    - To rebuild index after model change

    **Note:** This operation may take several minutes for large datasets.
    Embeddings are generated via OpenRouter API.

    **Returns:**
    - indexed: Number of metrics successfully indexed
    - errors: Number of failed indexing attempts
    - total: Total APPROVED metrics in system
    """
    from app.services.embedding import EmbeddingService

    service = EmbeddingService(db)
    try:
        result = await service.index_all_metrics()
        logger.info(
            f"Admin {admin.email} completed full reindex: "
            f"{result['indexed']}/{result['total']} metrics indexed"
        )
        return {
            "status": "success",
            "indexed": result["indexed"],
            "errors": result["errors"],
            "total": result["total"],
        }
    finally:
        await service.close()


@router.post("/metrics/{metric_id}/reindex", summary="Reindex single metric")
async def reindex_single_metric(
    metric_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict:
    """
    Reindex a specific metric for semantic search.

    **Requires:** ADMIN role

    **Use cases:**
    - After updating metric name/description
    - After adding synonyms
    - To fix missing embedding

    **Returns:** Success status with metric_id
    """
    from app.services.embedding import EmbeddingService

    service = EmbeddingService(db)
    try:
        await service.index_metric(metric_id)
        await db.commit()
        logger.info(f"Admin {admin.email} reindexed metric {metric_id}")
        return {"status": "success", "metric_id": str(metric_id)}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    finally:
        await service.close()


@router.post("/metrics/search-similar", summary="Search similar metrics")
async def search_similar_metrics(
    query: str = Query(..., min_length=1, max_length=1000, description="Text to search for similar metrics"),
    top_k: int = Query(5, ge=1, le=20, description="Number of results"),
    threshold: float = Query(0.5, ge=0.0, le=1.0, description="Minimum similarity"),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[dict]:
    """
    Find metrics similar to the given text (for debugging/testing).

    **Requires:** ADMIN role

    **Use cases:**
    - Test semantic search quality
    - Debug matching issues
    - Explore metric relationships

    **Parameters:**
    - query: Text to search for (e.g., metric name from document)
    - top_k: Maximum number of results (1-20)
    - threshold: Minimum cosine similarity score (0.0-1.0)

    **Returns:** List of similar metrics with similarity scores
    """
    from app.services.embedding import EmbeddingService

    service = EmbeddingService(db)
    try:
        results = await service.find_similar(query, top_k=top_k, threshold=threshold)
        return results
    finally:
        await service.close()


@router.get("/metrics/embedding-stats", summary="Get embedding statistics")
async def get_embedding_stats(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict:
    """
    Get statistics about the metric embedding index.

    **Requires:** ADMIN role

    **Returns:**
    - total_approved_metrics: Count of APPROVED metrics
    - total_embeddings: Count of indexed embeddings
    - missing_embeddings: Metrics without embeddings
    - coverage_percent: Percentage of metrics indexed
    - model: Embedding model being used
    - dimensions: Vector dimensions
    """
    from app.services.embedding import EmbeddingService

    service = EmbeddingService(db)
    try:
        stats = await service.get_embedding_stats()
        return stats
    finally:
        await service.close()
