"""
Unit tests for embedding service.

Tests cover:
- Building index text from metric data
- Generating embeddings via OpenRouter client
- Indexing metrics (create and update)
- Similarity search (marked as integration test)
- Embedding statistics

Markers:
- unit: Pure unit tests with mocked dependencies
- integration: Tests requiring pgvector database
"""

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.openrouter import OpenRouterClient, OpenRouterTransport
from app.db.models import MetricDef, MetricEmbedding, MetricSynonym
from app.services.embedding import EmbeddingService


class MockTransport(OpenRouterTransport):
    """Mock transport for testing without actual HTTP requests."""

    def __init__(self, responses: list[dict[str, Any]] | None = None):
        self.responses = responses or []
        self.call_index = 0
        self.requests: list[dict[str, Any]] = []

    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Record request and return mock response."""
        self.requests.append({
            "method": method,
            "url": url,
            "headers": headers,
            "json": json,
            "timeout": timeout,
        })

        if self.call_index < len(self.responses):
            response = self.responses[self.call_index]
            self.call_index += 1
            return response

        # Default embedding response
        return {
            "data": [{"embedding": [0.1] * 3072, "index": 0}],
            "model": "openai/text-embedding-3-large",
            "usage": {"prompt_tokens": 10, "total_tokens": 10},
        }

    async def close(self) -> None:
        pass


def create_mock_embedding(dimensions: int = 3072) -> list[float]:
    """Create a mock embedding vector."""
    return [0.1] * dimensions


@pytest.mark.unit
class TestBuildIndexText:
    """Test the _build_index_text method."""

    def setup_method(self):
        """Set up test service with mocked db."""
        self.mock_db = MagicMock()
        self.service = EmbeddingService(db=self.mock_db)

    def test_build_index_text_all_fields(self):
        """
        Test building index text with all fields populated.
        """
        # Arrange
        metric = MagicMock(spec=MetricDef)
        metric.name = "Attention Span"
        metric.name_ru = "Концентрация внимания"
        metric.description = "Ability to focus on tasks"
        synonyms = ["focus", "concentration", "attentiveness"]

        # Act
        result = self.service._build_index_text(metric, synonyms)

        # Assert
        assert "Attention Span" in result
        assert "Концентрация внимания" in result
        assert "Ability to focus on tasks" in result
        assert "focus" in result
        assert "concentration" in result
        assert "attentiveness" in result
        # Parts are joined with " | " separator
        assert " | " in result

    def test_build_index_text_name_only(self):
        """
        Test building index text with only name (minimal data).
        """
        # Arrange
        metric = MagicMock(spec=MetricDef)
        metric.name = "Memory"
        metric.name_ru = None
        metric.description = None
        synonyms = []

        # Act
        result = self.service._build_index_text(metric, synonyms)

        # Assert
        assert result == "Memory"
        # No separator when only one part
        assert " | " not in result

    def test_build_index_text_with_empty_name_ru(self):
        """
        Test that empty string name_ru is filtered out.
        """
        # Arrange
        metric = MagicMock(spec=MetricDef)
        metric.name = "Speed"
        metric.name_ru = ""
        metric.description = "Processing speed"
        synonyms = []

        # Act
        result = self.service._build_index_text(metric, synonyms)

        # Assert
        assert result == "Speed | Processing speed"

    def test_build_index_text_synonyms_joined(self):
        """
        Test that synonyms are joined with spaces.
        """
        # Arrange
        metric = MagicMock(spec=MetricDef)
        metric.name = "Accuracy"
        metric.name_ru = None
        metric.description = None
        synonyms = ["precision", "correctness", "exactness"]

        # Act
        result = self.service._build_index_text(metric, synonyms)

        # Assert
        # Synonyms should be space-joined
        assert "precision correctness exactness" in result


@pytest.mark.unit
class TestGenerateEmbedding:
    """Test the generate_embedding method."""

    @pytest.mark.asyncio
    async def test_generate_embedding_success(self):
        """
        Test successful embedding generation with mocked client.
        """
        # Arrange
        mock_transport = MockTransport(responses=[{
            "data": [{"embedding": [0.5, 0.3, 0.2] + [0.1] * 3069, "index": 0}],
            "model": "openai/text-embedding-3-large",
            "usage": {"prompt_tokens": 5, "total_tokens": 5},
        }])

        mock_client = OpenRouterClient(
            api_key="test-key",
            transport=mock_transport,
        )

        mock_db = MagicMock()
        service = EmbeddingService(db=mock_db, client=mock_client)

        # Act
        result = await service.generate_embedding("test text")

        # Assert
        assert isinstance(result, list)
        assert len(result) == 3072
        assert result[0] == 0.5
        assert result[1] == 0.3

        # Verify request was made to embeddings endpoint
        assert len(mock_transport.requests) == 1
        assert "/embeddings" in mock_transport.requests[0]["url"]

    @pytest.mark.asyncio
    async def test_generate_embedding_extracts_from_response(self):
        """
        Test that embedding is correctly extracted from nested response structure.
        """
        # Arrange
        expected_embedding = [float(i) / 3072 for i in range(3072)]
        mock_transport = MockTransport(responses=[{
            "data": [{"embedding": expected_embedding, "index": 0}],
            "model": "openai/text-embedding-3-large",
            "usage": {"prompt_tokens": 10, "total_tokens": 10},
        }])

        mock_client = OpenRouterClient(
            api_key="test-key",
            transport=mock_transport,
        )

        mock_db = MagicMock()
        service = EmbeddingService(db=mock_db, client=mock_client)

        # Act
        result = await service.generate_embedding("some metric name")

        # Assert
        assert result == expected_embedding

    @pytest.mark.asyncio
    async def test_generate_embedding_invalid_response_raises_error(self):
        """
        Test that invalid API response raises ValueError.
        """
        # Arrange - response missing 'data' key
        mock_transport = MockTransport(responses=[{
            "error": {"message": "Something went wrong"},
        }])

        mock_client = OpenRouterClient(
            api_key="test-key",
            transport=mock_transport,
        )

        mock_db = MagicMock()
        service = EmbeddingService(db=mock_db, client=mock_client)

        # Act & Assert
        with pytest.raises(ValueError, match="Failed to extract embedding"):
            await service.generate_embedding("test text")

    @pytest.mark.asyncio
    async def test_generate_embedding_empty_data_raises_error(self):
        """
        Test that empty data array raises ValueError.
        """
        # Arrange
        mock_transport = MockTransport(responses=[{
            "data": [],
            "model": "openai/text-embedding-3-large",
        }])

        mock_client = OpenRouterClient(
            api_key="test-key",
            transport=mock_transport,
        )

        mock_db = MagicMock()
        service = EmbeddingService(db=mock_db, client=mock_client)

        # Act & Assert
        with pytest.raises(ValueError, match="Failed to extract embedding"):
            await service.generate_embedding("test text")


@pytest.mark.unit
class TestIndexMetricUnit:
    """Unit tests for index_metric method with mocked database."""

    @pytest.mark.asyncio
    async def test_index_metric_not_found_raises_error(self):
        """
        Test that ValueError is raised when metric_def_id not found.
        """
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock execute to return empty result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = EmbeddingService(db=mock_db)

        # Act & Assert
        with pytest.raises(ValueError, match="not found"):
            await service.index_metric(uuid.uuid4())


@pytest.mark.unit
class TestGetEmbeddingStatsUnit:
    """Unit tests for get_embedding_stats method."""

    @pytest.mark.asyncio
    async def test_stats_calculation(self):
        """
        Test stats calculation with mocked database.
        """
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock for approved metrics count
        approved_result = MagicMock()
        approved_result.all.return_value = [(uuid.uuid4(),), (uuid.uuid4(),), (uuid.uuid4(),)]

        # Mock for embeddings count
        embeddings_result = MagicMock()
        embeddings_result.all.return_value = [(uuid.uuid4(),), (uuid.uuid4(),)]

        mock_db.execute.side_effect = [approved_result, embeddings_result]

        service = EmbeddingService(db=mock_db)

        # Act
        stats = await service.get_embedding_stats()

        # Assert
        assert stats["total_approved_metrics"] == 3
        assert stats["total_embeddings"] == 2
        assert stats["missing_embeddings"] == 1
        assert stats["coverage_percent"] == pytest.approx(66.67, rel=0.01)

    @pytest.mark.asyncio
    async def test_stats_zero_approved(self):
        """
        Test stats when no approved metrics exist.
        """
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock empty results
        empty_result = MagicMock()
        empty_result.all.return_value = []

        mock_db.execute.side_effect = [empty_result, empty_result]

        service = EmbeddingService(db=mock_db)

        # Act
        stats = await service.get_embedding_stats()

        # Assert
        assert stats["total_approved_metrics"] == 0
        assert stats["total_embeddings"] == 0
        assert stats["missing_embeddings"] == 0
        assert stats["coverage_percent"] == 0

    @pytest.mark.asyncio
    async def test_stats_full_coverage(self):
        """
        Test stats when all metrics have embeddings.
        """
        # Arrange
        mock_db = AsyncMock(spec=AsyncSession)

        # Same count for both
        result = MagicMock()
        result.all.return_value = [(uuid.uuid4(),), (uuid.uuid4(),)]

        mock_db.execute.side_effect = [result, result]

        service = EmbeddingService(db=mock_db)

        # Act
        stats = await service.get_embedding_stats()

        # Assert
        assert stats["total_approved_metrics"] == 2
        assert stats["total_embeddings"] == 2
        assert stats["missing_embeddings"] == 0
        assert stats["coverage_percent"] == 100.0


# Integration tests - require actual database with pgvector
# These tests require the metric_embedding table to exist (run migrations first)
# Mark as integration and skip if table doesn't exist

async def check_metric_embedding_table_exists(db_session: AsyncSession) -> bool:
    """Check if metric_embedding table exists in the database."""
    try:
        from sqlalchemy import text
        result = await db_session.execute(
            text("SELECT 1 FROM information_schema.tables WHERE table_name = 'metric_embedding'")
        )
        return result.scalar() is not None
    except Exception:
        return False


@pytest_asyncio.fixture
async def skip_if_no_embedding_table(db_session: AsyncSession):
    """Skip test if metric_embedding table doesn't exist."""
    exists = await check_metric_embedding_table_exists(db_session)
    if not exists:
        pytest.skip("metric_embedding table not found - run migrations first")


@pytest_asyncio.fixture
async def metric_def(db_session: AsyncSession) -> MetricDef:
    """
    Create an APPROVED metric definition for testing.
    """
    metric = MetricDef(
        id=uuid.uuid4(),
        code=f"TEST_METRIC_{uuid.uuid4().hex[:8]}",
        name="Test Metric",
        name_ru="Тестовая метрика",
        description="A metric for testing embedding service",
        moderation_status="APPROVED",
    )
    db_session.add(metric)
    await db_session.commit()
    await db_session.refresh(metric)
    return metric


@pytest_asyncio.fixture
async def metric_with_synonyms(db_session: AsyncSession) -> MetricDef:
    """
    Create an APPROVED metric with synonyms.
    """
    metric = MetricDef(
        id=uuid.uuid4(),
        code=f"SYNONYM_METRIC_{uuid.uuid4().hex[:8]}",
        name="Attention Span",
        name_ru="Концентрация",
        description="Ability to maintain focus",
        moderation_status="APPROVED",
    )
    db_session.add(metric)
    await db_session.flush()

    # Add synonyms
    for synonym_text in ["focus", "concentration", "attentiveness"]:
        synonym = MetricSynonym(
            metric_def_id=metric.id,
            synonym=f"{synonym_text}_{uuid.uuid4().hex[:6]}",
        )
        db_session.add(synonym)

    await db_session.commit()
    await db_session.refresh(metric)
    return metric


@pytest.mark.asyncio
@pytest.mark.integration
async def test_index_metric_creates_new_embedding(
    db_session: AsyncSession,
    metric_def: MetricDef,
    skip_if_no_embedding_table,
):
    """
    Integration test: index_metric creates new MetricEmbedding if none exists.

    Requires pgvector extension and actual database.
    """
    # Arrange
    mock_transport = MockTransport(responses=[{
        "data": [{"embedding": create_mock_embedding(), "index": 0}],
        "model": "openai/text-embedding-3-large",
        "usage": {"prompt_tokens": 5, "total_tokens": 5},
    }])

    mock_client = OpenRouterClient(
        api_key="test-key",
        transport=mock_transport,
    )

    service = EmbeddingService(db=db_session, client=mock_client)

    # Act
    result = await service.index_metric(metric_def.id)
    await db_session.commit()

    # Assert
    assert result is not None
    assert result.metric_def_id == metric_def.id
    assert result.indexed_text is not None
    assert "Test Metric" in result.indexed_text
    assert result.model is not None

    # Verify embedding was stored
    stored = await db_session.execute(
        select(MetricEmbedding).where(MetricEmbedding.metric_def_id == metric_def.id)
    )
    stored_embedding = stored.scalar_one_or_none()
    assert stored_embedding is not None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_index_metric_updates_existing_embedding(
    db_session: AsyncSession,
    metric_def: MetricDef,
    skip_if_no_embedding_table,
):
    """
    Integration test: index_metric updates existing MetricEmbedding.
    """
    # Arrange - create initial embedding
    initial_embedding = MetricEmbedding(
        metric_def_id=metric_def.id,
        embedding=create_mock_embedding(),
        indexed_text="old text",
        model="old-model",
        indexed_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    db_session.add(initial_embedding)
    await db_session.commit()
    await db_session.refresh(initial_embedding)

    old_indexed_at = initial_embedding.indexed_at

    mock_transport = MockTransport(responses=[{
        "data": [{"embedding": [0.9] * 3072, "index": 0}],
        "model": "openai/text-embedding-3-large",
        "usage": {"prompt_tokens": 5, "total_tokens": 5},
    }])

    mock_client = OpenRouterClient(
        api_key="test-key",
        transport=mock_transport,
    )

    service = EmbeddingService(db=db_session, client=mock_client)

    # Act
    result = await service.index_metric(metric_def.id)
    await db_session.commit()

    # Assert
    assert result.id == initial_embedding.id  # Same record updated
    assert result.indexed_text != "old text"
    assert result.indexed_at > old_indexed_at


@pytest.mark.asyncio
@pytest.mark.integration
async def test_index_metric_includes_synonyms(
    db_session: AsyncSession,
    metric_with_synonyms: MetricDef,
    skip_if_no_embedding_table,
):
    """
    Integration test: index_metric includes synonyms in indexed text.
    """
    # Arrange
    mock_transport = MockTransport(responses=[{
        "data": [{"embedding": create_mock_embedding(), "index": 0}],
        "model": "openai/text-embedding-3-large",
        "usage": {"prompt_tokens": 5, "total_tokens": 5},
    }])

    mock_client = OpenRouterClient(
        api_key="test-key",
        transport=mock_transport,
    )

    service = EmbeddingService(db=db_session, client=mock_client)

    # Act
    result = await service.index_metric(metric_with_synonyms.id)
    await db_session.commit()

    # Assert
    assert result is not None
    # Synonyms should be included in indexed text
    assert "focus" in result.indexed_text or "concentration" in result.indexed_text


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_embedding_stats_integration(
    db_session: AsyncSession,
    metric_def: MetricDef,
    skip_if_no_embedding_table,
):
    """
    Integration test: get_embedding_stats returns correct counts.
    """
    # Arrange
    mock_db = db_session
    service = EmbeddingService(db=mock_db)

    # Act
    stats = await service.get_embedding_stats()

    # Assert
    assert "total_approved_metrics" in stats
    assert "total_embeddings" in stats
    assert "missing_embeddings" in stats
    assert "coverage_percent" in stats
    assert "model" in stats
    assert "dimensions" in stats
    # At least the one metric we created should be counted
    assert stats["total_approved_metrics"] >= 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_delete_embedding(
    db_session: AsyncSession,
    metric_def: MetricDef,
    skip_if_no_embedding_table,
):
    """
    Integration test: delete_embedding removes the embedding record.
    """
    # Arrange - create embedding first
    embedding = MetricEmbedding(
        metric_def_id=metric_def.id,
        embedding=create_mock_embedding(),
        indexed_text="test text",
        model="test-model",
    )
    db_session.add(embedding)
    await db_session.commit()

    service = EmbeddingService(db=db_session)

    # Act
    result = await service.delete_embedding(metric_def.id)
    await db_session.commit()

    # Assert
    assert result is True

    # Verify deletion
    stored = await db_session.execute(
        select(MetricEmbedding).where(MetricEmbedding.metric_def_id == metric_def.id)
    )
    assert stored.scalar_one_or_none() is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_delete_embedding_not_found(
    db_session: AsyncSession,
    skip_if_no_embedding_table,
):
    """
    Integration test: delete_embedding returns False if not found.
    """
    # Arrange
    service = EmbeddingService(db=db_session)

    # Act
    result = await service.delete_embedding(uuid.uuid4())

    # Assert
    assert result is False


@pytest.mark.asyncio
async def test_service_close(db_session: AsyncSession):
    """
    Test that close() properly cleans up client resources.
    """
    # Arrange
    mock_transport = MockTransport()
    mock_client = OpenRouterClient(
        api_key="test-key",
        transport=mock_transport,
    )

    service = EmbeddingService(db=db_session, client=mock_client)

    # Act - should not raise
    await service.close()

    # Service should still be usable after close if client is re-provided
    # but _client should be cleared if we owned it
    # In this case we provided the client, so _owns_client is False
    assert service._client is not None  # We didn't own it


@pytest.mark.asyncio
async def test_service_close_owned_client(db_session: AsyncSession):
    """
    Test that close() clears client when service owns it.
    """
    # Arrange - service creates its own client
    with patch("app.services.embedding.settings") as mock_settings:
        mock_settings.openrouter_keys_list = ["test-key"]
        mock_settings.embedding_model = "test-model"

        service = EmbeddingService(db=db_session)  # No client provided

        # Simulate that _client was lazily created
        # For this test, we just check the ownership flag
        assert service._owns_client is True

    # Act
    await service.close()

    # Assert
    assert service._client is None


@pytest.mark.integration
@pytest.mark.skip(reason="Requires pgvector with actual similarity search - run manually")
async def test_find_similar(
    db_session: AsyncSession,
    metric_def: MetricDef,
):
    """
    Integration test: find_similar performs vector search.

    This test is skipped by default as it requires:
    1. pgvector extension installed
    2. Proper vector index on metric_embedding table
    3. Mock or real embeddings with meaningful similarities

    Run manually with: pytest -k test_find_similar --run-integration
    """
    # Arrange - create embedding for the metric
    embedding = MetricEmbedding(
        metric_def_id=metric_def.id,
        embedding=create_mock_embedding(),
        indexed_text="Test Metric | Тестовая метрика | A metric for testing",
        model="openai/text-embedding-3-large",
    )
    db_session.add(embedding)
    await db_session.commit()

    mock_transport = MockTransport(responses=[{
        "data": [{"embedding": create_mock_embedding(), "index": 0}],
        "model": "openai/text-embedding-3-large",
        "usage": {"prompt_tokens": 5, "total_tokens": 5},
    }])

    mock_client = OpenRouterClient(
        api_key="test-key",
        transport=mock_transport,
    )

    service = EmbeddingService(db=db_session, client=mock_client)

    # Act
    results = await service.find_similar("test metric", top_k=5, threshold=0.5)

    # Assert
    assert isinstance(results, list)
    # With identical embeddings, similarity should be 1.0
    if results:
        assert "metric_def_id" in results[0]
        assert "similarity" in results[0]
