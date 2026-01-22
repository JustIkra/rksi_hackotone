"""
OpenRouter API client with OpenAI-compatible format.

Supports text generation and vision tasks through OpenRouter's unified API.
Uses the same interface as GeminiClient for drop-in compatibility.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.clients.exceptions import (
    OpenRouterAuthError,
    OpenRouterClientError,
    OpenRouterRateLimitError,
    OpenRouterServerError,
    OpenRouterServiceError,
    OpenRouterTimeoutError,
    OpenRouterValidationError,
)

logger = logging.getLogger(__name__)


class OpenRouterTransport(ABC):
    """
    Abstract transport layer for OpenRouter API calls.

    This interface allows mocking HTTP requests in tests without
    requiring actual network calls or complex patching.
    """

    @abstractmethod
    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Execute HTTP request and return parsed JSON response."""
        pass

    async def close(self) -> None:
        """Close transport resources."""
        pass


class HttpxTransport(OpenRouterTransport):
    """
    Production transport using httpx for actual HTTP requests.
    """

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create httpx client (lazy initialization)."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
                follow_redirects=True,
            )
        return self._client

    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Execute HTTP request with comprehensive error handling."""
        client = await self._get_client()

        try:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                json=json,
                timeout=timeout,
            )

            # Parse response
            try:
                data = response.json()
            except Exception:
                data = {"raw_text": response.text}

            # Map HTTP status codes to domain exceptions
            if response.status_code == 401:
                raise OpenRouterAuthError(
                    data.get("error", {}).get("message", "Invalid API key")
                )

            if response.status_code == 403:
                raise OpenRouterAuthError(
                    data.get("error", {}).get("message", "Access forbidden")
                )

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                retry_seconds = int(retry_after) if retry_after else None
                error_msg = data.get("error", {}).get("message", "Rate limit exceeded")

                # Check if service-level or key-level
                if "overloaded" in error_msg.lower():
                    raise OpenRouterServiceError(error_msg, status_code=429)
                raise OpenRouterRateLimitError(error_msg, retry_after=retry_seconds)

            if response.status_code in (400, 422):
                raise OpenRouterValidationError(
                    data.get("error", {}).get("message", f"Validation error: {response.text}")
                )

            if response.status_code == 503:
                raise OpenRouterServiceError(
                    data.get("error", {}).get("message", "Service temporarily unavailable")
                )

            if response.status_code >= 500:
                raise OpenRouterServerError(
                    data.get("error", {}).get("message", f"Server error: {response.status_code}"),
                    status_code=response.status_code,
                )

            if not response.is_success:
                raise OpenRouterClientError(
                    f"Unexpected status: {response.status_code}",
                    status_code=response.status_code,
                )

            return data

        except httpx.TimeoutException as e:
            raise OpenRouterTimeoutError(f"Request timed out: {e}") from e
        except httpx.RequestError as e:
            raise OpenRouterClientError(f"Request failed: {e}") from e

    async def close(self) -> None:
        """Close httpx client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None


class OpenRouterClient:
    """
    OpenRouter API client with OpenAI-compatible format.

    Maintains the same interface as GeminiClient for drop-in compatibility.
    """

    def __init__(
        self,
        api_key: str,
        model_text: str = "google/gemini-2.0-flash-001",
        model_vision: str = "google/gemini-2.0-flash-001",
        timeout_s: int = 30,
        max_retries: int = 3,
        transport: OpenRouterTransport | None = None,
        base_url: str = "https://openrouter.ai/api/v1",
        app_url: str = "",
        app_name: str = "Workers Proficiency Assessment",
    ):
        """
        Initialize OpenRouter client.

        Args:
            api_key: OpenRouter API key
            model_text: Model for text generation
            model_vision: Model for vision tasks
            timeout_s: Request timeout in seconds
            max_retries: Maximum retry attempts
            transport: Custom transport (for testing)
            base_url: OpenRouter API base URL
            app_url: HTTP-Referer header value
            app_name: X-Title header value
        """
        self.api_key = api_key
        self.model_text = model_text
        self.model_vision = model_vision
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.base_url = base_url.rstrip("/")
        self.app_url = app_url
        self.app_name = app_name

        if transport is not None:
            self.transport = transport
        else:
            self.transport = HttpxTransport()

        logger.info(
            "openrouter_client_initialized",
            extra={
                "model_text": model_text,
                "model_vision": model_vision,
                "timeout_s": timeout_s,
                "max_retries": max_retries,
            },
        )

    def _build_headers(self) -> dict[str, str]:
        """Build request headers with authentication."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.app_url:
            headers["HTTP-Referer"] = self.app_url
        if self.app_name:
            headers["X-Title"] = self.app_name
        return headers

    async def _request_with_retry(
        self,
        payload: dict[str, Any],
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Execute request with exponential backoff retry."""
        url = f"{self.base_url}/chat/completions"
        headers = self._build_headers()
        effective_timeout = timeout or self.timeout_s

        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                response = await self.transport.request(
                    method="POST",
                    url=url,
                    headers=headers,
                    json=payload,
                    timeout=effective_timeout,
                )
                return response

            except (OpenRouterRateLimitError, OpenRouterServerError, OpenRouterTimeoutError) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    # Calculate backoff
                    if isinstance(e, OpenRouterRateLimitError) and e.retry_after:
                        delay = min(e.retry_after, 60)
                    else:
                        delay = 2 ** attempt  # 1, 2, 4 seconds

                    logger.warning(
                        "openrouter_request_retry",
                        extra={
                            "attempt": attempt + 1,
                            "max_retries": self.max_retries,
                            "delay_s": delay,
                            "error": str(e),
                        },
                    )
                    await asyncio.sleep(delay)
                else:
                    raise

            except OpenRouterServiceError as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    # Fixed 30s delay for service errors
                    logger.warning(
                        "openrouter_service_error_retry",
                        extra={
                            "attempt": attempt + 1,
                            "delay_s": 30,
                            "error": str(e),
                        },
                    )
                    await asyncio.sleep(30)
                else:
                    raise

            except (OpenRouterAuthError, OpenRouterValidationError):
                # Non-retryable errors
                raise

        # Should not reach here, but just in case
        if last_error:
            raise last_error
        raise OpenRouterClientError("Max retries exceeded")

    async def generate_text(
        self,
        prompt: str,
        system_instructions: str | None = None,
        response_mime_type: str = "text/plain",
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """
        Generate text using OpenRouter API.

        Args:
            prompt: User prompt
            system_instructions: Optional system message
            response_mime_type: "text/plain" or "application/json"
            timeout: Request timeout override

        Returns:
            Raw API response with choices[0].message.content
        """
        messages = []

        if system_instructions:
            messages.append({
                "role": "system",
                "content": system_instructions,
            })

        messages.append({
            "role": "user",
            "content": prompt,
        })

        payload: dict[str, Any] = {
            "model": self.model_text,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 8192,
        }

        # Request JSON format if needed
        if response_mime_type == "application/json":
            payload["response_format"] = {"type": "json_object"}

        logger.debug(
            "openrouter_generate_text",
            extra={
                "model": self.model_text,
                "prompt_length": len(prompt),
                "has_system": system_instructions is not None,
            },
        )

        return await self._request_with_retry(payload, timeout)

    async def generate_from_image(
        self,
        prompt: str,
        image_data: bytes,
        mime_type: str = "image/png",
        response_mime_type: str = "application/json",
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """
        Generate text from image using OpenRouter API.

        Args:
            prompt: Description of what to extract
            image_data: Image bytes
            mime_type: Image MIME type (image/png, image/jpeg)
            response_mime_type: Response format
            timeout: Request timeout override

        Returns:
            Raw API response with choices[0].message.content
        """
        # Encode image to base64
        image_b64 = base64.standard_b64encode(image_data).decode("utf-8")
        data_url = f"data:{mime_type};base64,{image_b64}"

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ]

        payload: dict[str, Any] = {
            "model": self.model_vision,
            "messages": messages,
            "temperature": 0.1,  # Low temperature for consistent JSON output
            "max_tokens": 8192,
        }

        if response_mime_type == "application/json":
            payload["response_format"] = {"type": "json_object"}

        logger.debug(
            "openrouter_generate_from_image",
            extra={
                "model": self.model_vision,
                "prompt_length": len(prompt),
                "image_size": len(image_data),
                "mime_type": mime_type,
            },
        )

        return await self._request_with_retry(payload, timeout)

    async def create_embedding(
        self,
        input_text: str | list[str],
        model: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """
        Create embeddings for text using OpenRouter API.

        Args:
            input_text: Single string or list of strings to embed
            model: Embedding model (default: openai/text-embedding-3-large)
            timeout: Request timeout override

        Returns:
            Raw API response with format:
            {
                "data": [{"embedding": [...], "index": 0}],
                "model": "...",
                "usage": {"prompt_tokens": N, "total_tokens": N}
            }
        """
        effective_model = model or "openai/text-embedding-3-large"
        effective_timeout = timeout or self.timeout_s

        payload: dict[str, Any] = {
            "model": effective_model,
            "input": input_text,
        }

        url = f"{self.base_url}/embeddings"
        headers = self._build_headers()

        # Calculate input size for logging
        if isinstance(input_text, str):
            input_count = 1
            total_chars = len(input_text)
        else:
            input_count = len(input_text)
            total_chars = sum(len(t) for t in input_text)

        logger.debug(
            "openrouter_create_embedding",
            extra={
                "model": effective_model,
                "input_count": input_count,
                "total_chars": total_chars,
            },
        )

        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                response = await self.transport.request(
                    method="POST",
                    url=url,
                    headers=headers,
                    json=payload,
                    timeout=effective_timeout,
                )

                logger.debug(
                    "openrouter_embedding_success",
                    extra={
                        "model": effective_model,
                        "usage": response.get("usage"),
                    },
                )

                return response

            except (OpenRouterRateLimitError, OpenRouterServerError, OpenRouterTimeoutError) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    if isinstance(e, OpenRouterRateLimitError) and e.retry_after:
                        delay = min(e.retry_after, 60)
                    else:
                        delay = 2 ** attempt  # 1, 2, 4 seconds

                    logger.warning(
                        "openrouter_embedding_retry",
                        extra={
                            "attempt": attempt + 1,
                            "max_retries": self.max_retries,
                            "delay_s": delay,
                            "error": str(e),
                        },
                    )
                    await asyncio.sleep(delay)
                else:
                    raise

            except OpenRouterServiceError as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    logger.warning(
                        "openrouter_embedding_service_error_retry",
                        extra={
                            "attempt": attempt + 1,
                            "delay_s": 30,
                            "error": str(e),
                        },
                    )
                    await asyncio.sleep(30)
                else:
                    raise

            except (OpenRouterAuthError, OpenRouterValidationError):
                # Non-retryable errors
                raise

        if last_error:
            raise last_error
        raise OpenRouterClientError("Max retries exceeded for embedding request")

    async def close(self) -> None:
        """Close client resources."""
        await self.transport.close()
        logger.debug("openrouter_client_closed")

    def __repr__(self) -> str:
        return (
            f"OpenRouterClient(model_text={self.model_text!r}, "
            f"model_vision={self.model_vision!r}, timeout_s={self.timeout_s})"
        )
