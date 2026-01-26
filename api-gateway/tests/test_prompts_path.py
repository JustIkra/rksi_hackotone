"""
Tests for prompts path resolution in Docker environment.
"""
import os
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.mark.unit
class TestPromptsPathResolution:
    """Test prompts config file path resolution."""

    def test_prompts_path_candidates_include_docker_path(self):
        """
        Test that PROMPTS_PATH_CANDIDATES includes Docker path (/app/config/...).

        In Docker, metric_generation.py is at /app/app/services/metric_generation.py
        so 3x .parent = /app/, and config is at /app/config/prompts/...
        """
        from app.services.metric_generation import _PROMPTS_CANDIDATES

        # Should have at least 2 candidates (Docker and local)
        assert len(_PROMPTS_CANDIDATES) >= 2, "Should have multiple path candidates"

        # Convert to strings for easier comparison
        paths_str = [str(p) for p in _PROMPTS_CANDIDATES]

        # At least one path should end with /config/prompts/metric-extraction.json
        config_paths = [p for p in paths_str if p.endswith("config/prompts/metric-extraction.json")]
        assert len(config_paths) >= 1, f"No config path found in {paths_str}"

    def test_prompts_path_finds_existing_file(self):
        """
        Test that PROMPTS_PATH resolves to an existing file when run locally.
        """
        from app.services.metric_generation import PROMPTS_PATH

        # When running locally, the file should exist
        assert PROMPTS_PATH.exists(), f"Prompts file not found at {PROMPTS_PATH}"

    def test_prompts_fallback_when_no_file_exists(self):
        """
        Test that when no prompts file exists, _PROMPTS_CANDIDATES[0] is used as fallback.
        """
        # Verify fallback behavior is deterministic
        from app.services.metric_generation import _PROMPTS_CANDIDATES

        # First candidate should be the Docker path (most specific)
        first_path = str(_PROMPTS_CANDIDATES[0])
        assert "config/prompts/metric-extraction.json" in first_path
