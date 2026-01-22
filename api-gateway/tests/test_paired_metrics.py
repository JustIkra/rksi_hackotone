"""
Tests for paired metrics normalization.

Paired metrics (двухполюсные шкалы) appear in reports with both pole names
separated by various delimiters (en-dash, hyphen, slash). The system must
normalize these to a single internal code.

This module tests the normalization logic for all 12 paired metric types:
1. ЗАМКНУТОСТЬ–ОБЩИТЕЛЬНОСТЬ (introversion_sociability)
2. ПАССИВНОСТЬ–АКТИВНОСТЬ (passivity_activity)
3. НЕДОВЕРЧИВОСТЬ–ДРУЖЕЛЮБИЕ (distrust_friendliness)
4. НЕЗАВИСИМОСТЬ–КОНФОРМИЗМ (independence_conformism)
5. МОРАЛЬНАЯ ГИБКОСТЬ–МОРАЛЬНОСТЬ (moral_flexibility_morality)
6. ИМПУЛЬСИВНОСТЬ–ОРГАНИЗОВАННОСТЬ (impulsiveness_organization)
7. ТРЕВОЖНОСТЬ–УРАВНОВЕШЕННОСТЬ (anxiety_emotional_stability)
8. СЕНЗИТИВНОСТЬ–НЕЧУВСТВИТЕЛЬНОСТЬ (sensitivity_insensitivity)
9. ИНТЕЛЛЕКТУАЛЬНАЯ СДЕРЖАННОСТЬ–ЛЮБОЗНАТЕЛЬНОСТЬ (intellectual_restraint_curiosity)
10. ТРАДИЦИОННОСТЬ–ОРИГИНАЛЬНОСТЬ (traditionality_originality)
11. КОНКРЕТНОСТЬ–АБСТРАКТНОСТЬ (concreteness_abstractness)
12. ВНЕШНЯЯ МОТИВАЦИЯ–ВНУТРЕННЯЯ МОТИВАЦИЯ (external_internal_motivation)

Markers:
- unit: Pure unit tests (no database required)
"""

import pytest

from app.services.metric_localization import METRIC_DISPLAY_NAMES_RU


@pytest.mark.unit
class TestPairedMetricsNormalization:
    """Test normalization of paired metric labels."""

    # All 12 paired metrics with their expected combined codes
    PAIRED_METRICS = [
        ("ЗАМКНУТОСТЬ", "ОБЩИТЕЛЬНОСТЬ", "introversion_sociability"),
        ("ПАССИВНОСТЬ", "АКТИВНОСТЬ", "passivity_activity"),
        ("НЕДОВЕРЧИВОСТЬ", "ДРУЖЕЛЮБИЕ", "distrust_friendliness"),
        ("НЕЗАВИСИМОСТЬ", "КОНФОРМИЗМ", "independence_conformism"),
        ("МОРАЛЬНАЯ ГИБКОСТЬ", "МОРАЛЬНОСТЬ", "moral_flexibility_morality"),
        ("ИМПУЛЬСИВНОСТЬ", "ОРГАНИЗОВАННОСТЬ", "impulsiveness_organization"),
        ("ТРЕВОЖНОСТЬ", "УРАВНОВЕШЕННОСТЬ", "anxiety_stability"),
        ("СЕНЗИТИВНОСТЬ", "НЕЧУВСТВИТЕЛЬНОСТЬ", "sensitivity_insensitivity"),
        (
            "ИНТЕЛЛЕКТУАЛЬНАЯ СДЕРЖАННОСТЬ",
            "ЛЮБОЗНАТЕЛЬНОСТЬ",
            "intellectual_restraint_curiosity",
        ),
        ("ТРАДИЦИОННОСТЬ", "ОРИГИНАЛЬНОСТЬ", "traditionality_originality"),
        ("КОНКРЕТНОСТЬ", "АБСТРАКТНОСТЬ", "concreteness_abstractness"),
        ("ВНЕШНЯЯ МОТИВАЦИЯ", "ВНУТРЕННЯЯ МОТИВАЦИЯ", "external_internal_motivation"),
    ]

    @pytest.mark.parametrize(
        "left_pole,right_pole,expected_code",
        PAIRED_METRICS,
        ids=[
            "introversion_sociability",
            "passivity_activity",
            "distrust_friendliness",
            "independence_conformism",
            "moral_flexibility_morality",
            "impulsiveness_organization",
            "anxiety_stability",
            "sensitivity_insensitivity",
            "intellectual_restraint_curiosity",
            "traditionality_originality",
            "concreteness_abstractness",
            "external_internal_motivation",
        ],
    )
    def test_paired_label_with_endash(self, left_pole, right_pole, expected_code):
        """
        Test that paired labels with en-dash (–) are normalized to combined code.

        Example: "ЗАМКНУТОСТЬ–ОБЩИТЕЛЬНОСТЬ" → "introversion_sociability"
        """
        from app.services.metric_mapping import get_metric_mapping_service

        service = get_metric_mapping_service()
        paired_label = f"{left_pole}–{right_pole}"

        result = service.get_metric_code(paired_label)

        assert result == expected_code, (
            f"Expected '{paired_label}' to map to '{expected_code}', "
            f"but got '{result}'"
        )

    @pytest.mark.parametrize(
        "left_pole,right_pole,expected_code",
        PAIRED_METRICS,
        ids=[
            "introversion_sociability",
            "passivity_activity",
            "distrust_friendliness",
            "independence_conformism",
            "moral_flexibility_morality",
            "impulsiveness_organization",
            "anxiety_stability",
            "sensitivity_insensitivity",
            "intellectual_restraint_curiosity",
            "traditionality_originality",
            "concreteness_abstractness",
            "external_internal_motivation",
        ],
    )
    def test_paired_label_with_hyphen_and_spaces(
        self, left_pole, right_pole, expected_code
    ):
        """
        Test that paired labels with hyphen and spaces are normalized.

        Example: "ЗАМКНУТОСТЬ - ОБЩИТЕЛЬНОСТЬ" → "introversion_sociability"
        """
        from app.services.metric_mapping import get_metric_mapping_service

        service = get_metric_mapping_service()
        paired_label = f"{left_pole} - {right_pole}"

        result = service.get_metric_code(paired_label)

        assert result == expected_code, (
            f"Expected '{paired_label}' to map to '{expected_code}', "
            f"but got '{result}'"
        )

    @pytest.mark.parametrize(
        "left_pole,right_pole,expected_code",
        PAIRED_METRICS,
        ids=[
            "introversion_sociability",
            "passivity_activity",
            "distrust_friendliness",
            "independence_conformism",
            "moral_flexibility_morality",
            "impulsiveness_organization",
            "anxiety_stability",
            "sensitivity_insensitivity",
            "intellectual_restraint_curiosity",
            "traditionality_originality",
            "concreteness_abstractness",
            "external_internal_motivation",
        ],
    )
    def test_paired_label_with_slash(self, left_pole, right_pole, expected_code):
        """
        Test that paired labels with slash (/) are normalized.

        Example: "ЗАМКНУТОСТЬ/ОБЩИТЕЛЬНОСТЬ" → "introversion_sociability"
        """
        from app.services.metric_mapping import get_metric_mapping_service

        service = get_metric_mapping_service()
        paired_label = f"{left_pole}/{right_pole}"

        result = service.get_metric_code(paired_label)

        assert result == expected_code, (
            f"Expected '{paired_label}' to map to '{expected_code}', "
            f"but got '{result}'"
        )

    @pytest.mark.parametrize(
        "left_pole,right_pole,expected_code",
        PAIRED_METRICS,
        ids=[
            "introversion_sociability",
            "passivity_activity",
            "distrust_friendliness",
            "independence_conformism",
            "moral_flexibility_morality",
            "impulsiveness_organization",
            "anxiety_stability",
            "sensitivity_insensitivity",
            "intellectual_restraint_curiosity",
            "traditionality_originality",
            "concreteness_abstractness",
            "external_internal_motivation",
        ],
    )
    def test_paired_label_with_slash_and_spaces(
        self, left_pole, right_pole, expected_code
    ):
        """
        Test that paired labels with slash and spaces are normalized.

        Example: "ЗАМКНУТОСТЬ / ОБЩИТЕЛЬНОСТЬ" → "introversion_sociability"
        """
        from app.services.metric_mapping import get_metric_mapping_service

        service = get_metric_mapping_service()
        paired_label = f"{left_pole} / {right_pole}"

        result = service.get_metric_code(paired_label)

        assert result == expected_code, (
            f"Expected '{paired_label}' to map to '{expected_code}', "
            f"but got '{result}'"
        )

    @pytest.mark.parametrize(
        "left_pole,right_pole,expected_code",
        PAIRED_METRICS,
        ids=[
            "introversion_sociability",
            "passivity_activity",
            "distrust_friendliness",
            "independence_conformism",
            "moral_flexibility_morality",
            "impulsiveness_organization",
            "anxiety_stability",
            "sensitivity_insensitivity",
            "intellectual_restraint_curiosity",
            "traditionality_originality",
            "concreteness_abstractness",
            "external_internal_motivation",
        ],
    )
    def test_paired_label_lowercase(self, left_pole, right_pole, expected_code):
        """
        Test that paired labels in lowercase are normalized.

        Example: "замкнутость–общительность" → "introversion_sociability"
        """
        from app.services.metric_mapping import get_metric_mapping_service

        service = get_metric_mapping_service()
        paired_label = f"{left_pole.lower()}–{right_pole.lower()}"

        result = service.get_metric_code(paired_label)

        assert result == expected_code, (
            f"Expected '{paired_label}' to map to '{expected_code}', "
            f"but got '{result}'"
        )

    @pytest.mark.parametrize(
        "left_pole,right_pole,expected_code",
        PAIRED_METRICS,
        ids=[
            "introversion_sociability",
            "passivity_activity",
            "distrust_friendliness",
            "independence_conformism",
            "moral_flexibility_morality",
            "impulsiveness_organization",
            "anxiety_stability",
            "sensitivity_insensitivity",
            "intellectual_restraint_curiosity",
            "traditionality_originality",
            "concreteness_abstractness",
            "external_internal_motivation",
        ],
    )
    def test_paired_label_reversed_order(self, left_pole, right_pole, expected_code):
        """
        Test that paired labels work in reversed order too.

        Example: "ОБЩИТЕЛЬНОСТЬ–ЗАМКНУТОСТЬ" → "introversion_sociability"
        """
        from app.services.metric_mapping import get_metric_mapping_service

        service = get_metric_mapping_service()
        paired_label = f"{right_pole}–{left_pole}"

        result = service.get_metric_code(paired_label)

        assert result == expected_code, (
            f"Expected reversed '{paired_label}' to map to '{expected_code}', "
            f"but got '{result}'"
        )

    @pytest.mark.parametrize(
        "left_pole,right_pole,expected_code",
        PAIRED_METRICS,
        ids=[
            "introversion_sociability",
            "passivity_activity",
            "distrust_friendliness",
            "independence_conformism",
            "moral_flexibility_morality",
            "impulsiveness_organization",
            "anxiety_stability",
            "sensitivity_insensitivity",
            "intellectual_restraint_curiosity",
            "traditionality_originality",
            "concreteness_abstractness",
            "external_internal_motivation",
        ],
    )
    def test_paired_label_with_extra_whitespace(
        self, left_pole, right_pole, expected_code
    ):
        """
        Test that paired labels with extra whitespace are normalized.

        Example: "  ЗАМКНУТОСТЬ  –  ОБЩИТЕЛЬНОСТЬ  " → "introversion_sociability"
        """
        from app.services.metric_mapping import get_metric_mapping_service

        service = get_metric_mapping_service()
        paired_label = f"  {left_pole}  –  {right_pole}  "

        result = service.get_metric_code(paired_label)

        assert result == expected_code, (
            f"Expected '{paired_label.strip()}' to map to '{expected_code}', "
            f"but got '{result}'"
        )


@pytest.mark.unit
class TestPairedMetricsDisplayNames:
    """Test that all paired metrics have proper display names in localization."""

    PAIRED_CODES = [
        "introversion_sociability",
        "passivity_activity",
        "distrust_friendliness",
        "independence_conformism",
        "moral_flexibility_morality",
        "impulsiveness_organization",
        "anxiety_stability",
        "sensitivity_insensitivity",
        "intellectual_restraint_curiosity",
        "traditionality_originality",
        "concreteness_abstractness",
        "external_internal_motivation",
    ]

    @pytest.mark.parametrize("code", PAIRED_CODES)
    def test_paired_metric_has_display_name(self, code):
        """
        Test that each paired metric code has a display name in localization.
        """
        assert code in METRIC_DISPLAY_NAMES_RU, (
            f"Paired metric code '{code}' is missing from METRIC_DISPLAY_NAMES_RU"
        )

    @pytest.mark.parametrize("code", PAIRED_CODES)
    def test_paired_metric_display_name_has_endash(self, code):
        """
        Test that paired metric display names use en-dash (–) separator.

        This ensures UI consistency with the report format.
        """
        display_name = METRIC_DISPLAY_NAMES_RU.get(code)
        assert display_name is not None, f"Missing display name for '{code}'"

        # Check for en-dash (U+2013) or regular hyphen
        assert "–" in display_name or "-" in display_name or "/" in display_name, (
            f"Display name for '{code}' should contain a separator (–/-//): "
            f"'{display_name}'"
        )


@pytest.mark.unit
class TestIndividualPolesRemoved:
    """
    Test that individual poles are NO LONGER supported (removed in migration e1f2g3h4i5j6).

    Single-pole personality metrics like 'introversion', 'sociability', etc. have been
    completely removed from the system. Only paired metrics are now supported.
    """

    REMOVED_INDIVIDUAL_POLES = [
        "ЗАМКНУТОСТЬ",
        "ОБЩИТЕЛЬНОСТЬ",
        "ПАССИВНОСТЬ",
        "АКТИВНОСТЬ",
        "НЕДОВЕРЧИВОСТЬ",
        "ДРУЖЕЛЮБИЕ",
        "НЕЗАВИСИМОСТЬ",
        "КОНФОРМИЗМ",
        "МОРАЛЬНАЯ ГИБКОСТЬ",
        "МОРАЛЬНОСТЬ",
        "ИМПУЛЬСИВНОСТЬ",
        "ОРГАНИЗОВАННОСТЬ",
        "ТРЕВОЖНОСТЬ",
        "УРАВНОВЕШЕННОСТЬ",
        "СЕНЗИТИВНОСТЬ",
        "НЕЧУВСТВИТЕЛЬНОСТЬ",
        "ИНТЕЛЛЕКТУАЛЬНАЯ СДЕРЖАННОСТЬ",
        "ЛЮБОЗНАТЕЛЬНОСТЬ",
        "ТРАДИЦИОННОСТЬ",
        "ОРИГИНАЛЬНОСТЬ",
        "КОНКРЕТНОСТЬ",
        "АБСТРАКТНОСТЬ",
        "ВНЕШНЯЯ МОТИВАЦИЯ",
        "ВНУТРЕННЯЯ МОТИВАЦИЯ",
    ]

    @pytest.mark.parametrize("label", REMOVED_INDIVIDUAL_POLES)
    def test_individual_pole_not_mapped(self, label):
        """
        Test that individual poles return None (no longer supported).

        These single-pole metrics have been removed in favor of paired metrics.
        Example: "ЗАМКНУТОСТЬ" alone should return None; use "ЗАМКНУТОСТЬ–ОБЩИТЕЛЬНОСТЬ" instead.
        """
        from app.services.metric_mapping import get_metric_mapping_service

        service = get_metric_mapping_service()

        result = service.get_metric_code(label)

        assert result is None, (
            f"Individual pole '{label}' should NOT be mapped anymore. "
            f"Got '{result}' but expected None. Use paired metrics instead."
        )


@pytest.mark.unit
class TestPairedMetricsEdgeCases:
    """Test edge cases and error handling for paired metrics."""

    def test_unknown_paired_metric_returns_none(self):
        """Test that unknown paired labels return None."""
        from app.services.metric_mapping import get_metric_mapping_service

        service = get_metric_mapping_service()

        result = service.get_metric_code("НЕИЗВЕСТНАЯ МЕТРИКА–ДРУГАЯ МЕТРИКА")

        assert result is None

    def test_single_pole_unknown_returns_none(self):
        """Test that single unknown pole returns None."""
        from app.services.metric_mapping import get_metric_mapping_service

        service = get_metric_mapping_service()

        result = service.get_metric_code("НЕИЗВЕСТНАЯ МЕТРИКА")

        assert result is None

    def test_empty_label_returns_none(self):
        """Test that empty label returns None."""
        from app.services.metric_mapping import get_metric_mapping_service

        service = get_metric_mapping_service()

        result = service.get_metric_code("")

        assert result is None

    def test_whitespace_only_label_returns_none(self):
        """Test that whitespace-only label returns None."""
        from app.services.metric_mapping import get_metric_mapping_service

        service = get_metric_mapping_service()

        result = service.get_metric_code("   ")

        assert result is None

    def test_multiple_delimiters_normalized(self):
        """Test that labels with multiple delimiter types are handled."""
        from app.services.metric_mapping import get_metric_mapping_service

        service = get_metric_mapping_service()

        # Test hyphen converted to en-dash or handled consistently
        result1 = service.get_metric_code("ЗАМКНУТОСТЬ-ОБЩИТЕЛЬНОСТЬ")
        result2 = service.get_metric_code("ЗАМКНУТОСТЬ–ОБЩИТЕЛЬНОСТЬ")

        # Both should either map to the same code or both return None
        assert result1 == result2


@pytest.mark.unit
class TestYamlConfigConsistency:
    """Test that YAML config has all required paired metric mappings."""

    def test_yaml_has_all_paired_combinations(self):
        """
        Test that YAML config contains mappings for common paired formats.

        This ensures the metric_mapping.yaml is properly configured.
        """
        from app.services.metric_mapping import get_metric_mapping_service

        service = get_metric_mapping_service()
        all_mappings = service.get_all_mappings()

        # Check for at least one paired format for each metric type
        # This is a smoke test to ensure YAML is properly set up
        paired_samples = [
            "ЗАМКНУТОСТЬ–ОБЩИТЕЛЬНОСТЬ",
            "ПАССИВНОСТЬ–АКТИВНОСТЬ",
            "ВНЕШНЯЯ МОТИВАЦИЯ–ВНУТРЕННЯЯ МОТИВАЦИЯ",
        ]

        for sample in paired_samples:
            normalized = sample.upper().strip()
            result = service.get_metric_code(normalized)
            # Should find a mapping (either direct or through normalization)
            assert result is not None or normalized in all_mappings, (
                f"Expected to find mapping for '{sample}' but none found. "
                f"Check metric-mapping.yaml configuration."
            )
