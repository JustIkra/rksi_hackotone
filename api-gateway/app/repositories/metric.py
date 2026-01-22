"""
Repository layer for Metric data access.

Handles all database operations for metric definitions and extracted metrics.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import ExtractedMetric, MetricDef, Report, WeightTable
from app.services.metric_localization import get_metric_display_name_ru


class MetricDefRepository:
    """Repository for metric definition database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        code: str,
        name: str,
        name_ru: str | None = None,
        description: str | None = None,
        unit: str | None = None,
        min_value: Decimal | None = None,
        max_value: Decimal | None = None,
        active: bool = True,
        category_id: UUID | None = None,
        sort_order: int = 0,
    ) -> MetricDef:
        """
        Create a new metric definition.

        Args:
            code: Unique metric code
            name: Metric name
            description: Optional description
            unit: Optional measurement unit
            min_value: Optional minimum value
            max_value: Optional maximum value
            active: Whether metric is active (default: True)
            category_id: Optional category ID for grouping
            sort_order: Sort order within category (default: 0)

        Returns:
            Created MetricDef instance
        """
        resolved_name_ru = (
            name_ru if name_ru and name_ru.strip() else get_metric_display_name_ru(code)
        )

        metric_def = MetricDef(
            code=code,
            name=name,
            name_ru=resolved_name_ru,
            description=description,
            unit=unit,
            min_value=min_value,
            max_value=max_value,
            active=active,
            category_id=category_id,
            sort_order=sort_order,
        )
        self.db.add(metric_def)
        await self.db.commit()
        await self.db.refresh(metric_def)
        return metric_def

    async def get_by_id(self, metric_def_id: UUID) -> MetricDef | None:
        """
        Get a metric definition by ID.

        Args:
            metric_def_id: UUID of the metric definition

        Returns:
            MetricDef if found, None otherwise
        """
        result = await self.db.execute(select(MetricDef).where(MetricDef.id == metric_def_id))
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> MetricDef | None:
        """
        Get a metric definition by code.

        Args:
            code: Unique metric code

        Returns:
            MetricDef if found, None otherwise
        """
        result = await self.db.execute(select(MetricDef).where(MetricDef.code == code))
        return result.scalar_one_or_none()

    async def list_all(self, active_only: bool = False) -> list[MetricDef]:
        """
        List all metric definitions.

        Args:
            active_only: If True, return only active metrics

        Returns:
            List of MetricDef instances
        """
        stmt = select(MetricDef).order_by(MetricDef.code)
        if active_only:
            stmt = stmt.where(MetricDef.active)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self,
        metric_def_id: UUID,
        name: str | None = None,
        name_ru: str | None = None,
        description: str | None = None,
        unit: str | None = None,
        min_value: Decimal | None = None,
        max_value: Decimal | None = None,
        active: bool | None = None,
        category_id: UUID | None = None,
        sort_order: int | None = None,
    ) -> MetricDef | None:
        """
        Update a metric definition.

        Args:
            metric_def_id: UUID of the metric definition
            name: New name (if provided)
            description: New description (if provided)
            unit: New unit (if provided)
            min_value: New min_value (if provided)
            max_value: New max_value (if provided)
            active: New active status (if provided)
            category_id: New category ID (if provided)
            sort_order: New sort order (if provided)

        Returns:
            Updated MetricDef if found, None otherwise
        """
        metric_def = await self.get_by_id(metric_def_id)
        if not metric_def:
            return None

        if name is not None:
            metric_def.name = name
        if name_ru is not None:
            metric_def.name_ru = name_ru
        if description is not None:
            metric_def.description = description
        if unit is not None:
            metric_def.unit = unit
        if min_value is not None:
            metric_def.min_value = min_value
        if max_value is not None:
            metric_def.max_value = max_value
        if active is not None:
            metric_def.active = active
        if category_id is not None:
            metric_def.category_id = category_id
        if sort_order is not None:
            metric_def.sort_order = sort_order

        await self.db.commit()
        await self.db.refresh(metric_def)
        return metric_def

    async def delete(self, metric_def_id: UUID) -> bool:
        """
        Delete a metric definition.

        Args:
            metric_def_id: UUID of the metric definition

        Returns:
            True if deleted, False if not found
        """
        metric_def = await self.get_by_id(metric_def_id)
        if not metric_def:
            return False

        await self.db.delete(metric_def)
        await self.db.commit()
        return True

    async def bulk_move_to_category(
        self,
        metric_ids: list[UUID],
        target_category_id: UUID | None,
    ) -> tuple[int, list[str]]:
        """
        Move multiple metric definitions to a category.

        Args:
            metric_ids: List of metric definition UUIDs
            target_category_id: Target category ID (None for uncategorized)

        Returns:
            Tuple of (affected_count, error_messages)
        """
        affected = 0
        errors: list[str] = []

        for metric_id in metric_ids:
            metric_def = await self.get_by_id(metric_id)
            if not metric_def:
                errors.append(f"Metric {metric_id} not found")
                continue
            metric_def.category_id = target_category_id
            affected += 1

        if affected > 0:
            await self.db.commit()

        return affected, errors

    async def bulk_delete(
        self, metric_ids: list[UUID]
    ) -> tuple[int, list[dict], dict]:
        """
        Delete multiple metric definitions with CASCADE behavior.

        Args:
            metric_ids: List of metric definition UUIDs

        Returns:
            Tuple of (deleted_count, error_list, affected_counts)
            - deleted_count: Number of successfully deleted metrics
            - error_list: List of {metric_id, error} dicts for failures
            - affected_counts: Dict with totals for audit logging
        """
        from sqlalchemy.exc import IntegrityError

        from app.db.models import MetricSynonym

        deleted = 0
        errors: list[dict] = []
        affected_counts = {
            "extracted_metrics": 0,
            "synonyms": 0,
            "weight_tables": 0,
        }

        for metric_id in metric_ids:
            try:
                metric_def = await self.get_by_id(metric_id)
                if not metric_def:
                    errors.append(
                        {"metric_id": str(metric_id), "error": "Metric not found"}
                    )
                    continue

                # Get usage stats before deletion for audit
                usage = await self.get_usage_stats(metric_id)
                affected_counts["extracted_metrics"] += usage["extracted_metrics_count"]

                # Count synonyms
                synonym_count_stmt = select(func.count(MetricSynonym.id)).where(
                    MetricSynonym.metric_def_id == metric_id
                )
                synonym_result = await self.db.execute(synonym_count_stmt)
                synonym_count = synonym_result.scalar() or 0
                affected_counts["synonyms"] += synonym_count

                # Clean up weight tables (JSONB, not FK)
                weight_tables_affected = await self._cleanup_weight_tables_for_metric(
                    metric_def.code
                )
                affected_counts["weight_tables"] += len(weight_tables_affected)

                # Delete (CASCADE will handle synonyms, extracted_metrics)
                await self.db.delete(metric_def)
                deleted += 1

            except IntegrityError:
                await self.db.rollback()
                errors.append(
                    {
                        "metric_id": str(metric_id),
                        "error": "Cannot delete: integrity constraint violation",
                    }
                )

        if deleted > 0:
            await self.db.commit()

        return deleted, errors, affected_counts

    async def _cleanup_weight_tables_for_metric(self, metric_code: str) -> list[UUID]:
        """
        Remove metric from all weight_tables JSONB and mark as needs_review.

        Args:
            metric_code: Code of the metric being deleted

        Returns:
            List of affected weight_table IDs
        """
        stmt = select(WeightTable)
        result = await self.db.execute(stmt)
        weight_tables = result.scalars().all()

        affected_table_ids: list[UUID] = []
        for wt in weight_tables:
            if wt.weights:
                original_len = len(wt.weights)
                new_weights = [
                    w for w in wt.weights if w.get("metric_code") != metric_code
                ]
                if len(new_weights) < original_len:
                    wt.weights = new_weights
                    # Mark as needing review (sum != 1.0 now)
                    wt.needs_review = True
                    affected_table_ids.append(wt.id)

        return affected_table_ids

    async def get_usage_stats(self, metric_def_id: UUID) -> dict:
        """
        Get usage statistics for a metric definition.

        Args:
            metric_def_id: UUID of the metric definition

        Returns:
            Dict with usage statistics including:
            - extracted_metrics_count: Number of extracted metric values
            - participant_metrics_count: Number of participant metric values
            - scoring_results_count: Number of scoring results affected
            - weight_tables_count: Number of weight tables using this metric
            - reports_affected: Number of unique reports with this metric
        """
        from app.db.models import ParticipantMetric, ScoringResult

        # Get the metric to find its code
        metric_def = await self.get_by_id(metric_def_id)
        if not metric_def:
            return {
                "metric_id": metric_def_id,
                "extracted_metrics_count": 0,
                "participant_metrics_count": 0,
                "scoring_results_count": 0,
                "weight_tables_count": 0,
                "reports_affected": 0,
            }

        # Count extracted metrics
        extracted_stmt = select(func.count(ExtractedMetric.id)).where(
            ExtractedMetric.metric_def_id == metric_def_id
        )
        extracted_result = await self.db.execute(extracted_stmt)
        extracted_count = extracted_result.scalar() or 0

        # Count unique reports affected
        reports_stmt = select(func.count(func.distinct(ExtractedMetric.report_id))).where(
            ExtractedMetric.metric_def_id == metric_def_id
        )
        reports_result = await self.db.execute(reports_stmt)
        reports_count = reports_result.scalar() or 0

        # Count participant metrics using this metric code
        participant_metrics_stmt = select(func.count(ParticipantMetric.id)).where(
            ParticipantMetric.metric_code == metric_def.code
        )
        participant_metrics_result = await self.db.execute(participant_metrics_stmt)
        participant_metrics_count = participant_metrics_result.scalar() or 0

        # Count weight tables that include this metric code in their JSONB weights
        # The weights field is a JSONB array of {metric_code, weight} objects
        weight_tables_list_stmt = select(WeightTable)
        weight_tables_list_result = await self.db.execute(weight_tables_list_stmt)
        weight_tables = weight_tables_list_result.scalars().all()

        weight_tables_count = 0
        weight_table_ids = []
        for wt in weight_tables:
            if wt.weights:
                for weight_entry in wt.weights:
                    if weight_entry.get("metric_code") == metric_def.code:
                        weight_tables_count += 1
                        weight_table_ids.append(wt.id)
                        break

        # Count scoring results that used weight tables containing this metric
        scoring_results_count = 0
        if weight_table_ids:
            scoring_stmt = select(func.count(ScoringResult.id)).where(
                ScoringResult.weight_table_id.in_(weight_table_ids)
            )
            scoring_result = await self.db.execute(scoring_stmt)
            scoring_results_count = scoring_result.scalar() or 0

        return {
            "metric_id": metric_def_id,
            "extracted_metrics_count": extracted_count,
            "participant_metrics_count": participant_metrics_count,
            "scoring_results_count": scoring_results_count,
            "weight_tables_count": weight_tables_count,
            "reports_affected": reports_count,
        }


class ExtractedMetricRepository:
    """Repository for extracted metric database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_or_update(
        self,
        report_id: UUID,
        metric_def_id: UUID,
        value: Decimal,
        source: str = "MANUAL",
        confidence: Decimal | None = None,
        notes: str | None = None,
    ) -> ExtractedMetric:
        """
        Create or update an extracted metric.
        If (report_id, metric_def_id) already exists, update it; otherwise create new.

        Args:
            report_id: UUID of the report
            metric_def_id: UUID of the metric definition
            value: Extracted value
            source: Source of extraction (OCR, LLM, MANUAL)
            confidence: Confidence score (0-1)
            notes: Additional notes

        Returns:
            Created or updated ExtractedMetric instance
        """
        # Check if exists
        existing = await self.get_by_report_and_metric(report_id, metric_def_id)

        if existing:
            # Update existing
            existing.value = value
            existing.source = source
            existing.confidence = confidence
            existing.notes = notes
            await self.db.commit()
            await self.db.refresh(existing)
            return existing
        else:
            # Create new
            extracted_metric = ExtractedMetric(
                report_id=report_id,
                metric_def_id=metric_def_id,
                value=value,
                source=source,
                confidence=confidence,
                notes=notes,
            )
            self.db.add(extracted_metric)
            await self.db.commit()
            await self.db.refresh(extracted_metric)
            return extracted_metric

    async def get_by_id(self, extracted_metric_id: UUID) -> ExtractedMetric | None:
        """
        Get an extracted metric by ID.

        Args:
            extracted_metric_id: UUID of the extracted metric

        Returns:
            ExtractedMetric if found, None otherwise
        """
        result = await self.db.execute(
            select(ExtractedMetric)
            .options(selectinload(ExtractedMetric.metric_def))
            .where(ExtractedMetric.id == extracted_metric_id)
        )
        return result.scalar_one_or_none()

    async def get_by_report_and_metric(
        self, report_id: UUID, metric_def_id: UUID
    ) -> ExtractedMetric | None:
        """
        Get an extracted metric by report and metric definition.

        Args:
            report_id: UUID of the report
            metric_def_id: UUID of the metric definition

        Returns:
            ExtractedMetric if found, None otherwise
        """
        result = await self.db.execute(
            select(ExtractedMetric)
            .options(selectinload(ExtractedMetric.metric_def))
            .where(
                ExtractedMetric.report_id == report_id,
                ExtractedMetric.metric_def_id == metric_def_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_report(self, report_id: UUID) -> list[ExtractedMetric]:
        """
        List all extracted metrics for a report.

        Args:
            report_id: UUID of the report

        Returns:
            List of ExtractedMetric instances with metric_def loaded
        """
        result = await self.db.execute(
            select(ExtractedMetric)
            .options(selectinload(ExtractedMetric.metric_def))
            .where(ExtractedMetric.report_id == report_id)
            .order_by(ExtractedMetric.metric_def_id)
        )
        return list(result.scalars().all())

    async def get_by_participant(self, participant_id: UUID) -> list[ExtractedMetric]:
        """
        Get all extracted metrics for a participant across all their reports.

        Args:
            participant_id: UUID of the participant

        Returns:
            List of ExtractedMetric instances with metric_def loaded
        """
        # Import here to avoid circular dependency

        result = await self.db.execute(
            select(ExtractedMetric)
            .join(Report, ExtractedMetric.report_id == Report.id)
            .options(selectinload(ExtractedMetric.metric_def))
            .where(Report.participant_id == participant_id)
            .order_by(ExtractedMetric.metric_def_id)
        )
        return list(result.scalars().all())

    async def delete(self, extracted_metric_id: UUID) -> bool:
        """
        Delete an extracted metric.

        Args:
            extracted_metric_id: UUID of the extracted metric

        Returns:
            True if deleted, False if not found
        """
        extracted_metric = await self.get_by_id(extracted_metric_id)
        if not extracted_metric:
            return False

        await self.db.delete(extracted_metric)
        await self.db.commit()
        return True

    async def delete_by_report(self, report_id: UUID) -> int:
        """
        Delete all extracted metrics for a report.

        Args:
            report_id: UUID of the report

        Returns:
            Number of metrics deleted
        """
        metrics = await self.list_by_report(report_id)
        count = len(metrics)
        for metric in metrics:
            await self.db.delete(metric)
        await self.db.commit()
        return count
