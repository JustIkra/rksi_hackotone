"""Tests for batch embedding generation."""

import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_generate_embeddings_calls_openrouter_once_for_list():
    """generate_embeddings should call OpenRouter API once for a batch of texts."""
    from app.services.embedding import EmbeddingService

    mock_client = AsyncMock()
    mock_client.create_embedding.return_value = {
        "data": [
            {"embedding": [0.0, 1.0], "index": 0},
            {"embedding": [1.0, 0.0], "index": 1},
        ]
    }

    svc = EmbeddingService(db=AsyncMock(), client=mock_client)
    embeddings = await svc.generate_embeddings(["a", "b"])

    assert embeddings == [[0.0, 1.0], [1.0, 0.0]]
    mock_client.create_embedding.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_embeddings_returns_in_correct_order():
    """generate_embeddings should return embeddings in the same order as input texts."""
    from app.services.embedding import EmbeddingService

    mock_client = AsyncMock()
    # Response index might be different from input order
    mock_client.create_embedding.return_value = {
        "data": [
            {"embedding": [0.1, 0.2, 0.3], "index": 0},
            {"embedding": [0.4, 0.5, 0.6], "index": 1},
            {"embedding": [0.7, 0.8, 0.9], "index": 2},
        ]
    }

    svc = EmbeddingService(db=AsyncMock(), client=mock_client)
    embeddings = await svc.generate_embeddings(["text1", "text2", "text3"])

    assert len(embeddings) == 3
    assert embeddings[0] == [0.1, 0.2, 0.3]
    assert embeddings[1] == [0.4, 0.5, 0.6]
    assert embeddings[2] == [0.7, 0.8, 0.9]


@pytest.mark.asyncio
async def test_generate_embeddings_single_text():
    """generate_embeddings should work for a single text."""
    from app.services.embedding import EmbeddingService

    mock_client = AsyncMock()
    mock_client.create_embedding.return_value = {
        "data": [{"embedding": [0.1, 0.2], "index": 0}]
    }

    svc = EmbeddingService(db=AsyncMock(), client=mock_client)
    embeddings = await svc.generate_embeddings(["single"])

    assert embeddings == [[0.1, 0.2]]


@pytest.mark.asyncio
async def test_generate_embeddings_empty_list():
    """generate_embeddings should return empty list for empty input."""
    from app.services.embedding import EmbeddingService

    mock_client = AsyncMock()
    svc = EmbeddingService(db=AsyncMock(), client=mock_client)
    embeddings = await svc.generate_embeddings([])

    assert embeddings == []
    mock_client.create_embedding.assert_not_awaited()
