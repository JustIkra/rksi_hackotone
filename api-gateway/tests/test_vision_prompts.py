"""Tests for vision prompts module."""

import pytest

from app.services.vision_prompts import get_vision_prompt, IMPROVED_VISION_PROMPT


class TestVisionPrompts:
    """Tests for vision prompt loading."""

    def test_improved_vision_prompt_exists(self):
        """IMPROVED_VISION_PROMPT should be available for backward compatibility."""
        assert IMPROVED_VISION_PROMPT is not None
        assert len(IMPROVED_VISION_PROMPT) > 100
        assert "ФОРМАТ ОТВЕТА" in IMPROVED_VISION_PROMPT

    def test_get_vision_prompt_returns_string(self):
        """get_vision_prompt() should return prompt text."""
        prompt = get_vision_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_prompt_contains_required_sections(self):
        """Prompt should contain all required sections."""
        prompt = get_vision_prompt()

        required_sections = [
            "ФОРМАТ ОТВЕТА",
            "ГДЕ ИСКАТЬ ЗНАЧЕНИЯ",
            "РАЗРЕШЁННЫЕ МЕТРИКИ",
            "ПРАВИЛА",
            "ПАРНЫЕ ШКАЛЫ",
            "НОРМАЛИЗАЦИЯ НАЗВАНИЙ",
        ]

        for section in required_sections:
            assert section in prompt, f"Missing section: {section}"
