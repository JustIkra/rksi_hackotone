"""
LLM decision service for metric mapping.

Uses AI to select the best metric_code from retrieval candidates
with guardrails to prevent hallucination and ensure code validity.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.prompt_loader import get_prompt_loader

# Re-export for easier import from this module
__all__ = [
    "get_metric_mapping_decision_system",
    "get_metric_mapping_decision_user_prefix",
    "get_metric_mapping_decision_schema",
    "get_metric_mapping_decision_batch_prefix",
    "get_metric_mapping_decision_batch_schema",
    "decide_metric_mapping",
    "decide_metric_mapping_batch",
]

logger = logging.getLogger(__name__)


def get_metric_mapping_decision_system() -> str:
    """
    Get system prompt for metric mapping decision.

    Returns:
        System prompt text
    """
    loader = get_prompt_loader()
    return loader.get_prompt_text(
        "metric-mapping-decision",
        "decision_system",
        fallback="You are an expert at mapping metric labels to codes.",
    )


def get_metric_mapping_decision_user_prefix() -> str:
    """
    Get user prompt template for metric mapping decision.

    Returns:
        User prompt template with {label} and {candidates} placeholders
    """
    loader = get_prompt_loader()
    return loader.get_prompt_text(
        "metric-mapping-decision",
        "decision_user_prefix",
        fallback="Label: {label}\nCandidates:\n{candidates}",
    )


def get_metric_mapping_decision_schema() -> dict[str, Any] | None:
    """Get output_schema from metric-mapping-decision config for structured outputs."""
    loader = get_prompt_loader()
    cfg = loader.load("metric-mapping-decision")
    return cfg.get("output_schema")


def get_metric_mapping_decision_batch_prefix() -> str:
    """
    Get user prompt template for batch metric mapping decision.

    Returns:
        User prompt template with {items} placeholder (JSON array)
    """
    loader = get_prompt_loader()
    return loader.get_prompt_text(
        "metric-mapping-decision",
        "decision_user_prefix_batch",
        fallback='Items (JSON array):\n{items}\n\nReturn JSON with "results" array.',
    )


def get_metric_mapping_decision_batch_schema() -> dict[str, Any] | None:
    """Get output_schema_batch from metric-mapping-decision config for batch structured outputs."""
    loader = get_prompt_loader()
    cfg = loader.load("metric-mapping-decision")
    return cfg.get("output_schema_batch")


def _format_candidates(candidates: list[dict[str, Any]]) -> str:
    """
    Format candidates for LLM prompt.

    Args:
        candidates: List of candidate dicts with code, name_ru, description, indexed_text, similarity

    Returns:
        Formatted string representation of candidates
    """
    lines = []
    for cand in candidates:
        code = cand.get("code", "N/A")
        name_ru = cand.get("name_ru", "")
        description = cand.get("description", "") or ""
        similarity = cand.get("similarity", 0.0)
        # Include description explicitly for better LLM understanding
        desc_part = f" — {description}" if description else ""
        lines.append(f"{code} | {name_ru}{desc_part} | sim={similarity:.3f}")
    return "\n".join(lines)


async def decide_metric_mapping(
    ai_client: Any,
    label: str,
    candidates: list[dict[str, Any]],
    min_confidence: float = 0.6,
    description: str | None = None,
) -> dict[str, Any]:
    """
    Use LLM to decide best metric mapping from candidates.

    Implements guardrails:
    1. Empty candidates → immediate return with status="unknown"
    2. LLM must return valid JSON
    3. LLM must choose code from candidate list (no hallucination)
    4. Confidence must be above threshold
    5. Respect LLM decision (match/ambiguous/unknown)

    Args:
        ai_client: AI client with generate_text method
        label: Metric label to map
        candidates: List of candidate dicts from retrieval
        min_confidence: Minimum confidence threshold (default 0.6)
        description: Optional description of the metric being mapped

    Returns:
        Dict with:
        - status: "mapped", "ambiguous", or "unknown"
        - code: Metric code if mapped, None otherwise
        - confidence: Confidence score from LLM
        - reason: Explanation from LLM or guardrail message
    """
    # Guardrail 1: Empty candidates
    if not candidates:
        logger.debug("llm_decision_skipped_empty_candidates", extra={"label": label})
        return {
            "status": "unknown",
            "code": None,
            "confidence": 0.0,
            "reason": "No candidates available",
        }

    # Extract valid codes from candidates
    valid_codes = {cand.get("code") for cand in candidates if cand.get("code")}

    # Build prompt
    system_prompt = get_metric_mapping_decision_system()
    user_template = get_metric_mapping_decision_user_prefix()
    output_schema = get_metric_mapping_decision_schema()

    candidates_text = _format_candidates(candidates)
    desc_text = description if description else "нет описания"
    user_prompt = user_template.format(
        label=label,
        description=desc_text,
        candidates=candidates_text,
    )

    # Call LLM with structured outputs if schema is available
    try:
        response = await ai_client.generate_text(
            prompt=user_prompt,
            system_instructions=system_prompt,
            response_mime_type="application/json",
            json_schema=output_schema,
        )
        content = response["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(
            "llm_decision_api_error",
            extra={"label": label, "error": str(e)},
        )
        return {
            "status": "unknown",
            "code": None,
            "confidence": 0.0,
            "reason": f"LLM API error: {str(e)}",
        }

    # Guardrail 2: Valid JSON
    try:
        result = json.loads(content)
    except json.JSONDecodeError as e:
        logger.warning(
            "llm_decision_invalid_json",
            extra={"label": label, "content": content, "error": str(e)},
        )
        return {
            "status": "unknown",
            "code": None,
            "confidence": 0.0,
            "reason": f"Invalid JSON response from LLM: {str(e)}",
        }

    decision = result.get("decision", "").lower()
    metric_code = result.get("metric_code")
    confidence = float(result.get("confidence", 0.0))
    reason = result.get("reason", "")

    # Handle decision types
    if decision == "unknown":
        logger.debug(
            "llm_decision_unknown",
            extra={"label": label, "reason": reason},
        )
        return {
            "status": "unknown",
            "code": None,
            "confidence": confidence,
            "reason": reason,
        }

    if decision == "ambiguous":
        logger.debug(
            "llm_decision_ambiguous",
            extra={"label": label, "reason": reason},
        )
        return {
            "status": "ambiguous",
            "code": None,
            "confidence": confidence,
            "reason": reason,
        }

    if decision == "match":
        # Guardrail 3: Code must be from candidate list
        if metric_code not in valid_codes:
            logger.warning(
                "llm_decision_invalid_code",
                extra={
                    "label": label,
                    "hallucinated_code": metric_code,
                    "valid_codes": list(valid_codes),
                },
            )
            return {
                "status": "unknown",
                "code": None,
                "confidence": 0.0,
                "reason": f"LLM returned invalid code: {metric_code} not in candidates",
            }

        # Guardrail 4: Confidence threshold
        if confidence < min_confidence:
            logger.debug(
                "llm_decision_low_confidence",
                extra={
                    "label": label,
                    "code": metric_code,
                    "confidence": confidence,
                    "threshold": min_confidence,
                },
            )
            return {
                "status": "unknown",
                "code": None,
                "confidence": confidence,
                "reason": f"Confidence {confidence:.2f} below threshold {min_confidence:.2f}",
            }

        # Success
        logger.info(
            "llm_decision_mapped",
            extra={
                "label": label,
                "code": metric_code,
                "confidence": confidence,
            },
        )
        return {
            "status": "mapped",
            "code": metric_code,
            "confidence": confidence,
            "reason": reason,
        }

    # Unknown decision type
    logger.warning(
        "llm_decision_unknown_type",
        extra={"label": label, "decision": decision},
    )
    return {
        "status": "unknown",
        "code": None,
        "confidence": 0.0,
        "reason": f"Unknown decision type: {decision}",
    }


async def decide_metric_mapping_batch(
    ai_client: Any,
    items: list[dict[str, Any]],
    min_confidence: float = 0.6,
) -> list[dict[str, Any]]:
    """
    Use LLM to decide best metric mappings for multiple labels in one call.

    Reduces API calls by processing all items in a single LLM request.

    Each item should have:
    - label: The metric label from the document
    - candidates: List of candidate dicts (code, name_ru, indexed_text, similarity)

    Implements guardrails:
    1. Empty items → immediate return with empty list
    2. LLM must return valid JSON
    3. For each result, code must come from that item's candidate list
    4. Confidence must be above threshold
    5. Respect LLM decision (match/ambiguous/unknown)

    Args:
        ai_client: AI client with generate_text method
        items: List of dicts with label and candidates
        min_confidence: Minimum confidence threshold (default 0.6)

    Returns:
        List of dicts with:
        - status: "mapped", "ambiguous", or "unknown"
        - code: Metric code if mapped, None otherwise
        - confidence: Confidence score from LLM
        - reason: Explanation from LLM or guardrail message
    """
    if not items:
        return []

    # Build valid codes map for each label
    valid_codes_by_label: dict[str, set[str]] = {}
    for item in items:
        label = item.get("label", "")
        candidates = item.get("candidates", [])
        valid_codes_by_label[label] = {c.get("code") for c in candidates if c.get("code")}

    # Build prompt with items formatted for batch processing
    system_prompt = get_metric_mapping_decision_system()
    user_template = get_metric_mapping_decision_batch_prefix()
    output_schema = get_metric_mapping_decision_batch_schema()

    # Format items for the prompt
    formatted_items = []
    for item in items:
        label = item.get("label", "")
        candidates = item.get("candidates", [])
        formatted_items.append({
            "label": label,
            "candidates": _format_candidates(candidates),
        })

    items_json = json.dumps(formatted_items, ensure_ascii=False)
    user_prompt = user_template.format(items=items_json)

    # Call LLM with structured outputs
    try:
        response = await ai_client.generate_text(
            prompt=user_prompt,
            system_instructions=system_prompt,
            response_mime_type="application/json",
            json_schema=output_schema,
        )
        content = response["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(
            "llm_batch_decision_api_error",
            extra={"items_count": len(items), "error": str(e)},
        )
        # Return unknown for all items on API error
        return [
            {
                "status": "unknown",
                "code": None,
                "confidence": 0.0,
                "reason": f"LLM API error: {str(e)}",
            }
            for _ in items
        ]

    # Parse JSON response
    try:
        result = json.loads(content)
    except json.JSONDecodeError as e:
        logger.warning(
            "llm_batch_decision_invalid_json",
            extra={"content": content[:500], "error": str(e)},
        )
        return [
            {
                "status": "unknown",
                "code": None,
                "confidence": 0.0,
                "reason": f"Invalid JSON response from LLM: {str(e)}",
            }
            for _ in items
        ]

    # Process each result
    llm_results = result.get("results", [])
    processed = []

    for i, item in enumerate(items):
        label = item.get("label", "")
        valid_codes = valid_codes_by_label.get(label, set())

        # Find matching result from LLM
        llm_result = None
        for r in llm_results:
            if r.get("label") == label:
                llm_result = r
                break

        if llm_result is None:
            # LLM didn't return result for this label
            logger.warning(
                "llm_batch_missing_result",
                extra={"label": label, "index": i},
            )
            processed.append({
                "status": "unknown",
                "code": None,
                "confidence": 0.0,
                "reason": "LLM did not return result for this label",
            })
            continue

        decision = llm_result.get("decision", "").lower()
        metric_code = llm_result.get("metric_code")
        confidence = float(llm_result.get("confidence", 0.0))
        reason = llm_result.get("reason", "")

        # Handle decision types
        if decision == "unknown":
            processed.append({
                "status": "unknown",
                "code": None,
                "confidence": confidence,
                "reason": reason,
            })
            continue

        if decision == "ambiguous":
            processed.append({
                "status": "ambiguous",
                "code": None,
                "confidence": confidence,
                "reason": reason,
            })
            continue

        if decision == "match":
            # Guardrail: Code must be from candidate list
            if metric_code not in valid_codes:
                logger.warning(
                    "llm_batch_decision_invalid_code",
                    extra={
                        "label": label,
                        "hallucinated_code": metric_code,
                        "valid_codes": list(valid_codes),
                    },
                )
                processed.append({
                    "status": "unknown",
                    "code": None,
                    "confidence": 0.0,
                    "reason": f"LLM returned invalid code: {metric_code} not in candidates",
                })
                continue

            # Guardrail: Confidence threshold
            if confidence < min_confidence:
                processed.append({
                    "status": "unknown",
                    "code": None,
                    "confidence": confidence,
                    "reason": f"Confidence {confidence:.2f} below threshold {min_confidence:.2f}",
                })
                continue

            # Success
            processed.append({
                "status": "mapped",
                "code": metric_code,
                "confidence": confidence,
                "reason": reason,
            })
            continue

        # Unknown decision type
        processed.append({
            "status": "unknown",
            "code": None,
            "confidence": 0.0,
            "reason": f"Unknown decision type: {decision}",
        })

    logger.info(
        "llm_batch_decision_completed",
        extra={
            "items_count": len(items),
            "mapped": sum(1 for r in processed if r["status"] == "mapped"),
            "unknown": sum(1 for r in processed if r["status"] == "unknown"),
            "ambiguous": sum(1 for r in processed if r["status"] == "ambiguous"),
        },
    )

    return processed
