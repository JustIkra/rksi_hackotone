"""
Repository layer for MetricSynonym data access.

Handles all database operations for metric synonyms.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MetricDef, MetricSynonym


class MetricSynonymRepository:
    """Repository for metric synonym database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, synonym_id: int) -> MetricSynonym | None:
        """
        Get a synonym by ID.

        Args:
            synonym_id: ID of the synonym

        Returns:
            MetricSynonym if found, None otherwise
        """
        result = await self.db.execute(
            select(MetricSynonym).where(MetricSynonym.id == synonym_id)
        )
        return result.scalar_one_or_none()

    async def get_by_metric_def_id(self, metric_def_id: UUID) -> list[MetricSynonym]:
        """
        Get all synonyms for a metric definition.

        Args:
            metric_def_id: ID of the metric definition

        Returns:
            List of MetricSynonym instances
        """
        result = await self.db.execute(
            select(MetricSynonym).where(MetricSynonym.metric_def_id == metric_def_id)
        )
        return list(result.scalars().all())

    async def get_by_synonym_text(self, synonym: str) -> MetricSynonym | None:
        """
        Find a synonym by its text (case-sensitive).

        Args:
            synonym: Synonym text to search for

        Returns:
            MetricSynonym if found, None otherwise
        """
        result = await self.db.execute(
            select(MetricSynonym).where(MetricSynonym.synonym == synonym)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        metric_def_id: UUID,
        synonym: str,
        created_by_id: UUID | None = None,
    ) -> MetricSynonym:
        """
        Create a new synonym for a metric definition.

        Args:
            metric_def_id: UUID of the metric definition
            synonym: Synonym text (will be stripped)
            created_by_id: UUID of the user who created the synonym

        Returns:
            Created MetricSynonym instance
        """
        db_synonym = MetricSynonym(
            metric_def_id=metric_def_id,
            synonym=synonym.strip(),
            created_by_id=created_by_id,
        )
        self.db.add(db_synonym)
        await self.db.commit()
        await self.db.refresh(db_synonym)
        return db_synonym

    async def update(self, synonym_id: int, new_synonym: str) -> MetricSynonym | None:
        """
        Update a synonym's text.

        Args:
            synonym_id: ID of the synonym to update
            new_synonym: New synonym text (will be stripped)

        Returns:
            Updated MetricSynonym if found, None otherwise
        """
        db_synonym = await self.get_by_id(synonym_id)
        if db_synonym:
            db_synonym.synonym = new_synonym.strip()
            await self.db.commit()
            await self.db.refresh(db_synonym)
        return db_synonym

    async def delete(self, synonym_id: int) -> bool:
        """
        Delete a synonym.

        Args:
            synonym_id: ID of the synonym to delete

        Returns:
            True if deleted, False if not found
        """
        db_synonym = await self.get_by_id(synonym_id)
        if db_synonym:
            await self.db.delete(db_synonym)
            await self.db.commit()
            return True
        return False

    async def check_synonym_exists(
        self, synonym: str, exclude_id: int | None = None
    ) -> bool:
        """
        Check if a synonym already exists globally (case-insensitive).

        Uses Python casefold() for proper Unicode case-insensitive comparison
        since PostgreSQL LOWER() doesn't handle Cyrillic correctly without proper locale.

        Args:
            synonym: Synonym text to check (will be stripped and casefolded)
            exclude_id: Optional synonym ID to exclude (for updates)

        Returns:
            True if synonym exists, False otherwise
        """
        normalized = synonym.strip().casefold()
        query = select(MetricSynonym)
        if exclude_id:
            query = query.where(MetricSynonym.id != exclude_id)
        result = await self.db.execute(query)
        for existing in result.scalars():
            if existing.synonym.casefold() == normalized:
                return True
        return False

    async def find_existing_synonym_with_metric(
        self, synonym: str, exclude_id: int | None = None
    ) -> tuple[MetricSynonym | None, MetricDef | None]:
        """
        Find existing synonym with its metric definition (case-insensitive).

        Args:
            synonym: Synonym text to check
            exclude_id: Optional synonym ID to exclude (for updates)

        Returns:
            Tuple of (MetricSynonym, MetricDef) if found, (None, None) otherwise
        """
        from sqlalchemy.orm import selectinload

        normalized = synonym.strip().casefold()
        query = select(MetricSynonym).options(selectinload(MetricSynonym.metric_def))
        if exclude_id:
            query = query.where(MetricSynonym.id != exclude_id)
        result = await self.db.execute(query)
        for existing in result.scalars():
            if existing.synonym.casefold() == normalized:
                return existing, existing.metric_def
        return None, None

    async def check_conflicts_with_metric_names(self, synonym: str) -> bool:
        """
        Check if a synonym conflicts with any metric_def name or name_ru (case-insensitive).

        Uses Python casefold() for proper Unicode case-insensitive comparison
        since PostgreSQL LOWER() doesn't handle Cyrillic correctly without proper locale.

        Args:
            synonym: Synonym text to check (will be stripped and casefolded)

        Returns:
            True if conflict exists, False otherwise
        """
        normalized = synonym.strip().casefold()
        result = await self.db.execute(select(MetricDef.name, MetricDef.name_ru))
        for name, name_ru in result:
            if name and name.casefold() == normalized:
                return True
            if name_ru and name_ru.casefold() == normalized:
                return True
        return False
