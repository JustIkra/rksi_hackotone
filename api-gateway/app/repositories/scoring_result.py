"""
Repository layer for ScoringResult data access.

Handles all database operations for participant scoring results.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import ScoringResult, WeightTable


class ScoringResultRepository:
    """Repository for scoring result database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_participant_and_weight_table(
        self, participant_id: UUID, weight_table_id: UUID
    ) -> ScoringResult | None:
        """Get scoring result for a specific participant and weight table."""
        result = await self.db.execute(
            select(ScoringResult)
            .options(selectinload(ScoringResult.weight_table).selectinload(WeightTable.prof_activity))
            .where(
                and_(
                    ScoringResult.participant_id == participant_id,
                    ScoringResult.weight_table_id == weight_table_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_by_participant(self, participant_id: UUID) -> list[ScoringResult]:
        """List all scoring results for a participant."""
        result = await self.db.execute(
            select(ScoringResult)
            .options(selectinload(ScoringResult.weight_table).selectinload(WeightTable.prof_activity))
            .where(ScoringResult.participant_id == participant_id)
            .order_by(ScoringResult.computed_at.desc())
        )
        return list(result.scalars().all())

    async def list_by_participants_and_weight_table(
        self, participant_ids: list[UUID], weight_table_id: UUID
    ) -> dict[UUID, ScoringResult]:
        """Batch fetch scoring results for multiple participants and one weight table."""
        if not participant_ids:
            return {}
        result = await self.db.execute(
            select(ScoringResult).where(
                and_(
                    ScoringResult.participant_id.in_(participant_ids),
                    ScoringResult.weight_table_id == weight_table_id,
                )
            )
        )
        return {sr.participant_id: sr for sr in result.scalars().all()}

    async def list_by_weight_table(self, weight_table_id: UUID) -> list[ScoringResult]:
        """List all scoring results for a weight table."""
        result = await self.db.execute(
            select(ScoringResult)
            .where(ScoringResult.weight_table_id == weight_table_id)
            .order_by(ScoringResult.final_score.desc())
        )
        return list(result.scalars().all())

    async def upsert(
        self,
        participant_id: UUID,
        weight_table_id: UUID,
        base_score: Decimal,
        penalty_multiplier: Decimal,
        final_score: Decimal,
        penalties_applied: list[dict[str, Any]] | None,
        metrics_used: list[dict[str, Any]] | None,
    ) -> ScoringResult:
        """Create or update a scoring result."""
        existing = await self.get_by_participant_and_weight_table(participant_id, weight_table_id)

        if existing:
            existing.base_score = base_score
            existing.penalty_multiplier = penalty_multiplier
            existing.final_score = final_score
            existing.penalties_applied = penalties_applied
            existing.metrics_used = metrics_used
            existing.computed_at = datetime.now(UTC)
            await self.db.commit()
            await self.db.refresh(existing)
            return existing
        else:
            new_result = ScoringResult(
                participant_id=participant_id,
                weight_table_id=weight_table_id,
                base_score=base_score,
                penalty_multiplier=penalty_multiplier,
                final_score=final_score,
                penalties_applied=penalties_applied,
                metrics_used=metrics_used,
            )
            self.db.add(new_result)
            await self.db.commit()
            await self.db.refresh(new_result)
            return new_result

    async def delete_by_participant(self, participant_id: UUID) -> int:
        """Delete all scoring results for a participant. Returns count deleted."""
        result = await self.db.execute(
            delete(ScoringResult).where(ScoringResult.participant_id == participant_id)
        )
        await self.db.commit()
        return result.rowcount

    async def delete_by_weight_table(self, weight_table_id: UUID) -> int:
        """Delete all scoring results for a weight table. Returns count deleted."""
        result = await self.db.execute(
            delete(ScoringResult).where(ScoringResult.weight_table_id == weight_table_id)
        )
        await self.db.commit()
        return result.rowcount
