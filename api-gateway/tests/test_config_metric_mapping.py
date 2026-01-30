"""Tests for metric mapping configuration."""

import pytest


@pytest.mark.unit
def test_metric_mapping_config_has_defaults():
    """Verify metric mapping config fields exist with defaults."""
    from app.core.config import settings

    assert hasattr(settings, "metric_mapping_top_k")
    assert hasattr(settings, "metric_mapping_llm_min_confidence")
    assert settings.metric_mapping_top_k == 10
    assert settings.metric_mapping_llm_min_confidence == 0.6


@pytest.mark.unit
def test_metric_mapping_top_k_is_positive():
    """top_k should be a positive integer."""
    from app.core.config import settings

    assert isinstance(settings.metric_mapping_top_k, int)
    assert settings.metric_mapping_top_k > 0


@pytest.mark.unit
def test_metric_mapping_confidence_in_range():
    """Confidence threshold should be between 0 and 1."""
    from app.core.config import settings

    assert 0.0 <= settings.metric_mapping_llm_min_confidence <= 1.0
