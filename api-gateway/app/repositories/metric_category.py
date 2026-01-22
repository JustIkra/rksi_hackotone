"""
Repository layer for Metric Category data access.

Handles all database operations for metric categories.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import ExtractedMetric, MetricCategory, MetricDef


class MetricCategoryRepository:
    """Repository for metric category database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        code: str,
        name: str,
        description: str | None = None,
        sort_order: int = 0,
    ) -> MetricCategory:
        """
        Create a new metric category.

        Args:
            code: Unique category code
            name: Category name
            description: Optional description
            sort_order: Sort order for display

        Returns:
            Created MetricCategory instance
        """
        category = MetricCategory(
            code=code,
            name=name,
            description=description,
            sort_order=sort_order,
        )
        self.db.add(category)
        await self.db.commit()
        await self.db.refresh(category)
        return category

    async def get_by_id(self, category_id: UUID) -> MetricCategory | None:
        """
        Get a metric category by ID.

        Args:
            category_id: UUID of the metric category

        Returns:
            MetricCategory if found, None otherwise
        """
        result = await self.db.execute(
            select(MetricCategory).where(MetricCategory.id == category_id)
        )
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> MetricCategory | None:
        """
        Get a metric category by code.

        Args:
            code: Unique category code

        Returns:
            MetricCategory if found, None otherwise
        """
        result = await self.db.execute(
            select(MetricCategory).where(MetricCategory.code == code)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[MetricCategory]:
        """
        List all metric categories sorted by sort_order.

        Returns:
            List of MetricCategory instances
        """
        result = await self.db.execute(
            select(MetricCategory)
            .options(selectinload(MetricCategory.metrics))
            .order_by(MetricCategory.sort_order, MetricCategory.code)
        )
        return list(result.scalars().all())

    async def list_with_metrics_count(self) -> list[tuple[MetricCategory, int]]:
        """
        List all metric categories with metrics count.

        Returns:
            List of tuples (MetricCategory, metrics_count)
        """
        # Subquery for counting metrics
        metrics_count_subq = (
            select(MetricDef.category_id, func.count(MetricDef.id).label("count"))
            .group_by(MetricDef.category_id)
            .subquery()
        )

        # Main query with left join
        stmt = (
            select(MetricCategory, func.coalesce(metrics_count_subq.c.count, 0))
            .outerjoin(
                metrics_count_subq,
                MetricCategory.id == metrics_count_subq.c.category_id
            )
            .order_by(MetricCategory.sort_order, MetricCategory.code)
        )

        result = await self.db.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def update(
        self,
        category_id: UUID,
        name: str | None = None,
        description: str | None = None,
        sort_order: int | None = None,
    ) -> MetricCategory | None:
        """
        Update a metric category.

        Args:
            category_id: UUID of the metric category
            name: New name (if provided)
            description: New description (if provided)
            sort_order: New sort order (if provided)

        Returns:
            Updated MetricCategory if found, None otherwise
        """
        category = await self.get_by_id(category_id)
        if not category:
            return None

        if name is not None:
            category.name = name
        if description is not None:
            category.description = description
        if sort_order is not None:
            category.sort_order = sort_order

        await self.db.commit()
        await self.db.refresh(category)
        return category

    async def delete(self, category_id: UUID) -> bool:
        """
        Delete a metric category.

        Note: This will also delete all metrics in this category due to CASCADE.

        Args:
            category_id: UUID of the metric category

        Returns:
            True if deleted, False if not found
        """
        category = await self.get_by_id(category_id)
        if not category:
            return False

        await self.db.delete(category)
        await self.db.commit()
        return True

    async def get_metrics_count(self, category_id: UUID) -> int:
        """
        Get the count of metrics in a category.

        Args:
            category_id: UUID of the metric category

        Returns:
            Number of metrics in the category
        """
        result = await self.db.execute(
            select(func.count(MetricDef.id)).where(MetricDef.category_id == category_id)
        )
        return result.scalar() or 0

    async def get_usage_stats(self, category_id: UUID) -> dict:
        """
        Get usage statistics for a category before deletion.

        Args:
            category_id: UUID of the category

        Returns:
            Dict with usage statistics
        """
        # Count metrics in this category
        metrics_stmt = select(func.count(MetricDef.id)).where(
            MetricDef.category_id == category_id
        )
        metrics_result = await self.db.execute(metrics_stmt)
        metrics_count = metrics_result.scalar() or 0

        # Count extracted metrics for metrics in this category
        extracted_stmt = (
            select(func.count(ExtractedMetric.id))
            .join(MetricDef, ExtractedMetric.metric_def_id == MetricDef.id)
            .where(MetricDef.category_id == category_id)
        )
        extracted_result = await self.db.execute(extracted_stmt)
        extracted_count = extracted_result.scalar() or 0

        return {
            "category_id": category_id,
            "metrics_count": metrics_count,
            "extracted_metrics_count": extracted_count,
        }

    async def get_uncategorized_metrics_count(self) -> int:
        """
        Get count of metrics without a category.

        Returns:
            Number of metrics with category_id = NULL
        """
        stmt = select(func.count(MetricDef.id)).where(MetricDef.category_id.is_(None))
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def reorder_single(
        self, category_id: UUID, target_position: int
    ) -> list[MetricCategory]:
        """
        Reorder a single category by moving it to a target position.

        Uses gap algorithm (sort_order increments of 10) for efficient reordering.
        Performs soft validation with auto-correction of target_position.

        Args:
            category_id: UUID of the category to move
            target_position: Target position (0-based index), auto-corrected if out of bounds

        Returns:
            List of all MetricCategory instances sorted by new sort_order

        Raises:
            ValueError: If category_id is not found
        """
        # Fetch all categories ordered by sort_order
        result = await self.db.execute(
            select(MetricCategory).order_by(MetricCategory.sort_order, MetricCategory.code)
        )
        categories = list(result.scalars().all())

        if not categories:
            raise ValueError(f"Category not found: {category_id}")

        # Find the category to move
        category_to_move = None
        current_idx = -1
        for idx, cat in enumerate(categories):
            if cat.id == category_id:
                category_to_move = cat
                current_idx = idx
                break

        if category_to_move is None:
            raise ValueError(f"Category not found: {category_id}")

        # Auto-correct target_position (soft validation)
        max_idx = len(categories) - 1
        target_position = max(0, min(target_position, max_idx))

        # If already at target position, return as-is
        if current_idx == target_position:
            return categories

        # Remove from current position and insert at target
        categories.pop(current_idx)
        categories.insert(target_position, category_to_move)

        # Recalculate sort_order for all (gap = 10 for potential future insertions)
        for idx, cat in enumerate(categories):
            cat.sort_order = idx * 10

        await self.db.commit()

        # Refresh all categories
        for cat in categories:
            await self.db.refresh(cat)

        return categories
