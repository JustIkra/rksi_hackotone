"""
Canonical metric service for managing metric aliases and merging.

Provides:
- Resolution of metric codes to their canonical form
- Merging of alias metrics into canonical metrics
- Migration of ParticipantMetric records from alias to canonical
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ExtractedMetric, MetricDef, ParticipantMetric

logger = logging.getLogger(__name__)


class CanonicalMetricService:
    """
    Service for managing canonical/alias metric relationships.

    When AI creates duplicate metrics (e.g., "Творчество" and "Творческое мышление"),
    one can be marked as canonical and the other as an alias. This service:
    - Resolves alias codes to their canonical form
    - Merges alias metrics into canonical (updating all references)
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize canonical metric service.

        Args:
            db: Async database session
        """
        self.db = db

    async def resolve_to_canonical(self, metric_code: str) -> str:
        """
        Resolve a metric code to its canonical form.

        If the metric is an alias (has canonical_metric_id set),
        returns the canonical metric's code. Otherwise returns the original code.

        Args:
            metric_code: Metric code to resolve

        Returns:
            Canonical metric code (same code if not an alias)
        """
        result = await self.db.execute(
            select(MetricDef).where(MetricDef.code == metric_code)
        )
        metric = result.scalar_one_or_none()

        if not metric:
            logger.warning(
                "metric_not_found_for_canonical_resolve",
                extra={"metric_code": metric_code},
            )
            return metric_code

        if not metric.canonical_metric_id:
            return metric_code

        # Load canonical metric
        result = await self.db.execute(
            select(MetricDef.code).where(MetricDef.id == metric.canonical_metric_id)
        )
        canonical_code = result.scalar_one_or_none()

        if canonical_code:
            logger.debug(
                "resolved_to_canonical",
                extra={
                    "alias_code": metric_code,
                    "canonical_code": canonical_code,
                },
            )
            return canonical_code

        return metric_code

    async def get_metric_by_code(self, code: str) -> MetricDef | None:
        """
        Get a metric definition by its code.

        Args:
            code: Metric code

        Returns:
            MetricDef if found, None otherwise
        """
        result = await self.db.execute(
            select(MetricDef).where(MetricDef.code == code)
        )
        return result.scalar_one_or_none()

    async def merge_metrics(
        self,
        alias_code: str,
        canonical_code: str,
    ) -> dict[str, Any]:
        """
        Merge an alias metric into a canonical metric.

        This operation:
        1. Sets canonical_metric_id on the alias
        2. Migrates ParticipantMetric records from alias to canonical
           (using upsert logic - keeps higher value/confidence)
        3. Deactivates the alias (sets active=False)

        Args:
            alias_code: Code of the metric to mark as alias
            canonical_code: Code of the canonical metric

        Returns:
            Dict with merge statistics:
            - participant_metrics_migrated: Number of records migrated
            - participant_metrics_skipped: Number of records skipped (canonical had better value)
            - extracted_metrics_count: Number of ExtractedMetric records (not migrated, kept for history)
            - alias_deactivated: Whether alias was deactivated

        Raises:
            ValueError: If alias or canonical metric not found
            ValueError: If alias and canonical are the same
        """
        if alias_code == canonical_code:
            raise ValueError("Cannot merge metric with itself")

        # Load both metrics
        alias_metric = await self.get_metric_by_code(alias_code)
        canonical_metric = await self.get_metric_by_code(canonical_code)

        if not alias_metric:
            raise ValueError(f"Alias metric '{alias_code}' not found")
        if not canonical_metric:
            raise ValueError(f"Canonical metric '{canonical_code}' not found")

        # Check for circular reference
        if canonical_metric.canonical_metric_id:
            logger.warning(
                "canonical_is_itself_an_alias",
                extra={
                    "canonical_code": canonical_code,
                    "canonical_points_to": str(canonical_metric.canonical_metric_id),
                },
            )

        stats = {
            "alias_code": alias_code,
            "canonical_code": canonical_code,
            "participant_metrics_migrated": 0,
            "participant_metrics_skipped": 0,
            "extracted_metrics_count": 0,
            "alias_deactivated": False,
        }

        # Step 1: Set canonical_metric_id on alias
        alias_metric.canonical_metric_id = canonical_metric.id
        logger.info(
            "set_canonical_metric_id",
            extra={
                "alias_code": alias_code,
                "canonical_code": canonical_code,
                "canonical_id": str(canonical_metric.id),
            },
        )

        # Step 2: Migrate ParticipantMetric records
        # Get all participant metrics with alias code
        result = await self.db.execute(
            select(ParticipantMetric).where(
                ParticipantMetric.metric_code == alias_code
            )
        )
        alias_participant_metrics = list(result.scalars().all())

        for alias_pm in alias_participant_metrics:
            # Check if canonical already has a record for this participant
            result = await self.db.execute(
                select(ParticipantMetric).where(
                    ParticipantMetric.participant_id == alias_pm.participant_id,
                    ParticipantMetric.metric_code == canonical_code,
                )
            )
            canonical_pm = result.scalar_one_or_none()

            if canonical_pm:
                # Decide which to keep based on priority rules
                # Priority: higher value > higher confidence > newer
                should_migrate = self._should_replace(
                    existing=canonical_pm,
                    incoming=alias_pm,
                )

                if should_migrate:
                    # Update canonical record with alias values
                    canonical_pm.value = alias_pm.value
                    canonical_pm.confidence = alias_pm.confidence
                    canonical_pm.last_source_report_id = alias_pm.last_source_report_id
                    stats["participant_metrics_migrated"] += 1
                else:
                    stats["participant_metrics_skipped"] += 1

                # Delete alias record
                await self.db.delete(alias_pm)
            else:
                # No canonical record - just change the code
                alias_pm.metric_code = canonical_code
                stats["participant_metrics_migrated"] += 1

        # Step 3: Count ExtractedMetric records (keep for audit trail)
        result = await self.db.execute(
            select(ExtractedMetric).where(
                ExtractedMetric.metric_def_id == alias_metric.id
            )
        )
        extracted_metrics = result.scalars().all()
        stats["extracted_metrics_count"] = len(list(extracted_metrics))

        # Step 4: Deactivate alias
        alias_metric.active = False
        stats["alias_deactivated"] = True

        await self.db.commit()

        logger.info(
            "metric_merge_completed",
            extra=stats,
        )

        return stats

    def _should_replace(
        self,
        existing: ParticipantMetric,
        incoming: ParticipantMetric,
    ) -> bool:
        """
        Determine if incoming should replace existing based on priority rules.

        Priority (same as ParticipantMetricRepository.upsert):
        1. Higher value wins
        2. Higher confidence wins (on tie)
        3. More recent source report wins (on tie)

        Args:
            existing: Current canonical ParticipantMetric
            incoming: Alias ParticipantMetric to potentially migrate

        Returns:
            True if incoming should replace existing
        """
        from decimal import Decimal

        def to_decimal(v: Any) -> Decimal:
            if v is None:
                return Decimal("0")
            if isinstance(v, Decimal):
                return v
            return Decimal(str(v))

        existing_value = to_decimal(existing.value)
        incoming_value = to_decimal(incoming.value)

        # Rule 1: Higher value wins
        if incoming_value > existing_value:
            return True
        if incoming_value < existing_value:
            return False

        # Rule 2: Higher confidence wins
        existing_confidence = to_decimal(existing.confidence)
        incoming_confidence = to_decimal(incoming.confidence)

        if incoming_confidence > existing_confidence:
            return True
        if incoming_confidence < existing_confidence:
            return False

        # Rule 3: More recent upload wins
        # For simplicity, we don't check upload dates here
        # (would require loading Report records)
        # Tie goes to existing (don't migrate)
        return False

    async def list_aliases(self, canonical_code: str) -> list[str]:
        """
        List all alias codes that point to a canonical metric.

        Args:
            canonical_code: Code of the canonical metric

        Returns:
            List of alias metric codes
        """
        canonical = await self.get_metric_by_code(canonical_code)
        if not canonical:
            return []

        result = await self.db.execute(
            select(MetricDef.code).where(
                MetricDef.canonical_metric_id == canonical.id
            )
        )
        return [row[0] for row in result.all()]

    async def is_alias(self, metric_code: str) -> bool:
        """
        Check if a metric is an alias (has canonical_metric_id set).

        Args:
            metric_code: Metric code to check

        Returns:
            True if the metric is an alias
        """
        metric = await self.get_metric_by_code(metric_code)
        if not metric:
            return False
        return metric.canonical_metric_id is not None
