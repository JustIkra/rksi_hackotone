import pytest


@pytest.mark.unit
def test_report_pdf_prompt_loads():
    from app.services.report_pdf_prompts import get_report_pdf_extraction_prompt

    prompt = get_report_pdf_extraction_prompt()
    assert isinstance(prompt, str)
    assert "label" in prompt
    assert "value" in prompt
