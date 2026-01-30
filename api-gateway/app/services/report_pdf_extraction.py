from __future__ import annotations

import json
import logging
import re
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_factory import AIClient, extract_text_from_response
from app.repositories.metric import ExtractedMetricRepository, MetricDefRepository
from app.repositories.participant_metric import ParticipantMetricRepository
from app.services.report_pdf_prompts import (
    get_report_pdf_extraction_prompt,
    get_report_pdf_extraction_schema,
)
from app.services.report_rag_mapping import RagMappingService
from app.services.semantic_dedup import SemanticDeduplicationService

logger = logging.getLogger(__name__)


def _parse_pdf_metrics(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse metrics from LLM response, extracting label/value/evidence dicts."""
    metrics = payload.get("metrics", [])
    if not isinstance(metrics, list):
        return []
    result: list[dict[str, Any]] = []
    for m in metrics:
        if not isinstance(m, dict):
            continue
        label = m.get("label")
        value = m.get("value")
        if not label or value is None:
            continue
        evidence = m.get("evidence", {})
        quotes = evidence.get("quotes", []) if isinstance(evidence, dict) else []
        page_numbers = evidence.get("page_numbers", []) if isinstance(evidence, dict) else []
        result.append({
            "label": str(label).strip(),
            "value": str(value).strip(),
            "quotes": quotes if isinstance(quotes, list) else [],
            "page_numbers": page_numbers if isinstance(page_numbers, list) else [],
        })
    return result


def _parse_value_1_to_10(value_str: str) -> Decimal:
    normalized = value_str.replace(",", ".").strip()
    d = Decimal(normalized)
    if not (Decimal("1") <= d <= Decimal("10")):
        raise ValueError("value_out_of_range")
    return d


def _normalize_for_comparison(text: str) -> str:
    """
    Normalize text for value comparison.

    - Replace comma with dot (decimal separator)
    - Collapse all whitespace to single space
    - Strip leading/trailing whitespace
    - Convert to lowercase
    """
    text = text.replace(",", ".")
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def _evidence_contains_value(value_str: str, quotes: list[str]) -> bool:
    """
    Check if the extracted value appears in the evidence quotes.

    Performs normalization to handle:
    - Comma vs dot decimal separator (7,5 == 7.5)
    - Whitespace variations
    - Ensures exact number match (8 should not match 8.5 or 18)

    Args:
        value_str: The extracted value (e.g., "7.5")
        quotes: List of evidence quote strings from LLM

    Returns:
        True if value is found in any quote, False otherwise
    """
    if not quotes:
        return False

    # Normalize the value
    norm_value = _normalize_for_comparison(value_str)

    # Build regex pattern for exact number match
    # Value should be surrounded by word boundaries or non-digit characters
    # This prevents "8" from matching "8.5" or "18"
    try:
        # Escape dots for regex (they're literal decimal points after normalization)
        escaped_value = re.escape(norm_value)
        # Pattern: value must be preceded and followed by non-digit or start/end
        pattern = rf"(?<![0-9.]){escaped_value}(?![0-9.])"
    except re.error:
        # Fallback to simple substring match if regex fails
        pattern = None

    for quote in quotes:
        if not quote:
            continue
        norm_quote = _normalize_for_comparison(quote)

        if pattern:
            if re.search(pattern, norm_quote):
                return True
        else:
            # Fallback: simple substring match
            if norm_value in norm_quote:
                return True

    return False


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
        # 1. Load metric definitions first (for prompt context and validation)
        metric_defs = await self.metric_def_repo.list_all(active_only=True)
        metric_def_by_code = {m.code: m for m in metric_defs}

        # Build metrics context for LLM prompt
        existing_metrics_context = [
            {
                "code": m.code,
                "name_ru": m.name_ru,
                "name": m.name,
            }
            for m in metric_defs
        ]

        # 2. Extract raw metrics from PDF (label/value pairs)
        prompt = get_report_pdf_extraction_prompt(existing_metrics=existing_metrics_context)
        output_schema = get_report_pdf_extraction_schema()

        response = await self.ai_client.generate_from_pdf(
            prompt=prompt,
            pdf_data=pdf_bytes,
            response_mime_type="application/json",
            timeout=180,
            json_schema=output_schema,
        )

        text = extract_text_from_response(response)
        data = json.loads(text)
        items = _parse_pdf_metrics(data)

        logger.info(
            "pdf_metrics_parsed",
            extra={"report_id": str(report_id), "raw_count": len(items)},
        )

        # Pre-deduplicate semantically identical labels before RAG mapping
        dedup_service = SemanticDeduplicationService(self.db)
        try:
            items = await dedup_service.deduplicate_items(items)
            logger.info(
                "pdf_metrics_deduplicated",
                extra={"report_id": str(report_id), "deduplicated_count": len(items)},
            )
        finally:
            await dedup_service.close()

        # 3. Map labels to metric codes using RAG
        rag_service = RagMappingService(self.db, ai_client=self.ai_client)

        saved = 0
        errors: list[dict[str, Any]] = []
        unknown_labels: list[str] = []
        ambiguous: list[dict[str, Any]] = []

        try:
            for item in items:
                label = item["label"]
                value_str = item["value"]
                quotes = item["quotes"]

                # Step 1: Verify value appears in evidence quotes (deterministic check)
                if not _evidence_contains_value(value_str, quotes):
                    logger.warning(
                        "evidence_verification_failed",
                        extra={
                            "label": label,
                            "value": value_str,
                            "quotes_count": len(quotes),
                        },
                    )
                    errors.append({
                        "label": label,
                        "value": value_str,
                        "error": "evidence_missing_value",
                        "quotes": quotes[:2] if quotes else [],
                    })
                    continue

                # Step 2: Map label to metric code
                mapping_result = await rag_service.map_label(label)

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

                # Step 3: Parse and validate value
                try:
                    value = _parse_value_1_to_10(value_str)
                except Exception:
                    errors.append({"label": label, "value": value_str, "error": "invalid_value"})
                    continue

                # Step 4: Save metric
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
