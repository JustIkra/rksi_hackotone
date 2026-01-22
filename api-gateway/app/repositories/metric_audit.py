"""
Repository layer for MetricAuditLog data access.

Handles all database operations for metric audit logging.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import MetricAuditLog


class MetricAuditLogRepository:
    """Repository for metric audit log database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        user_id: UUID | None,
        action: str,
        metric_codes: list[str],
        affected_counts: dict | None = None,
    ) -> MetricAuditLog:
        """
        Create a new audit log entry.

        Args:
            user_id: UUID of the user performing the action (can be None for system actions)
            action: Type of action (e.g., "bulk_delete", "delete")
            metric_codes: List of affected metric codes
            affected_counts: Optional dict with counts of affected records

        Returns:
            Created MetricAuditLog instance
        """
        audit_log = MetricAuditLog(
            user_id=user_id,
            action=action,
            metric_codes=metric_codes,
            affected_counts=affected_counts,
        )
        self.db.add(audit_log)
        await self.db.commit()
        await self.db.refresh(audit_log)
        return audit_log

    async def get_by_id(self, audit_id: int) -> MetricAuditLog | None:
        """
        Get an audit log entry by ID.

        Args:
            audit_id: ID of the audit log entry

        Returns:
            MetricAuditLog if found, None otherwise
        """
        result = await self.db.execute(
            select(MetricAuditLog)
            .options(selectinload(MetricAuditLog.user))
            .where(MetricAuditLog.id == audit_id)
        )
        return result.scalar_one_or_none()

    async def list_by_date_range(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        action: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[MetricAuditLog], int]:
        """
        List audit log entries within a date range.

        Args:
            start: Start datetime (inclusive)
            end: End datetime (inclusive)
            action: Filter by action type
            limit: Maximum number of entries to return
            offset: Number of entries to skip

        Returns:
            Tuple of (list of MetricAuditLog instances, total count)
        """
        stmt = select(MetricAuditLog).options(selectinload(MetricAuditLog.user))

        # Apply filters
        if start:
            stmt = stmt.where(MetricAuditLog.timestamp >= start)
        if end:
            stmt = stmt.where(MetricAuditLog.timestamp <= end)
        if action:
            stmt = stmt.where(MetricAuditLog.action == action)

        # Get total count
        count_stmt = select(func.count(MetricAuditLog.id))
        if start:
            count_stmt = count_stmt.where(MetricAuditLog.timestamp >= start)
        if end:
            count_stmt = count_stmt.where(MetricAuditLog.timestamp <= end)
        if action:
            count_stmt = count_stmt.where(MetricAuditLog.action == action)

        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar() or 0

        # Apply ordering and pagination
        stmt = stmt.order_by(MetricAuditLog.timestamp.desc())
        stmt = stmt.offset(offset).limit(limit)

        result = await self.db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def list_by_user(
        self,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MetricAuditLog]:
        """
        List audit log entries for a specific user.

        Args:
            user_id: UUID of the user
            limit: Maximum number of entries to return
            offset: Number of entries to skip

        Returns:
            List of MetricAuditLog instances
        """
        stmt = (
            select(MetricAuditLog)
            .options(selectinload(MetricAuditLog.user))
            .where(MetricAuditLog.user_id == user_id)
            .order_by(MetricAuditLog.timestamp.desc())
            .offset(offset)
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_action_types(self) -> list[str]:
        """
        Get all distinct action types in the audit log.

        Returns:
            List of unique action types
        """
        stmt = select(MetricAuditLog.action).distinct()
        result = await self.db.execute(stmt)
        return [row[0] for row in result.all()]
