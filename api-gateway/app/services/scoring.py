"""
Scoring service for calculating professional fitness scores.

Implements:
- Formula: score_pct = Σ(value × weight) × 10
- Strengths/dev_areas generation

With Decimal precision and quantization to 0.01.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.metric import ExtractedMetricRepository
from app.repositories.participant_metric import ParticipantMetricRepository
from app.repositories.prof_activity import ProfActivityRepository
from app.repositories.scoring_result import ScoringResultRepository


class ScoringService:
    """Service for calculating professional fitness scores."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.extracted_metric_repo = ExtractedMetricRepository(db)
        self.participant_metric_repo = ParticipantMetricRepository(db)
        self.prof_activity_repo = ProfActivityRepository(db)
        self.scoring_result_repo = ScoringResultRepository(db)

    async def calculate_score(
        self,
        participant_id: UUID,
        prof_activity_code: str,
    ) -> dict:
        """
        Calculate professional fitness score for a participant.

        Args:
            participant_id: UUID of the participant
            prof_activity_code: Code of the professional activity

        Returns:
            Dictionary with:
                - score_pct: Decimal score as percentage (0-100), quantized to 0.01
                - details: List of metric contributions
                - missing_metrics: List of metrics without extracted values

        Raises:
            ValueError: If no active weight table or required metrics are missing
        """
        # 1. Get professional activity
        prof_activity = await self.prof_activity_repo.get_by_code(prof_activity_code)
        if not prof_activity:
            raise ValueError(f"Professional activity '{prof_activity_code}' not found")

        # 2. Get active weight table
        weight_table = await self.prof_activity_repo.get_active_weight_table(prof_activity.id)
        if not weight_table:
            raise ValueError(f"No active weight table for activity '{prof_activity_code}'")

        # 3. Parse weights from JSONB
        weights_map = {}  # metric_code -> weight
        for weight_entry in weight_table.weights:
            metric_code = weight_entry["metric_code"]
            weight = Decimal(weight_entry["weight"])
            weights_map[metric_code] = weight

        # 4. Validate sum of weights == 1.0
        total_weight = sum(weights_map.values())
        if total_weight != Decimal("1.0"):
            raise ValueError(f"Sum of weights must equal 1.0, got {total_weight}")

        # 5. Get participant metrics (S2-08: from participant_metric table)
        metrics_map = await self.participant_metric_repo.get_metrics_dict(participant_id)

        # 5b. Load MetricDef for names (needed for strengths/dev_areas)
        from app.repositories.metric import MetricDefRepository

        metric_def_repo = MetricDefRepository(self.db)
        metric_defs = await metric_def_repo.list_all(active_only=True)
        metric_def_by_code = {m.code: m for m in metric_defs}

        # 6. Check for missing required metrics
        missing_metrics = []
        for metric_code in weights_map.keys():
            if metric_code not in metrics_map:
                missing_metrics.append(metric_code)

        if missing_metrics:
            raise ValueError(
                f"Missing extracted metrics for: {', '.join(missing_metrics)}. "
                f"Please ensure all reports are processed and metrics are extracted."
            )

        # 7. Calculate score: Σ(value × weight) × 10
        score_sum = Decimal("0")
        details = []

        for metric_code, weight in weights_map.items():
            value = metrics_map[metric_code]

            # Validate value is in range [1..10]
            if not (Decimal("1") <= value <= Decimal("10")):
                raise ValueError(f"Metric '{metric_code}' value {value} is out of range [1..10]")

            contribution = value * weight
            score_sum += contribution

            details.append(
                {
                    "metric_code": metric_code,
                    "value": str(value),
                    "weight": str(weight),
                    "contribution": str(
                        contribution.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    ),
                }
            )

        # Final score as percentage: score × 10
        score_pct = (score_sum * Decimal("10")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # 8. Generate strengths and development areas
        strengths, dev_areas = self._generate_strengths_and_dev_areas(
            metrics_map=metrics_map,
            weights_map=weights_map,
            metric_def_by_code=metric_def_by_code,
        )

        # 8b. Generate top competencies (sorted by contribution)
        top_competencies = self._generate_top_competencies(
            metrics_map=metrics_map,
            weights_map=weights_map,
            metric_def_by_code=metric_def_by_code,
        )

        # 9. Save scoring result to database
        scoring_result = await self.scoring_result_repo.create(
            participant_id=participant_id,
            weight_table_id=weight_table.id,
            score_pct=score_pct,
            strengths=strengths,
            dev_areas=dev_areas,
            compute_notes="Score calculated using current weight table",
        )

        return {
            "scoring_result_id": str(scoring_result.id),
            "score_pct": score_pct,
            "details": details,
            "weight_table_id": str(weight_table.id),
            "missing_metrics": [],
            "prof_activity_id": str(prof_activity.id),
            "prof_activity_name": prof_activity.name,
            "strengths": strengths,
            "dev_areas": dev_areas,
            "top_competencies": top_competencies,
        }

    def _generate_strengths_and_dev_areas(
        self,
        metrics_map: dict[str, Decimal],
        weights_map: dict[str, Decimal],
        metric_def_by_code: dict[str, Any],
    ) -> tuple[list[dict], list[dict]]:
        """
        Generate strengths and development areas from metrics.

        Logic:
        - Strengths: Top-5 metrics with highest values
        - Dev areas: Top-5 metrics with lowest values
        - Stable sorting: primary by value, secondary by metric_code

        Args:
            metrics_map: Mapping of metric_code -> value
            weights_map: Mapping of metric_code -> weight (for reference)
            metric_def_by_code: Mapping of metric_code -> MetricDef

        Returns:
            Tuple of (strengths, dev_areas) as JSONB-compatible lists

        AC:
        - Each list has ≤5 elements
        - Stable sorting by value then code
        - No duplicates
        - Deterministic/reproducible
        """
        # Build list of metric items with all necessary data
        metric_items = []
        for metric_code, value in metrics_map.items():
            metric_def = metric_def_by_code.get(metric_code)
            if metric_def and metric_code in weights_map:
                metric_items.append(
                    {
                        "metric_code": metric_code,
                        "metric_name": metric_def.name_ru or metric_def.name,
                        "value": str(value),
                        "weight": str(weights_map[metric_code]),
                    }
                )

        # Sort for strengths: highest value first, then by code (ascending) for stability
        strengths_sorted = sorted(
            metric_items,
            key=lambda x: (-Decimal(x["value"]), x["metric_code"]),
        )
        strengths = strengths_sorted[:5]

        # Sort for dev_areas: lowest value first, then by code (ascending) for stability
        dev_areas_sorted = sorted(
            metric_items,
            key=lambda x: (Decimal(x["value"]), x["metric_code"]),
        )
        dev_areas = dev_areas_sorted[:5]

        return strengths, dev_areas

    def _generate_top_competencies(
        self,
        metrics_map: dict[str, Decimal],
        weights_map: dict[str, Decimal],
        metric_def_by_code: dict[str, Any],
        top_n: int = 5,
    ) -> list[dict]:
        """
        Generate top N competencies sorted by contribution (value × weight).

        This is different from strengths which is sorted by value alone.
        Top competencies represent the metrics that contribute most to the final score.

        Args:
            metrics_map: Mapping of metric_code -> value
            weights_map: Mapping of metric_code -> weight
            metric_def_by_code: Mapping of metric_code -> MetricDef
            top_n: Number of top competencies to return (default: 5)

        Returns:
            List of top competencies sorted by contribution DESC
        """
        competencies = []
        for metric_code, value in metrics_map.items():
            if metric_code not in weights_map:
                continue
            metric_def = metric_def_by_code.get(metric_code)
            if not metric_def:
                continue

            weight = weights_map[metric_code]
            contribution = (value * weight).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            competencies.append(
                {
                    "metric_code": metric_code,
                    "metric_name": metric_def.name,
                    "metric_name_ru": metric_def.name_ru or metric_def.name,
                    "value": str(value),
                    "weight": str(weight),
                    "contribution": str(contribution),
                }
            )

        # Sort by contribution DESC, then by metric_code ASC for stability
        competencies.sort(
            key=lambda x: (-Decimal(x["contribution"]), x["metric_code"])
        )

        return competencies[:top_n]

    async def generate_final_report(
        self,
        participant_id: UUID,
        prof_activity_code: str,
        scoring_result_id: UUID | None = None,
    ) -> dict:
        """
        Generate final report data for a participant.

        Args:
            participant_id: UUID of the participant
            prof_activity_code: Code of the professional activity

        Returns:
            Dictionary with final report data ready for JSON/HTML rendering

        Raises:
            ValueError: If no scoring result found or required data is missing
        """
        from app.repositories.participant import ParticipantRepository

        # 1. Get professional activity
        prof_activity = await self.prof_activity_repo.get_by_code(prof_activity_code)
        if not prof_activity:
            raise ValueError(f"Professional activity '{prof_activity_code}' not found")

        # 2. Get active weight table
        weight_table = await self.prof_activity_repo.get_active_weight_table(prof_activity.id)
        if not weight_table:
            raise ValueError(f"No active weight table for activity '{prof_activity_code}'")

        # 3. Get scoring result (specific by ID or latest)
        if scoring_result_id:
            # Get specific scoring result by ID
            scoring_result = await self.scoring_result_repo.get_by_id(scoring_result_id)
            if not scoring_result:
                raise ValueError(f"Scoring result {scoring_result_id} not found")
            # Validate that it belongs to the correct participant and weight table
            if scoring_result.participant_id != participant_id:
                raise ValueError(f"Scoring result {scoring_result_id} does not belong to participant {participant_id}")
            if scoring_result.weight_table_id != weight_table.id:
                raise ValueError(
                    f"Scoring result {scoring_result_id} was calculated for a different weight table. "
                    f"Please use the correct activity_code or omit scoring_result_id for latest result."
                )
        else:
            # Get latest scoring result (existing behavior)
            scoring_result = await self.scoring_result_repo.get_latest_by_participant_and_weight_table(
                participant_id=participant_id,
                weight_table_id=weight_table.id,
            )

        if not scoring_result:
            raise ValueError(
                f"No scoring result found for participant {participant_id} and activity '{prof_activity_code}'. "
                f"Please calculate score first."
            )

        # 4. Get participant details
        participant_repo = ParticipantRepository(self.db)
        participant = await participant_repo.get_by_id(participant_id)
        if not participant:
            raise ValueError(f"Participant {participant_id} not found")

        # 5. Get participant metrics with details (value, confidence) - S2-08
        participant_metrics = await self.participant_metric_repo.list_by_participant(participant_id)

        # Create metric_code -> ParticipantMetric mapping
        metrics_map = {}
        for metric in participant_metrics:
            metrics_map[metric.metric_code] = metric

        # 5b. Load MetricDef for names and units
        from app.repositories.metric import MetricDefRepository

        metric_def_repo = MetricDefRepository(self.db)
        metric_defs = await metric_def_repo.list_all(active_only=True)
        metric_def_by_code = {m.code: m for m in metric_defs}

        # 6. Parse weights from weight table
        weights_map = {}
        for weight_entry in weight_table.weights:
            metric_code = weight_entry["metric_code"]
            weight = Decimal(weight_entry["weight"])
            weights_map[metric_code] = weight

        # 7. Build detailed metrics list
        detailed_metrics = []
        for metric_code, weight in weights_map.items():
            if metric_code in metrics_map:
                metric = metrics_map[metric_code]
                metric_def = metric_def_by_code.get(metric_code)
                value = metric.value
                contribution = value * weight

                detailed_metrics.append(
                    {
                        "code": metric_code,
                        "name": (metric_def.name_ru or metric_def.name) if metric_def else metric_code,
                        "value": value,
                        "unit": metric_def.unit if metric_def else "балл",
                        "weight": weight,
                        "contribution": contribution.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                        "source": "LLM",  # Default source (S2-08: not stored in participant_metric)
                        "confidence": metric.confidence,
                    }
                )

        # Sort by code for consistency
        detailed_metrics.sort(key=lambda x: x["code"])

        # 7b. Generate top competencies (sorted by contribution)
        # Build metrics_map_decimal from participant_metrics for the helper method
        metrics_map_decimal = {metric.metric_code: metric.value for metric in participant_metrics}
        top_competencies = self._generate_top_competencies(
            metrics_map=metrics_map_decimal,
            weights_map=weights_map,
            metric_def_by_code=metric_def_by_code,
        )

        # 8. Transform strengths to final report format
        strengths_items = []
        if scoring_result.strengths:
            for strength in scoring_result.strengths[:5]:  # Max 5
                metric_code = strength.get("metric_code")
                # Get metric name from MetricDef if not present or if it's a code
                metric_name = strength.get("metric_name")
                if not metric_name or metric_name == metric_code:
                    metric_def = metric_def_by_code.get(metric_code) if metric_code else None
                    metric_name = (
                        (metric_def.name_ru or metric_def.name)
                        if metric_def
                        else (metric_code or "Неизвестная метрика")
                    )

                strengths_items.append(
                    {
                        "title": metric_name,
                        "metric_codes": [metric_code] if metric_code else [],
                        "reason": f"Высокое значение: {strength['value']} (вес {strength['weight']})",
                    }
                )

        # 9. Transform dev_areas to final report format
        dev_areas_items = []
        if scoring_result.dev_areas:
            for dev_area in scoring_result.dev_areas[:5]:  # Max 5
                metric_code = dev_area.get("metric_code")
                # Get metric name from MetricDef if not present or if it's a code
                metric_name = dev_area.get("metric_name")
                if not metric_name or metric_name == metric_code:
                    metric_def = metric_def_by_code.get(metric_code) if metric_code else None
                    metric_name = (
                        (metric_def.name_ru or metric_def.name)
                        if metric_def
                        else (metric_code or "Неизвестная метрика")
                    )

                dev_areas_items.append(
                    {
                        "title": metric_name,
                        "metric_codes": [metric_code] if metric_code else [],
                        "actions": [
                            "Рекомендуется уделить внимание развитию данной компетенции",
                            "Обратитесь к специалисту за персональными рекомендациями",
                        ],
                    }
                )

        # 10. Calculate average confidence for notes (S2-08: from participant_metrics)
        confidences = [m.confidence for m in participant_metrics if m.confidence is not None]
        avg_confidence = sum(confidences) / len(confidences) if confidences else None

        notes = f"OCR confidence средний: {avg_confidence:.2f}; " if avg_confidence else ""
        notes += f"Версия алгоритма расчета: weight_table {weight_table.id}"
        if scoring_result.compute_notes:
            notes += f"; {scoring_result.compute_notes}"

        return {
            # Header
            "participant_id": participant_id,
            "participant_name": participant.full_name,
            "report_date": scoring_result.computed_at,
            "prof_activity_code": prof_activity_code,
            "prof_activity_name": prof_activity.name,
            "weight_table_id": str(weight_table.id),
            # Score
            "score_pct": scoring_result.score_pct,
            # Top competencies (sorted by contribution)
            "top_competencies": top_competencies,
            # Strengths and dev areas
            "strengths": strengths_items,
            "dev_areas": dev_areas_items,
            # Metrics
            "metrics": detailed_metrics,
            # Notes
            "notes": notes,
            # Template version
            "template_version": "1.0.0",
        }
