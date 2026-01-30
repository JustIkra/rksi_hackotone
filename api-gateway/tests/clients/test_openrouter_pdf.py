"""Tests for OpenRouterClient PDF generation."""

import base64

import pytest

from app.clients.openrouter import OpenRouterClient, OpenRouterTransport


class MockTransport(OpenRouterTransport):
    """Mock transport that captures requests for testing."""

    def __init__(self, response: dict | None = None):
        self.requests: list[dict] = []
        self.response = response or {
            "choices": [{"message": {"content": '{"metrics": []}'}}]
        }

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
            "headers": headers,
            "json": json,
            "timeout": timeout,
        })
        return self.response


@pytest.mark.asyncio
async def test_generate_from_pdf_sends_correct_payload():
    """Test that generate_from_pdf sends PDF as base64 file attachment."""
    mock_transport = MockTransport()
    client = OpenRouterClient(
        api_key="test-key",
        model_vision="google/gemini-2.0-flash-001",
        transport=mock_transport,
    )

    pdf_bytes = b"%PDF-1.4 test content"
    prompt = "Extract metrics from this document"

    await client.generate_from_pdf(
        prompt=prompt,
        pdf_data=pdf_bytes,
        timeout=180,
    )

    assert len(mock_transport.requests) == 1
    req = mock_transport.requests[0]

    # Verify URL and method
    assert req["method"] == "POST"
    assert "/chat/completions" in req["url"]

    # Verify payload structure
    payload = req["json"]
    assert payload["model"] == "google/gemini-2.0-flash-001"
    assert "messages" in payload

    # Verify message content
    messages = payload["messages"]
    assert len(messages) == 1
    user_msg = messages[0]
    assert user_msg["role"] == "user"

    # Verify content has text and file parts
    content = user_msg["content"]
    assert len(content) == 2

    text_part = next(p for p in content if p["type"] == "text")
    assert text_part["text"] == prompt

    file_part = next(p for p in content if p["type"] == "file")
    assert file_part["file"]["filename"] == "document.pdf"

    # Verify base64 encoding
    expected_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
    assert file_part["file"]["file_data"] == f"data:application/pdf;base64,{expected_b64}"

    # Verify PDF engine is forced to Mistral OCR
    assert payload["plugins"] == [{"id": "file-parser", "pdf": {"engine": "mistral-ocr"}}]

    await client.close()


@pytest.mark.asyncio
async def test_generate_from_pdf_with_system_instructions():
    """Test that system instructions are included as system message."""
    mock_transport = MockTransport()
    client = OpenRouterClient(
        api_key="test-key",
        transport=mock_transport,
    )

    await client.generate_from_pdf(
        prompt="Extract metrics",
        pdf_data=b"%PDF-1.4 test",
        system_instructions="You are a document analysis expert.",
    )

    payload = mock_transport.requests[0]["json"]
    messages = payload["messages"]

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "You are a document analysis expert."
    assert messages[1]["role"] == "user"

    await client.close()


@pytest.mark.asyncio
async def test_generate_from_pdf_json_response_format():
    """Test that response_mime_type triggers JSON format."""
    mock_transport = MockTransport()
    client = OpenRouterClient(
        api_key="test-key",
        transport=mock_transport,
    )

    await client.generate_from_pdf(
        prompt="Extract metrics",
        pdf_data=b"%PDF-1.4 test",
        response_mime_type="application/json",
    )

    payload = mock_transport.requests[0]["json"]
    assert payload["response_format"] == {"type": "json_object"}

    await client.close()


@pytest.mark.asyncio
async def test_generate_from_pdf_custom_timeout():
    """Test that custom timeout is passed to transport."""
    mock_transport = MockTransport()
    client = OpenRouterClient(
        api_key="test-key",
        transport=mock_transport,
    )

    await client.generate_from_pdf(
        prompt="Extract metrics",
        pdf_data=b"%PDF-1.4 test",
        timeout=300,
    )

    assert mock_transport.requests[0]["timeout"] == 300

    await client.close()


@pytest.mark.asyncio
async def test_generate_from_pdf_with_json_schema():
    """Test that json_schema triggers structured outputs format."""
    mock_transport = MockTransport()
    client = OpenRouterClient(
        api_key="test-key",
        transport=mock_transport,
    )

    schema = {
        "type": "object",
        "properties": {
            "metrics": {
                "type": "array",
                "items": {"type": "object"},
            }
        },
        "required": ["metrics"],
    }

    await client.generate_from_pdf(
        prompt="Extract metrics",
        pdf_data=b"%PDF-1.4 test",
        response_mime_type="application/json",
        json_schema=schema,
    )

    payload = mock_transport.requests[0]["json"]
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["strict"] is True
    assert payload["response_format"]["json_schema"]["schema"] == schema

    await client.close()
