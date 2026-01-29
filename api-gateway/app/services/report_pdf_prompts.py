from __future__ import annotations

from functools import lru_cache

from app.core.prompt_loader import get_prompt_loader


@lru_cache(maxsize=1)
def get_report_pdf_extraction_prompt() -> str:
    loader = get_prompt_loader()
    return loader.get_prompt_text("report-pdf-extraction", "extraction_prompt")
