"""Tests for OpenRouter client text generation with json_schema support."""

import pytest

from app.clients.openrouter import OpenRouterClient, OpenRouterTransport


class MockTransport(OpenRouterTransport):
    """Mock transport for testing without network calls."""

    def __init__(self):
        self.requests = []

    async def request(self, method, url, headers=None, json=None, timeout=30.0):
        self.requests.append({"method": method, "url": url, "json": json})
        return {"choices": [{"message": {"content": '{"ok": true}'}}]}


@pytest.mark.asyncio
async def test_generate_text_supports_json_schema_response_format():
    """generate_text should use json_schema response_format when json_schema is provided."""
    transport = MockTransport()
    client = OpenRouterClient(api_key="test", transport=transport)

    schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
    }
    await client.generate_text(
        prompt="Return JSON",
        response_mime_type="application/json",
        json_schema=schema,
    )

    payload = transport.requests[0]["json"]
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["strict"] is True
    assert payload["response_format"]["json_schema"]["schema"] == schema

    await client.close()


@pytest.mark.asyncio
async def test_generate_text_uses_json_object_without_schema():
    """generate_text should use json_object when json_schema is not provided."""
    transport = MockTransport()
    client = OpenRouterClient(api_key="test", transport=transport)

    await client.generate_text(
        prompt="Return JSON",
        response_mime_type="application/json",
    )

    payload = transport.requests[0]["json"]
    assert payload["response_format"]["type"] == "json_object"
    assert "json_schema" not in payload["response_format"]

    await client.close()


@pytest.mark.asyncio
async def test_generate_text_no_response_format_for_text():
    """generate_text should not set response_format for text/plain."""
    transport = MockTransport()
    client = OpenRouterClient(api_key="test", transport=transport)

    await client.generate_text(
        prompt="Return text",
        response_mime_type="text/plain",
    )

    payload = transport.requests[0]["json"]
    assert "response_format" not in payload

    await client.close()
