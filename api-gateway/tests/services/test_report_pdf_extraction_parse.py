import pytest


@pytest.mark.unit
def test_parse_pdf_metrics_accepts_numbers_and_strings():
    from app.services.report_pdf_extraction import _parse_pdf_metrics

    parsed = _parse_pdf_metrics(
        {"metrics": [{"label": "Leadership", "value": "7.5"}, {"label": "Teamwork", "value": 8}]}
    )
    assert parsed == [("Leadership", "7.5"), ("Teamwork", "8")]


@pytest.mark.unit
def test_parse_pdf_metrics_strips_whitespace():
    from app.services.report_pdf_extraction import _parse_pdf_metrics

    parsed = _parse_pdf_metrics(
        {"metrics": [{"label": "  Test Label  ", "value": " 5.5 "}]}
    )
    assert parsed == [("Test Label", "5.5")]


@pytest.mark.unit
def test_parse_pdf_metrics_ignores_missing_label():
    from app.services.report_pdf_extraction import _parse_pdf_metrics

    parsed = _parse_pdf_metrics(
        {"metrics": [{"value": "7"}, {"label": "Valid", "value": "8"}]}
    )
    assert parsed == [("Valid", "8")]


@pytest.mark.unit
def test_parse_pdf_metrics_ignores_missing_value():
    from app.services.report_pdf_extraction import _parse_pdf_metrics

    parsed = _parse_pdf_metrics(
        {"metrics": [{"label": "NoValue"}, {"label": "HasValue", "value": "9"}]}
    )
    assert parsed == [("HasValue", "9")]


@pytest.mark.unit
def test_parse_pdf_metrics_handles_empty_metrics():
    from app.services.report_pdf_extraction import _parse_pdf_metrics

    parsed = _parse_pdf_metrics({"metrics": []})
    assert parsed == []


@pytest.mark.unit
def test_parse_pdf_metrics_handles_missing_metrics_key():
    from app.services.report_pdf_extraction import _parse_pdf_metrics

    parsed = _parse_pdf_metrics({})
    assert parsed == []
