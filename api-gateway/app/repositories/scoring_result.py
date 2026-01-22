"""
Repository layer for ScoringResult data access.

Handles all database operations for scoring results.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import ScoringResult


class ScoringResultRepository:
    """Repository for scoring result database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        participant_id: UUID,
        weight_table_id: UUID,
        score_pct: Decimal,
        strengths: list[dict] | None = None,
        dev_areas: list[dict] | None = None,
        compute_notes: str | None = None,
    ) -> ScoringResult:
        """
        Create a new scoring result.

        Args:
            participant_id: UUID of the participant
            weight_table_id: UUID of the weight table used
            score_pct: Calculated score as percentage (0-100)
            strengths: Optional JSONB array of strengths
            dev_areas: Optional JSONB array of development areas
            compute_notes: Optional notes about the computation

        Returns:
            Created ScoringResult instance
        """
        scoring_result = ScoringResult(
            participant_id=participant_id,
            weight_table_id=weight_table_id,
            score_pct=score_pct,
            strengths=strengths,
            dev_areas=dev_areas,
            compute_notes=compute_notes,
        )
        self.db.add(scoring_result)
        await self.db.commit()
        await self.db.refresh(scoring_result)
        return scoring_result

    async def get_by_id(self, scoring_result_id: UUID) -> ScoringResult | None:
        """
        Get a scoring result by ID.

        Args:
            scoring_result_id: UUID of the scoring result

        Returns:
            ScoringResult if found, None otherwise
        """
        result = await self.db.execute(
            select(ScoringResult)
            .options(
                selectinload(ScoringResult.participant),
                selectinload(ScoringResult.weight_table),
            )
            .where(ScoringResult.id == scoring_result_id)
        )
        return result.scalar_one_or_none()

    async def list_by_participant(
        self, participant_id: UUID, limit: int = 10
    ) -> list[ScoringResult]:
        """
        List scoring results for a participant.

        Args:
            participant_id: UUID of the participant
            limit: Maximum number of results to return

        Returns:
            List of ScoringResult instances, ordered by computed_at DESC
        """
        from app.db.models import WeightTable

        result = await self.db.execute(
            select(ScoringResult)
            .options(
                selectinload(ScoringResult.participant),
                selectinload(ScoringResult.weight_table).selectinload(WeightTable.prof_activity),
            )
            .where(ScoringResult.participant_id == participant_id)
            .order_by(ScoringResult.computed_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_latest_by_participant_and_weight_table(
        self, participant_id: UUID, weight_table_id: UUID
    ) -> ScoringResult | None:
        """
        Get the latest scoring result for a participant and weight table.

        Args:
            participant_id: UUID of the participant
            weight_table_id: UUID of the weight table

        Returns:
            Most recent ScoringResult if found, None otherwise
        """
        result = await self.db.execute(
            select(ScoringResult)
            .options(
                selectinload(ScoringResult.participant),
                selectinload(ScoringResult.weight_table),
            )
            .where(
                ScoringResult.participant_id == participant_id,
                ScoringResult.weight_table_id == weight_table_id,
            )
            .order_by(ScoringResult.computed_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def delete(self, scoring_result_id: UUID) -> bool:
        """
        Delete a scoring result.

        Args:
            scoring_result_id: UUID of the scoring result

        Returns:
            True if deleted, False if not found
        """
        scoring_result = await self.get_by_id(scoring_result_id)
        if not scoring_result:
            return False

        await self.db.delete(scoring_result)
        await self.db.commit()
        return True
