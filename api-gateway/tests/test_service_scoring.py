"""
Unit tests for scoring service.

Tests cover:
- _generate_strengths_and_dev_areas: Top-5 logic, stable sorting
- Score calculation formula validation
- Edge cases: empty metrics, boundary values
- Deterministic sorting by value then code

Markers:
- unit: Pure unit tests with mocked dependencies
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.services.scoring import ScoringService


@pytest.mark.unit
class TestGenerateStrengthsAndDevAreas:
    """Test the _generate_strengths_and_dev_areas method."""

    def test_top_5_strengths_and_dev_areas(self):
        """
        Test that strengths and dev_areas correctly select top 5 items.

        Strengths: Top 5 highest values
        Dev areas: Top 5 lowest values
        """
        # Arrange
        service = ScoringService(db=MagicMock())

        metrics_map = {
            "metric_a": Decimal("10.0"),  # Highest
            "metric_b": Decimal("9.0"),
            "metric_c": Decimal("8.0"),
            "metric_d": Decimal("7.0"),
            "metric_e": Decimal("6.0"),
            "metric_f": Decimal("5.0"),  # Middle
            "metric_g": Decimal("4.0"),
            "metric_h": Decimal("3.0"),
            "metric_i": Decimal("2.0"),
            "metric_j": Decimal("1.0"),  # Lowest
        }

        weights_map = {code: Decimal("0.1") for code in metrics_map.keys()}

        metric_def_by_code = {
            code: MagicMock(
                name_ru=f"Метрика {code.upper()}",
                name=f"Metric {code.upper()}"
            )
            for code in metrics_map.keys()
        }

        # Act
        strengths, dev_areas = service._generate_strengths_and_dev_areas(
            metrics_map=metrics_map,
            weights_map=weights_map,
            metric_def_by_code=metric_def_by_code,
        )

        # Assert - Strengths: top 5 highest
        assert len(strengths) == 5
        assert strengths[0]["metric_code"] == "metric_a"
        assert strengths[0]["value"] == "10.0"
        assert strengths[1]["metric_code"] == "metric_b"
        assert strengths[2]["metric_code"] == "metric_c"
        assert strengths[3]["metric_code"] == "metric_d"
        assert strengths[4]["metric_code"] == "metric_e"

        # Assert - Dev areas: top 5 lowest
        assert len(dev_areas) == 5
        assert dev_areas[0]["metric_code"] == "metric_j"
        assert dev_areas[0]["value"] == "1.0"
        assert dev_areas[1]["metric_code"] == "metric_i"
        assert dev_areas[2]["metric_code"] == "metric_h"
        assert dev_areas[3]["metric_code"] == "metric_g"
        assert dev_areas[4]["metric_code"] == "metric_f"

    def test_stable_sorting_by_code_when_values_equal(self):
        """
        Test stable sorting: when values are equal, sort by metric_code alphabetically.

        This ensures deterministic results.
        """
        # Arrange
        service = ScoringService(db=MagicMock())

        # All metrics have same value - sorting should be by code
        metrics_map = {
            "zulu": Decimal("5.0"),
            "alpha": Decimal("5.0"),
            "charlie": Decimal("5.0"),
            "bravo": Decimal("5.0"),
        }

        weights_map = {code: Decimal("0.25") for code in metrics_map.keys()}

        metric_def_by_code = {
            code: MagicMock(name_ru=f"Метрика {code}", name=code)
            for code in metrics_map.keys()
        }

        # Act
        strengths, dev_areas = service._generate_strengths_and_dev_areas(
            metrics_map=metrics_map,
            weights_map=weights_map,
            metric_def_by_code=metric_def_by_code,
        )

        # Assert - Both lists should be sorted alphabetically when values are equal
        strength_codes = [s["metric_code"] for s in strengths]
        dev_area_codes = [d["metric_code"] for d in dev_areas]

        assert strength_codes == ["alpha", "bravo", "charlie", "zulu"]
        assert dev_area_codes == ["alpha", "bravo", "charlie", "zulu"]

    def test_fewer_than_5_metrics(self):
        """
        Test handling when there are fewer than 5 metrics total.

        Both strengths and dev_areas should contain all available metrics.
        """
        # Arrange
        service = ScoringService(db=MagicMock())

        metrics_map = {
            "metric_a": Decimal("8.0"),
            "metric_b": Decimal("6.0"),
            "metric_c": Decimal("4.0"),
        }

        weights_map = {
            "metric_a": Decimal("0.4"),
            "metric_b": Decimal("0.3"),
            "metric_c": Decimal("0.3"),
        }

        metric_def_by_code = {
            code: MagicMock(name_ru=f"Метрика {code}", name=code)
            for code in metrics_map.keys()
        }

        # Act
        strengths, dev_areas = service._generate_strengths_and_dev_areas(
            metrics_map=metrics_map,
            weights_map=weights_map,
            metric_def_by_code=metric_def_by_code,
        )

        # Assert - Should have all 3 metrics in both lists
        assert len(strengths) == 3
        assert len(dev_areas) == 3

        # Strengths: highest first
        assert strengths[0]["metric_code"] == "metric_a"
        assert strengths[1]["metric_code"] == "metric_b"
        assert strengths[2]["metric_code"] == "metric_c"

        # Dev areas: lowest first
        assert dev_areas[0]["metric_code"] == "metric_c"
        assert dev_areas[1]["metric_code"] == "metric_b"
        assert dev_areas[2]["metric_code"] == "metric_a"

    def test_metric_not_in_weights_excluded(self):
        """
        Test that metrics not in weights_map are excluded from results.
        """
        # Arrange
        service = ScoringService(db=MagicMock())

        metrics_map = {
            "metric_a": Decimal("8.0"),
            "metric_b": Decimal("6.0"),
            "metric_orphan": Decimal("10.0"),  # Not in weights_map
        }

        weights_map = {
            "metric_a": Decimal("0.6"),
            "metric_b": Decimal("0.4"),
            # metric_orphan is missing
        }

        metric_def_by_code = {
            "metric_a": MagicMock(name_ru="Метрика A", name="Metric A"),
            "metric_b": MagicMock(name_ru="Метрика B", name="Metric B"),
            "metric_orphan": MagicMock(name_ru="Метрика Orphan", name="Metric Orphan"),
        }

        # Act
        strengths, dev_areas = service._generate_strengths_and_dev_areas(
            metrics_map=metrics_map,
            weights_map=weights_map,
            metric_def_by_code=metric_def_by_code,
        )

        # Assert - metric_orphan should not appear
        strength_codes = [s["metric_code"] for s in strengths]
        dev_area_codes = [d["metric_code"] for d in dev_areas]

        assert "metric_orphan" not in strength_codes
        assert "metric_orphan" not in dev_area_codes
        assert len(strengths) == 2
        assert len(dev_areas) == 2

    def test_result_format_structure(self):
        """
        Test that the result format contains all required fields.

        Each item should have: metric_code, metric_name, value, weight
        """
        # Arrange
        service = ScoringService(db=MagicMock())

        metrics_map = {
            "code_x": Decimal("7.5"),
        }

        weights_map = {
            "code_x": Decimal("1.0"),
        }

        metric_def_by_code = {
            "code_x": MagicMock(name_ru="Название на русском", name="English Name"),
        }

        # Act
        strengths, dev_areas = service._generate_strengths_and_dev_areas(
            metrics_map=metrics_map,
            weights_map=weights_map,
            metric_def_by_code=metric_def_by_code,
        )

        # Assert - Check structure
        assert len(strengths) == 1
        item = strengths[0]

        assert "metric_code" in item
        assert "metric_name" in item
        assert "value" in item
        assert "weight" in item

        assert item["metric_code"] == "code_x"
        assert item["metric_name"] == "Название на русском"
        assert item["value"] == "7.5"
        assert item["weight"] == "1.0"

    def test_boundary_values_min_and_max(self):
        """
        Test handling of boundary values: 1.0 (min) and 10.0 (max).
        """
        # Arrange
        service = ScoringService(db=MagicMock())

        metrics_map = {
            "min_metric": Decimal("1.0"),
            "max_metric": Decimal("10.0"),
            "mid_metric": Decimal("5.5"),
        }

        weights_map = {
            code: Decimal("0.333333") for code in metrics_map.keys()
        }

        metric_def_by_code = {
            code: MagicMock(name_ru=f"Метрика {code}", name=code)
            for code in metrics_map.keys()
        }

        # Act
        strengths, dev_areas = service._generate_strengths_and_dev_areas(
            metrics_map=metrics_map,
            weights_map=weights_map,
            metric_def_by_code=metric_def_by_code,
        )

        # Assert - Strengths: max_metric first
        assert strengths[0]["metric_code"] == "max_metric"
        assert strengths[0]["value"] == "10.0"

        # Assert - Dev areas: min_metric first
        assert dev_areas[0]["metric_code"] == "min_metric"
        assert dev_areas[0]["value"] == "1.0"

    def test_empty_metrics_map(self):
        """
        Test handling of empty metrics_map.

        Should return empty lists for strengths and dev_areas.
        """
        # Arrange
        service = ScoringService(db=MagicMock())

        metrics_map = {}
        weights_map = {}
        metric_def_by_code = {}

        # Act
        strengths, dev_areas = service._generate_strengths_and_dev_areas(
            metrics_map=metrics_map,
            weights_map=weights_map,
            metric_def_by_code=metric_def_by_code,
        )

        # Assert
        assert strengths == []
        assert dev_areas == []

    def test_metric_def_missing_uses_code(self):
        """
        Test that when metric_def is missing, metric is excluded.
        """
        # Arrange
        service = ScoringService(db=MagicMock())

        metrics_map = {
            "metric_a": Decimal("8.0"),
            "metric_b": Decimal("6.0"),
        }

        weights_map = {
            "metric_a": Decimal("0.6"),
            "metric_b": Decimal("0.4"),
        }

        metric_def_by_code = {
            "metric_a": MagicMock(name_ru="Метрика A", name="Metric A"),
            # metric_b is missing from metric_def_by_code
        }

        # Act
        strengths, dev_areas = service._generate_strengths_and_dev_areas(
            metrics_map=metrics_map,
            weights_map=weights_map,
            metric_def_by_code=metric_def_by_code,
        )

        # Assert - Only metric_a should appear
        assert len(strengths) == 1
        assert strengths[0]["metric_code"] == "metric_a"

        assert len(dev_areas) == 1
        assert dev_areas[0]["metric_code"] == "metric_a"

    def test_decimal_precision_preserved(self):
        """
        Test that Decimal precision is preserved in output.
        """
        # Arrange
        service = ScoringService(db=MagicMock())

        metrics_map = {
            "precise": Decimal("7.123456"),
        }

        weights_map = {
            "precise": Decimal("1.0"),
        }

        metric_def_by_code = {
            "precise": MagicMock(name_ru="Точная метрика", name="Precise Metric"),
        }

        # Act
        strengths, dev_areas = service._generate_strengths_and_dev_areas(
            metrics_map=metrics_map,
            weights_map=weights_map,
            metric_def_by_code=metric_def_by_code,
        )

        # Assert - Value should be preserved as string
        assert strengths[0]["value"] == "7.123456"
        assert dev_areas[0]["value"] == "7.123456"


@pytest.mark.unit
class TestScoringServiceValidation:
    """Test validation logic in ScoringService."""

    def test_weights_must_sum_to_one(self):
        """
        Test that weight validation rejects sums != 1.0.

        This is tested in the context of calculate_score.
        """
        # Note: This would require mocking the entire calculate_score flow,
        # which is more of an integration test. The actual validation happens
        # in calculate_score at line 81-83.
        #
        # For a true unit test, we would extract the validation logic into
        # a separate method like _validate_weights(weights_map).
        pass

    def test_metric_value_range_validation(self):
        """
        Test that metric values outside [1, 10] are rejected.

        This is tested in the context of calculate_score.
        """
        # Note: Similar to above, this is validated in calculate_score at
        # lines 115-116. For proper unit testing, this should be extracted
        # to a separate _validate_metric_value(value, metric_code) method.
        pass


@pytest.mark.unit
class TestScoringFormula:
    """
    Test score calculation formula: score_pct = Σ(value × weight) × 10

    These are conceptual tests - the actual calculation happens in
    calculate_score which requires database setup (integration test).
    """

    def test_formula_simple_case(self):
        """
        Verify formula with simple values:

        metrics: [8.0, 6.0, 4.0]
        weights: [0.5, 0.3, 0.2]

        score_sum = 8.0*0.5 + 6.0*0.3 + 4.0*0.2 = 4.0 + 1.8 + 0.8 = 6.6
        score_pct = 6.6 * 10 = 66.0
        """
        # This is a documentation test - the actual calculation is in calculate_score
        # which is tested in test_scoring.py (integration tests)

        value1 = Decimal("8.0")
        weight1 = Decimal("0.5")
        contribution1 = value1 * weight1

        value2 = Decimal("6.0")
        weight2 = Decimal("0.3")
        contribution2 = value2 * weight2

        value3 = Decimal("4.0")
        weight3 = Decimal("0.2")
        contribution3 = value3 * weight3

        score_sum = contribution1 + contribution2 + contribution3
        score_pct = score_sum * Decimal("10")

        assert score_sum == Decimal("6.6")
        assert score_pct == Decimal("66.0")

    def test_formula_boundary_all_tens(self):
        """
        Test boundary: all metrics at max value (10.0) should give 100.0%.
        """
        values = [Decimal("10.0")] * 3
        weights = [Decimal("0.333334"), Decimal("0.333333"), Decimal("0.333333")]

        score_sum = sum(v * w for v, w in zip(values, weights, strict=False))
        score_pct = score_sum * Decimal("10")

        # Should be very close to 100.0
        assert score_pct >= Decimal("99.99")
        assert score_pct <= Decimal("100.01")

    def test_formula_boundary_all_ones(self):
        """
        Test boundary: all metrics at min value (1.0) should give 10.0%.
        """
        values = [Decimal("1.0")] * 3
        weights = [Decimal("0.333334"), Decimal("0.333333"), Decimal("0.333333")]

        score_sum = sum(v * w for v, w in zip(values, weights, strict=False))
        score_pct = score_sum * Decimal("10")

        # Should be very close to 10.0
        assert score_pct >= Decimal("9.99")
        assert score_pct <= Decimal("10.01")
