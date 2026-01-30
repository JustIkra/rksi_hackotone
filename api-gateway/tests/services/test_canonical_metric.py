"""
Unit tests for CanonicalMetricService.

Tests canonical/alias resolution and merge logic.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


@pytest.mark.unit
class TestCanonicalMetricServiceLogic:
    """Tests for CanonicalMetricService helper methods."""

    def test_should_replace_higher_value_wins(self):
        """Higher value should replace existing."""
        from app.services.canonical_metric import CanonicalMetricService

        service = CanonicalMetricService(db=MagicMock())

        existing = MagicMock()
        existing.value = Decimal("7.0")
        existing.confidence = Decimal("0.9")

        incoming = MagicMock()
        incoming.value = Decimal("8.0")
        incoming.confidence = Decimal("0.5")

        result = service._should_replace(existing, incoming)
        assert result is True

    def test_should_replace_lower_value_does_not_win(self):
        """Lower value should not replace existing."""
        from app.services.canonical_metric import CanonicalMetricService

        service = CanonicalMetricService(db=MagicMock())

        existing = MagicMock()
        existing.value = Decimal("8.0")
        existing.confidence = Decimal("0.5")

        incoming = MagicMock()
        incoming.value = Decimal("7.0")
        incoming.confidence = Decimal("0.9")

        result = service._should_replace(existing, incoming)
        assert result is False

    def test_should_replace_tie_higher_confidence_wins(self):
        """On value tie, higher confidence should win."""
        from app.services.canonical_metric import CanonicalMetricService

        service = CanonicalMetricService(db=MagicMock())

        existing = MagicMock()
        existing.value = Decimal("8.0")
        existing.confidence = Decimal("0.7")

        incoming = MagicMock()
        incoming.value = Decimal("8.0")
        incoming.confidence = Decimal("0.9")

        result = service._should_replace(existing, incoming)
        assert result is True

    def test_should_replace_tie_existing_wins(self):
        """On complete tie, existing should win (don't migrate)."""
        from app.services.canonical_metric import CanonicalMetricService

        service = CanonicalMetricService(db=MagicMock())

        existing = MagicMock()
        existing.value = Decimal("8.0")
        existing.confidence = Decimal("0.9")

        incoming = MagicMock()
        incoming.value = Decimal("8.0")
        incoming.confidence = Decimal("0.9")

        result = service._should_replace(existing, incoming)
        assert result is False

    def test_should_replace_none_confidence_treated_as_zero(self):
        """None confidence should be treated as 0."""
        from app.services.canonical_metric import CanonicalMetricService

        service = CanonicalMetricService(db=MagicMock())

        existing = MagicMock()
        existing.value = Decimal("8.0")
        existing.confidence = None

        incoming = MagicMock()
        incoming.value = Decimal("8.0")
        incoming.confidence = Decimal("0.5")

        result = service._should_replace(existing, incoming)
        assert result is True


@pytest.mark.unit
class TestCanonicalMetricServiceAsync:
    """Async tests for CanonicalMetricService with mocked DB."""

    @pytest.mark.asyncio
    async def test_resolve_to_canonical_not_alias(self):
        """Non-alias metric should return same code."""
        from app.services.canonical_metric import CanonicalMetricService

        # Create mock metric without canonical_metric_id
        mock_metric = MagicMock()
        mock_metric.canonical_metric_id = None

        # Mock DB session
        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = mock_metric
        db_mock.execute = AsyncMock(return_value=result_mock)

        service = CanonicalMetricService(db=db_mock)
        result = await service.resolve_to_canonical("metric_code")

        assert result == "metric_code"

    @pytest.mark.asyncio
    async def test_resolve_to_canonical_is_alias(self):
        """Alias metric should return canonical code."""
        from app.services.canonical_metric import CanonicalMetricService

        canonical_id = uuid4()

        # Create mock alias metric
        mock_alias = MagicMock()
        mock_alias.canonical_metric_id = canonical_id

        # Mock DB session to return alias first, then canonical code
        db_mock = AsyncMock()

        # First call returns alias metric
        alias_result = MagicMock()
        alias_result.scalar_one_or_none.return_value = mock_alias

        # Second call returns canonical code
        canonical_result = MagicMock()
        canonical_result.scalar_one_or_none.return_value = "canonical_code"

        db_mock.execute = AsyncMock(side_effect=[alias_result, canonical_result])

        service = CanonicalMetricService(db=db_mock)
        result = await service.resolve_to_canonical("alias_code")

        assert result == "canonical_code"

    @pytest.mark.asyncio
    async def test_resolve_to_canonical_not_found(self):
        """Non-existent metric should return same code with warning."""
        from app.services.canonical_metric import CanonicalMetricService

        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db_mock.execute = AsyncMock(return_value=result_mock)

        service = CanonicalMetricService(db=db_mock)
        result = await service.resolve_to_canonical("nonexistent_code")

        assert result == "nonexistent_code"

    @pytest.mark.asyncio
    async def test_is_alias_true(self):
        """Metric with canonical_metric_id should be identified as alias."""
        from app.services.canonical_metric import CanonicalMetricService

        mock_metric = MagicMock()
        mock_metric.canonical_metric_id = uuid4()

        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = mock_metric
        db_mock.execute = AsyncMock(return_value=result_mock)

        service = CanonicalMetricService(db=db_mock)
        result = await service.is_alias("some_metric")

        assert result is True

    @pytest.mark.asyncio
    async def test_is_alias_false(self):
        """Metric without canonical_metric_id should not be alias."""
        from app.services.canonical_metric import CanonicalMetricService

        mock_metric = MagicMock()
        mock_metric.canonical_metric_id = None

        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = mock_metric
        db_mock.execute = AsyncMock(return_value=result_mock)

        service = CanonicalMetricService(db=db_mock)
        result = await service.is_alias("some_metric")

        assert result is False

    @pytest.mark.asyncio
    async def test_merge_metrics_same_code_raises(self):
        """Merging metric with itself should raise error."""
        from app.services.canonical_metric import CanonicalMetricService

        db_mock = AsyncMock()
        service = CanonicalMetricService(db=db_mock)

        with pytest.raises(ValueError, match="Cannot merge metric with itself"):
            await service.merge_metrics("same_code", "same_code")

    @pytest.mark.asyncio
    async def test_merge_metrics_alias_not_found_raises(self):
        """Merging non-existent alias should raise error."""
        from app.services.canonical_metric import CanonicalMetricService

        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db_mock.execute = AsyncMock(return_value=result_mock)

        service = CanonicalMetricService(db=db_mock)

        with pytest.raises(ValueError, match="Alias metric 'missing_alias' not found"):
            await service.merge_metrics("missing_alias", "canonical")

    @pytest.mark.asyncio
    async def test_merge_metrics_canonical_not_found_raises(self):
        """Merging with non-existent canonical should raise error."""
        from app.services.canonical_metric import CanonicalMetricService

        alias_metric = MagicMock()
        alias_metric.code = "alias_code"

        db_mock = AsyncMock()

        # First call returns alias, second returns None (canonical not found)
        alias_result = MagicMock()
        alias_result.scalar_one_or_none.return_value = alias_metric

        canonical_result = MagicMock()
        canonical_result.scalar_one_or_none.return_value = None

        db_mock.execute = AsyncMock(side_effect=[alias_result, canonical_result])

        service = CanonicalMetricService(db=db_mock)

        with pytest.raises(ValueError, match="Canonical metric 'missing_canonical' not found"):
            await service.merge_metrics("alias_code", "missing_canonical")
