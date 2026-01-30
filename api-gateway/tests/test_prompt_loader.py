"""Tests for prompt loader utility."""

import json
import tempfile
from pathlib import Path

import pytest

from app.core.prompt_loader import PromptLoader, PromptNotFoundError


class TestPromptLoader:
    """Tests for PromptLoader class."""

    def test_load_existing_prompt(self, tmp_path: Path):
        """Should load prompt from existing JSON file."""
        # Arrange
        prompt_file = tmp_path / "test-prompt.json"
        prompt_data = {"version": "1.0", "prompt": "Test prompt content"}
        prompt_file.write_text(json.dumps(prompt_data))

        loader = PromptLoader(prompts_dir=tmp_path)

        # Act
        result = loader.load("test-prompt")

        # Assert
        assert result == prompt_data
        assert result["prompt"] == "Test prompt content"

    def test_load_nonexistent_prompt_raises_error(self, tmp_path: Path):
        """Should raise PromptNotFoundError for missing file."""
        loader = PromptLoader(prompts_dir=tmp_path)

        with pytest.raises(PromptNotFoundError):
            loader.load("nonexistent")

    def test_load_with_fallback(self, tmp_path: Path):
        """Should return fallback when file not found."""
        loader = PromptLoader(prompts_dir=tmp_path)
        fallback = {"default": "fallback value"}

        result = loader.load("nonexistent", fallback=fallback)

        assert result == fallback

    def test_get_prompt_text(self, tmp_path: Path):
        """Should extract specific prompt text by key."""
        prompt_file = tmp_path / "test.json"
        prompt_data = {"vision_prompt": "Extract metrics", "other": "data"}
        prompt_file.write_text(json.dumps(prompt_data))

        loader = PromptLoader(prompts_dir=tmp_path)

        result = loader.get_prompt_text("test", "vision_prompt")

        assert result == "Extract metrics"

    def test_caching(self, tmp_path: Path):
        """Should cache loaded prompts."""
        prompt_file = tmp_path / "cached.json"
        prompt_file.write_text('{"value": 1}')

        loader = PromptLoader(prompts_dir=tmp_path)

        # First load
        result1 = loader.load("cached")
        # Modify file
        prompt_file.write_text('{"value": 2}')
        # Second load should return cached
        result2 = loader.load("cached")

        assert result1 == result2 == {"value": 1}

    def test_reload_clears_cache(self, tmp_path: Path):
        """Should clear cache on reload."""
        prompt_file = tmp_path / "reloadable.json"
        prompt_file.write_text('{"value": 1}')

        loader = PromptLoader(prompts_dir=tmp_path)
        loader.load("reloadable")

        prompt_file.write_text('{"value": 2}')
        loader.reload()

        result = loader.load("reloadable")
        assert result == {"value": 2}


def test_report_pdf_extraction_has_output_schema():
    """report-pdf-extraction.json must have output_schema for structured outputs."""
    from app.core.prompt_loader import get_prompt_loader

    loader = get_prompt_loader()
    cfg = loader.load("report-pdf-extraction")
    assert "output_schema" in cfg


def test_metric_mapping_decision_has_output_schema():
    """metric-mapping-decision.json must have output_schema for structured outputs."""
    from app.core.prompt_loader import get_prompt_loader

    loader = get_prompt_loader()
    cfg = loader.load("metric-mapping-decision")
    assert "output_schema" in cfg
