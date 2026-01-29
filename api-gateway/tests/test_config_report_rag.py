"""Tests for Report RAG configuration settings."""

import pytest


@pytest.mark.unit
def test_report_rag_defaults_present():
    """Verify that Report RAG settings are present with expected defaults."""
    from app.core.config import Settings

    s = Settings()
    assert hasattr(s, "report_rag_top_k")
    assert hasattr(s, "report_rag_max_top_k")
    assert hasattr(s, "report_rag_similarity_threshold")
    assert hasattr(s, "report_rag_ambiguity_delta")


@pytest.mark.unit
def test_report_rag_default_values():
    """Verify that Report RAG settings have correct default values."""
    from app.core.config import Settings

    s = Settings()
    assert s.report_rag_top_k == 5
    assert s.report_rag_max_top_k == 50
    assert s.report_rag_similarity_threshold == 0.85
    assert s.report_rag_ambiguity_delta == 0.02
