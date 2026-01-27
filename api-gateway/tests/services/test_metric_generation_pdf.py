"""Tests for MetricGenerationService PDF extraction."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.metric_generation import ExtractedMetricData
from app.services.metric_generation import MetricGenerationService


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))
    return session


@pytest.fixture
def mock_openrouter_client():
    """Create a mock OpenRouter client."""
    client = MagicMock()
    client.generate_from_pdf = AsyncMock()
    client.generate_text = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.fixture
def service(mock_db_session, mock_openrouter_client):
    """Create MetricGenerationService with mocked dependencies."""
    return MetricGenerationService(
        db=mock_db_session,
        redis=None,
        openrouter_client=mock_openrouter_client,
    )


@pytest.mark.asyncio
async def test_extract_metrics_from_pdf_parses_response(service, mock_openrouter_client):
    """Test that extract_metrics_from_pdf correctly parses AI response."""
    mock_openrouter_client.generate_from_pdf.return_value = {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "metrics": [
                        {
                            "name": "Лидерство",
                            "value": 7.5,
                            "description": "Способность вести за собой",
                            "category": "Управленческие",
                        },
                        {
                            "name": "Коммуникация",
                            "value": 8.0,
                            "description": "Навыки общения",
                            "category": "Социальные",
                        },
                    ],
                    "document_summary": "Test document",
                })
            }
        }]
    }

    metrics = await service.extract_metrics_from_pdf(
        pdf_data=b"%PDF-1.4 test",
        existing_metrics=[],
        existing_synonyms=[],
        existing_categories=[],
    )

    assert len(metrics) == 2
    assert metrics[0].name == "Лидерство"
    assert metrics[0].value == 7.5
    assert metrics[1].name == "Коммуникация"
    assert metrics[1].value == 8.0


@pytest.mark.asyncio
async def test_extract_metrics_from_pdf_filters_no_value(service, mock_openrouter_client):
    """Test that metrics without numeric values are filtered out."""
    mock_openrouter_client.generate_from_pdf.return_value = {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "metrics": [
                        {"name": "Valid Metric", "value": 6.0},
                        {"name": "Recommendation", "value": None},
                        {"name": "Text Only", "description": "No value"},
                    ],
                })
            }
        }]
    }

    metrics = await service.extract_metrics_from_pdf(
        pdf_data=b"%PDF-1.4 test",
        existing_metrics=[],
        existing_synonyms=[],
        existing_categories=[],
    )

    assert len(metrics) == 1
    assert metrics[0].name == "Valid Metric"


@pytest.mark.asyncio
async def test_extract_metrics_from_pdf_calls_client_correctly(service, mock_openrouter_client):
    """Test that generate_from_pdf is called with correct parameters."""
    mock_openrouter_client.generate_from_pdf.return_value = {
        "choices": [{"message": {"content": '{"metrics": []}'}}]
    }

    pdf_data = b"%PDF-1.4 test content"
    await service.extract_metrics_from_pdf(
        pdf_data=pdf_data,
        existing_metrics=[{"code": "test", "name": "Test", "description": "Test metric"}],
        existing_synonyms=[],
        existing_categories=[],
    )

    mock_openrouter_client.generate_from_pdf.assert_called_once()
    call_kwargs = mock_openrouter_client.generate_from_pdf.call_args.kwargs

    assert call_kwargs["pdf_data"] == pdf_data
    assert call_kwargs["response_mime_type"] == "application/json"
    assert call_kwargs["timeout"] == 180
    assert "Test" in call_kwargs["prompt"]  # Existing metrics included in prompt
