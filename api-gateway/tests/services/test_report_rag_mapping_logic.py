"""
Unit tests for RAG mapping service logic.

Tests the candidate selection algorithm with threshold and ambiguity detection.
"""

import pytest


@pytest.mark.unit
def test_select_best_candidate_threshold_and_ambiguity():
    """Test that ambiguous candidates (within delta) are rejected."""
    from app.services.report_rag_mapping import _select_candidate

    candidates = [
        {"code": "a", "similarity": 0.91},
        {"code": "b", "similarity": 0.90},
    ]
    code, status = _select_candidate(candidates, threshold=0.85, ambiguity_delta=0.02)
    assert code is None
    assert status == "ambiguous"


@pytest.mark.unit
def test_select_best_candidate_clear_winner():
    """Test that a clear winner (above threshold, large delta) is selected."""
    from app.services.report_rag_mapping import _select_candidate

    candidates = [
        {"code": "winner", "similarity": 0.95},
        {"code": "loser", "similarity": 0.80},
    ]
    code, status = _select_candidate(candidates, threshold=0.85, ambiguity_delta=0.02)
    assert code == "winner"
    assert status == "mapped"


@pytest.mark.unit
def test_select_best_candidate_below_threshold():
    """Test that candidates below threshold are rejected."""
    from app.services.report_rag_mapping import _select_candidate

    candidates = [
        {"code": "a", "similarity": 0.70},
        {"code": "b", "similarity": 0.60},
    ]
    code, status = _select_candidate(candidates, threshold=0.85, ambiguity_delta=0.02)
    assert code is None
    assert status == "unknown"


@pytest.mark.unit
def test_select_best_candidate_empty_list():
    """Test that empty candidate list returns unknown."""
    from app.services.report_rag_mapping import _select_candidate

    candidates = []
    code, status = _select_candidate(candidates, threshold=0.85, ambiguity_delta=0.02)
    assert code is None
    assert status == "unknown"


@pytest.mark.unit
def test_select_best_candidate_single_candidate_above_threshold():
    """Test that a single candidate above threshold is selected."""
    from app.services.report_rag_mapping import _select_candidate

    candidates = [
        {"code": "only_one", "similarity": 0.90},
    ]
    code, status = _select_candidate(candidates, threshold=0.85, ambiguity_delta=0.02)
    assert code == "only_one"
    assert status == "mapped"


@pytest.mark.unit
def test_select_best_candidate_second_below_threshold():
    """Test that if second candidate is below threshold, first is selected."""
    from app.services.report_rag_mapping import _select_candidate

    candidates = [
        {"code": "winner", "similarity": 0.90},
        {"code": "loser", "similarity": 0.80},
    ]
    # Second candidate is below threshold, so no ambiguity check needed
    code, status = _select_candidate(candidates, threshold=0.85, ambiguity_delta=0.02)
    assert code == "winner"
    assert status == "mapped"


@pytest.mark.unit
def test_norm_function():
    """Test text normalization function."""
    from app.services.report_rag_mapping import _norm

    assert _norm("  hello   world  ") == "HELLO WORLD"
    assert _norm("Test\n\tString") == "TEST STRING"
    assert _norm("already_normalized") == "ALREADY_NORMALIZED"
