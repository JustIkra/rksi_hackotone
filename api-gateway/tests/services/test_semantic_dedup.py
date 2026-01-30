"""
Unit tests for SemanticDeduplicationService.

Tests deduplication logic using mocked embedding generation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.unit
class TestSemanticDeduplicationService:
    """Tests for SemanticDeduplicationService logic."""

    def test_cosine_similarity_identical(self):
        """Identical vectors should have similarity of 1.0."""
        from app.services.semantic_dedup import SemanticDeduplicationService

        service = SemanticDeduplicationService(db=MagicMock(), threshold=0.92)
        vec = [1.0, 0.0, 0.0]
        similarity = service._cosine_similarity(vec, vec)
        assert abs(similarity - 1.0) < 0.0001

    def test_cosine_similarity_orthogonal(self):
        """Orthogonal vectors should have similarity of 0.0."""
        from app.services.semantic_dedup import SemanticDeduplicationService

        service = SemanticDeduplicationService(db=MagicMock(), threshold=0.92)
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [0.0, 1.0, 0.0]
        similarity = service._cosine_similarity(vec_a, vec_b)
        assert abs(similarity) < 0.0001

    def test_cosine_similarity_opposite(self):
        """Opposite vectors should have similarity of -1.0."""
        from app.services.semantic_dedup import SemanticDeduplicationService

        service = SemanticDeduplicationService(db=MagicMock(), threshold=0.92)
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [-1.0, 0.0, 0.0]
        similarity = service._cosine_similarity(vec_a, vec_b)
        assert abs(similarity - (-1.0)) < 0.0001

    def test_cosine_similarity_zero_vector(self):
        """Zero vector should return 0 similarity."""
        from app.services.semantic_dedup import SemanticDeduplicationService

        service = SemanticDeduplicationService(db=MagicMock(), threshold=0.92)
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [0.0, 0.0, 0.0]
        similarity = service._cosine_similarity(vec_a, vec_b)
        assert similarity == 0.0

    def test_parse_numeric_value_valid(self):
        """Valid numeric values should be parsed correctly."""
        from app.services.semantic_dedup import SemanticDeduplicationService

        service = SemanticDeduplicationService(db=MagicMock(), threshold=0.92)
        assert service._parse_numeric_value("7.5") == 7.5
        assert service._parse_numeric_value("8,0") == 8.0
        assert service._parse_numeric_value("  9  ") == 9.0

    def test_parse_numeric_value_invalid(self):
        """Invalid values should return -inf."""
        from app.services.semantic_dedup import SemanticDeduplicationService

        service = SemanticDeduplicationService(db=MagicMock(), threshold=0.92)
        assert service._parse_numeric_value("invalid") == float("-inf")
        assert service._parse_numeric_value("") == float("-inf")

    def test_select_best_item_by_value(self):
        """Should select item with highest value."""
        from app.services.semantic_dedup import SemanticDeduplicationService

        service = SemanticDeduplicationService(db=MagicMock(), threshold=0.92)

        items = [
            {"label": "Metric A", "value": "7.0", "quotes": [], "page_numbers": []},
            {"label": "Metric B", "value": "9.0", "quotes": [], "page_numbers": []},
            {"label": "Metric C", "value": "8.0", "quotes": [], "page_numbers": []},
        ]
        indices = [0, 1, 2]

        best_idx = service._select_best_item(items, indices)
        assert best_idx == 1  # "Metric B" has value 9.0

    def test_select_best_item_tie_prefers_shorter_label(self):
        """On value tie, should prefer shorter label."""
        from app.services.semantic_dedup import SemanticDeduplicationService

        service = SemanticDeduplicationService(db=MagicMock(), threshold=0.92)

        items = [
            {"label": "Творческое мышление", "value": "8.0", "quotes": [], "page_numbers": []},
            {"label": "Творчество", "value": "8.0", "quotes": [], "page_numbers": []},
        ]
        indices = [0, 1]

        best_idx = service._select_best_item(items, indices)
        assert best_idx == 1  # "Творчество" is shorter


@pytest.mark.unit
class TestSemanticDeduplicationAsync:
    """Async tests for deduplication with mocked embeddings."""

    @pytest.mark.asyncio
    async def test_deduplicate_single_item(self):
        """Single item should be returned unchanged."""
        from app.services.semantic_dedup import SemanticDeduplicationService

        db_mock = MagicMock()
        service = SemanticDeduplicationService(db=db_mock, threshold=0.92)

        items = [{"label": "Metric A", "value": "7.0", "quotes": [], "page_numbers": []}]
        result = await service.deduplicate_items(items)

        assert result == items

    @pytest.mark.asyncio
    async def test_deduplicate_empty_list(self):
        """Empty list should return empty."""
        from app.services.semantic_dedup import SemanticDeduplicationService

        db_mock = MagicMock()
        service = SemanticDeduplicationService(db=db_mock, threshold=0.92)

        result = await service.deduplicate_items([])
        assert result == []

    @pytest.mark.asyncio
    async def test_deduplicate_groups_similar_items(self):
        """Items with high similarity should be grouped, keeping highest value."""
        from app.services.semantic_dedup import SemanticDeduplicationService

        db_mock = MagicMock()
        service = SemanticDeduplicationService(db=db_mock, threshold=0.92)

        # Mock embeddings: first two are very similar, third is different
        mock_embeddings = [
            [1.0, 0.0, 0.0],  # Item 0: "Творчество"
            [0.99, 0.1, 0.0],  # Item 1: "Творческое мышление" - similar to 0
            [0.0, 1.0, 0.0],  # Item 2: "Анализ" - different
        ]

        items = [
            {"label": "Творчество", "value": "7.0", "quotes": [], "page_numbers": []},
            {"label": "Творческое мышление", "value": "8.0", "quotes": [], "page_numbers": []},
            {"label": "Анализ", "value": "6.0", "quotes": [], "page_numbers": []},
        ]

        with patch.object(
            service._embedding_service,
            "generate_embeddings",
            new=AsyncMock(return_value=mock_embeddings),
        ):
            result = await service.deduplicate_items(items)

        # Should have 2 items: one from the similar group (value=8.0), and "Анализ"
        assert len(result) == 2
        # The similar group should keep the one with value 8.0
        values = sorted([item["value"] for item in result])
        assert values == ["6.0", "8.0"]

    @pytest.mark.asyncio
    async def test_deduplicate_preserves_dissimilar_items(self):
        """Dissimilar items should all be preserved."""
        from app.services.semantic_dedup import SemanticDeduplicationService

        db_mock = MagicMock()
        service = SemanticDeduplicationService(db=db_mock, threshold=0.92)

        # Mock embeddings: all orthogonal (dissimilar)
        mock_embeddings = [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]

        items = [
            {"label": "Metric A", "value": "7.0", "quotes": [], "page_numbers": []},
            {"label": "Metric B", "value": "8.0", "quotes": [], "page_numbers": []},
            {"label": "Metric C", "value": "6.0", "quotes": [], "page_numbers": []},
        ]

        with patch.object(
            service._embedding_service,
            "generate_embeddings",
            new=AsyncMock(return_value=mock_embeddings),
        ):
            result = await service.deduplicate_items(items)

        # All items should be preserved
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_deduplicate_handles_embedding_failure(self):
        """On embedding failure, should return original items."""
        from app.services.semantic_dedup import SemanticDeduplicationService

        db_mock = MagicMock()
        service = SemanticDeduplicationService(db=db_mock, threshold=0.92)

        items = [
            {"label": "Metric A", "value": "7.0", "quotes": [], "page_numbers": []},
            {"label": "Metric B", "value": "8.0", "quotes": [], "page_numbers": []},
        ]

        with patch.object(
            service._embedding_service,
            "generate_embeddings",
            new=AsyncMock(side_effect=Exception("API error")),
        ):
            result = await service.deduplicate_items(items)

        # Should return original items on failure
        assert result == items
