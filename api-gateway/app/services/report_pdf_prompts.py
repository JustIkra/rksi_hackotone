from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.core.prompt_loader import get_prompt_loader


@lru_cache(maxsize=1)
def _get_report_pdf_extraction_template() -> str:
    """Get raw template with placeholders."""
    loader = get_prompt_loader()
    return loader.get_prompt_text("report-pdf-extraction", "extraction_prompt")


def get_report_pdf_extraction_prompt(
    existing_metrics: list[dict[str, Any]] | None = None,
) -> str:
    """
    Get extraction prompt with existing metrics context.

    Args:
        existing_metrics: List of dicts with code, name_ru, description keys.
            If provided, LLM will try to use these names for better matching.

    Returns:
        Formatted prompt string
    """
    template = _get_report_pdf_extraction_template()

    if existing_metrics:
        metrics_str = "\n".join(
            f"- {m.get('name_ru') or m.get('name', '')} ({m.get('code', '')})"
            for m in existing_metrics[:100]  # Limit to avoid token overflow
        )
        template = template.replace(
            "{existing_metrics}",
            f"\n\nСуществующие метрики в системе (используй эти названия при совпадении):\n{metrics_str}",
        )
    else:
        template = template.replace("{existing_metrics}", "")

    return template


def get_report_pdf_extraction_schema() -> dict[str, Any] | None:
    """Get output_schema from report-pdf-extraction config for structured outputs."""
    loader = get_prompt_loader()
    cfg = loader.load("report-pdf-extraction")
    return cfg.get("output_schema")
