from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_factory import AIClient, extract_text_from_response
from app.repositories.metric import ExtractedMetricRepository, MetricDefRepository
from app.repositories.participant_metric import ParticipantMetricRepository
from app.services.report_pdf_prompts import get_report_pdf_extraction_prompt
from app.services.report_rag_mapping import RagMappingService

logger = logging.getLogger(__name__)


def _parse_pdf_metrics(payload: dict[str, Any]) -> list[tuple[str, str]]:
    """Parse metrics from LLM response, extracting label/value pairs."""
    metrics = payload.get("metrics", [])
    if not isinstance(metrics, list):
        return []
    result: list[tuple[str, str]] = []
    for m in metrics:
        if not isinstance(m, dict):
            continue
        label = m.get("label")
        value = m.get("value")
        if not label or value is None:
            continue
        result.append((str(label).strip(), str(value).strip()))
    return result


def _parse_value_1_to_10(value_str: str) -> Decimal:
    normalized = value_str.replace(",", ".").strip()
    d = Decimal(normalized)
    if not (Decimal("1") <= d <= Decimal("10")):
        raise ValueError("value_out_of_range")
    return d


class ReportPdfExtractionService:
    def __init__(self, db: AsyncSession, ai_client: AIClient):
        self.db = db
        self.ai_client = ai_client
        self.metric_def_repo = MetricDefRepository(db)
        self.extracted_metric_repo = ExtractedMetricRepository(db)
        self.participant_metric_repo = ParticipantMetricRepository(db)

    async def extract_and_save(
        self,
        report_id: UUID,
        participant_id: UUID,
        pdf_bytes: bytes,
    ) -> dict[str, Any]:
        """
        Extract metrics from PDF and save them to database.

        Uses RAG mapping to convert labels to metric codes.
        Returns warning info for unmapped/ambiguous metrics.
        """
        # 1. Extract raw metrics from PDF (label/value pairs)
        prompt = get_report_pdf_extraction_prompt()

        response = await self.ai_client.generate_from_pdf(
            prompt=prompt,
            pdf_data=pdf_bytes,
            response_mime_type="application/json",
            timeout=180,
        )

        text = extract_text_from_response(response)
        data = json.loads(text)
        items = _parse_pdf_metrics(data)

        logger.info(
            "pdf_metrics_parsed",
            extra={"report_id": str(report_id), "raw_count": len(items)},
        )

        # 2. Load metric definitions for validation
        metric_defs = await self.metric_def_repo.list_all(active_only=True)
        metric_def_by_code = {m.code: m for m in metric_defs}

        # 3. Map labels to metric codes using RAG
        rag_service = RagMappingService(self.db)

        saved = 0
        errors: list[dict[str, Any]] = []
        unknown_labels: list[str] = []
        ambiguous: list[dict[str, Any]] = []

        try:
            for label, value_str in items:
                # Map label to metric code
                mapping_result = await rag_service.map_label(label, use_progressive_widening=True)

                if mapping_result["status"] == "unknown":
                    unknown_labels.append(label)
                    errors.append({"label": label, "error": "unknown_label"})
                    continue

                if mapping_result["status"] == "ambiguous":
                    ambiguous.append({
                        "label": label,
                        "candidates": mapping_result.get("candidates", []),
                    })
                    errors.append({
                        "label": label,
                        "error": "ambiguous_mapping",
                        "candidates": [c.get("code") for c in mapping_result.get("candidates", [])[:3]],
                    })
                    continue

                metric_code = mapping_result["code"]
                metric_def = metric_def_by_code.get(metric_code)

                if not metric_def:
                    errors.append({"label": label, "metric_code": metric_code, "error": "unknown_metric_code"})
                    unknown_labels.append(label)
                    continue

                # Parse and validate value
                try:
                    value = _parse_value_1_to_10(value_str)
                except Exception:
                    errors.append({"label": label, "value": value_str, "error": "invalid_value"})
                    continue

                # Save metric
                await self.extracted_metric_repo.create_or_update(
                    report_id=report_id,
                    metric_def_id=metric_def.id,
                    value=value,
                    source="LLM",
                    confidence=Decimal("1.0"),
                    notes=f"Extracted from PDF via RAG mapping (label: {label})",
                )
                await self.participant_metric_repo.upsert(
                    participant_id=participant_id,
                    metric_code=metric_code,
                    value=value,
                    confidence=Decimal("1.0"),
                    source_report_id=report_id,
                )
                saved += 1

        finally:
            await rag_service.close()

        # 4. Build warning info
        from app.tasks.extraction import _build_extract_warning

        warning_msg, warning_details = _build_extract_warning(unknown_labels, ambiguous)

        result = {
            "metrics_extracted": len(items),
            "metrics_saved": saved,
            "errors": errors,
            "extract_warning": warning_msg,
            "extract_warning_details": warning_details,
        }

        logger.info(
            "pdf_extraction_completed",
            extra={
                "report_id": str(report_id),
                "metrics_extracted": len(items),
                "metrics_saved": saved,
                "unknown_count": len(unknown_labels),
                "ambiguous_count": len(ambiguous),
            },
        )

        return result
