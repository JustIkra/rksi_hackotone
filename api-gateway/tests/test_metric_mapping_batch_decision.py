"""Tests for batch LLM decision for metric mapping."""

import json

import pytest

from app.clients.openrouter import OpenRouterClient, OpenRouterTransport


class MockTransport(OpenRouterTransport):
    """Mock transport that captures requests for testing."""

    def __init__(self, response_content: str = ""):
        self.requests: list[dict] = []
        self.response_content = response_content

    async def request(
        self,
        method: str,
        url: str,
        headers: dict | None = None,
        json: dict | None = None,
        timeout: float = 30.0,
    ) -> dict:
        self.requests.append({
            "method": method,
            "url": url,
            "json": json,
        })
        return {"choices": [{"message": {"content": self.response_content}}]}


@pytest.mark.asyncio
async def test_decide_metric_mapping_batch_calls_llm_once():
    """decide_metric_mapping_batch should call LLM once for multiple items."""
    from app.services.metric_mapping_llm_decision import decide_metric_mapping_batch

    response = json.dumps({
        "results": [
            {"label": "Метрика А", "decision": "match", "metric_code": "CODE_A", "confidence": 0.9, "reason": "Exact match"},
            {"label": "Метрика Б", "decision": "unknown", "metric_code": None, "confidence": 0.3, "reason": "No match"},
        ]
    })

    transport = MockTransport(response_content=response)
    client = OpenRouterClient(api_key="test-key", transport=transport)

    items = [
        {"label": "Метрика А", "candidates": [{"code": "CODE_A", "similarity": 0.9, "name_ru": "A", "indexed_text": "A", "description": ""}]},
        {"label": "Метрика Б", "candidates": [{"code": "CODE_B", "similarity": 0.5, "name_ru": "B", "indexed_text": "B", "description": ""}]},
    ]

    results = await decide_metric_mapping_batch(
        ai_client=client,
        items=items,
    )

    # Should only make one API call
    assert len(transport.requests) == 1
    # Should return two results
    assert len(results) == 2
    assert results[0]["status"] == "mapped"
    assert results[0]["code"] == "CODE_A"
    assert results[1]["status"] == "unknown"
    assert results[1]["code"] is None

    await client.close()


@pytest.mark.asyncio
async def test_decide_metric_mapping_batch_validates_codes():
    """decide_metric_mapping_batch should reject hallucinated codes."""
    from app.services.metric_mapping_llm_decision import decide_metric_mapping_batch

    # LLM returns a code not in candidates
    response = json.dumps({
        "results": [
            {"label": "Метрика А", "decision": "match", "metric_code": "HALLUCINATED", "confidence": 0.9, "reason": "Wrong code"},
        ]
    })

    transport = MockTransport(response_content=response)
    client = OpenRouterClient(api_key="test-key", transport=transport)

    items = [
        {"label": "Метрика А", "candidates": [{"code": "CODE_A", "similarity": 0.9, "name_ru": "A", "indexed_text": "A", "description": ""}]},
    ]

    results = await decide_metric_mapping_batch(
        ai_client=client,
        items=items,
    )

    # Should reject the hallucinated code
    assert results[0]["status"] == "unknown"
    assert results[0]["code"] is None
    assert "invalid" in results[0]["reason"].lower() or "not in candidates" in results[0]["reason"].lower()

    await client.close()


@pytest.mark.asyncio
async def test_decide_metric_mapping_batch_empty_items():
    """decide_metric_mapping_batch should return empty list for empty input."""
    from app.services.metric_mapping_llm_decision import decide_metric_mapping_batch

    transport = MockTransport()
    client = OpenRouterClient(api_key="test-key", transport=transport)

    results = await decide_metric_mapping_batch(
        ai_client=client,
        items=[],
    )

    assert results == []
    # Should not make any API calls
    assert len(transport.requests) == 0

    await client.close()


@pytest.mark.asyncio
async def test_decide_metric_mapping_batch_uses_json_schema():
    """decide_metric_mapping_batch should use json_schema structured outputs."""
    from app.services.metric_mapping_llm_decision import decide_metric_mapping_batch

    response = json.dumps({
        "results": [
            {"label": "Test", "decision": "unknown", "metric_code": None, "confidence": 0.0, "reason": "No match"},
        ]
    })

    transport = MockTransport(response_content=response)
    client = OpenRouterClient(api_key="test-key", transport=transport)

    items = [
        {"label": "Test", "candidates": []},
    ]

    await decide_metric_mapping_batch(
        ai_client=client,
        items=items,
    )

    # Check that json_schema was used
    payload = transport.requests[0]["json"]
    assert payload["response_format"]["type"] == "json_schema"

    await client.close()
