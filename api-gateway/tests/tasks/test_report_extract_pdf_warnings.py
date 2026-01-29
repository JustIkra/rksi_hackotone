import pytest


@pytest.mark.unit
def test_build_warning_message_for_unknown_metrics():
    from app.tasks.extraction import _build_extract_warning

    msg, details = _build_extract_warning(unknown_labels=["A", "B"], ambiguous=[])
    assert "сообщите администрации" in msg.lower() or "сообщите администрации" in msg  # Case insensitive check
    assert details["unknown_count"] == 2


@pytest.mark.unit
def test_build_warning_message_for_ambiguous_metrics():
    from app.tasks.extraction import _build_extract_warning

    msg, details = _build_extract_warning(
        unknown_labels=[],
        ambiguous=[{"label": "Test", "candidates": [{"code": "A"}, {"code": "B"}]}]
    )
    assert details["ambiguous_count"] == 1
    assert "ambiguous" in details


@pytest.mark.unit
def test_build_warning_message_empty_when_no_issues():
    from app.tasks.extraction import _build_extract_warning

    msg, details = _build_extract_warning(unknown_labels=[], ambiguous=[])
    assert msg is None
    assert details is None
