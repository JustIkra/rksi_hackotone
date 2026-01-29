"""Tests for OpenRouterPoolClient PDF generation."""

import base64

import pytest

from app.clients.openrouter import OpenRouterTransport
from app.clients.openrouter_pool import OpenRouterPoolClient


class MockTransport(OpenRouterTransport):
    def __init__(self):
        self.requests: list[dict] = []

    async def request(self, method, url, headers=None, json=None, timeout=30.0):
        self.requests.append(
            {"method": method, "url": url, "headers": headers, "json": json, "timeout": timeout}
        )
        return {"choices": [{"message": {"content": '{"metrics": []}'}}]}


@pytest.mark.asyncio
async def test_pool_generate_from_pdf_sends_file_attachment():
    transport = MockTransport()
    pool = OpenRouterPoolClient(
        api_keys=["test-key"],
        model_vision="google/gemini-2.0-flash-001",
        transport=transport,
    )

    pdf_bytes = b"%PDF-1.4 test content"
    await pool.generate_from_pdf(
        prompt="Extract metrics",
        pdf_data=pdf_bytes,
        response_mime_type="application/json",
        timeout=180,
    )

    assert len(transport.requests) == 1
    payload = transport.requests[0]["json"]
    assert payload["model"] == "google/gemini-2.0-flash-001"
    assert payload["response_format"] == {"type": "json_object"}

    content = payload["messages"][0]["content"]
    file_part = next(p for p in content if p["type"] == "file")
    expected_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
    assert file_part["file"]["filename"] == "document.pdf"
    assert file_part["file"]["file_data"] == f"data:application/pdf;base64,{expected_b64}"

    await pool.close()
