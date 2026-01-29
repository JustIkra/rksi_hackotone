"""
OpenRouter Pool Client with multi-key rotation, rate limiting, and circuit breakers.

Wraps multiple OpenRouterClient instances for load balancing and fault tolerance.
Uses the same interface as GeminiPoolClient for drop-in compatibility.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Literal

from app.clients.circuit_breaker import CircuitBreaker, CircuitState
from app.clients.exceptions import (
    OpenRouterAuthError,
    OpenRouterClientError,
    OpenRouterRateLimitError,
    OpenRouterServerError,
    OpenRouterServiceError,
    OpenRouterTimeoutError,
    OpenRouterValidationError,
)
from app.clients.openrouter import HttpxTransport, OpenRouterClient, OpenRouterTransport
from app.clients.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class OpenRouterPoolClient:
    """
    Pool client managing multiple OpenRouter API keys with rotation.

    Features:
    - Multi-key management with automatic rotation
    - Per-key rate limiting
    - Per-key circuit breaker
    - Selection strategies: ROUND_ROBIN or LEAST_BUSY
    """

    def __init__(
        self,
        api_keys: list[str],
        model_text: str = "google/gemini-2.0-flash-001",
        model_vision: str = "google/gemini-2.0-flash-001",
        timeout_s: int = 30,
        max_retries: int = 3,
        transport: OpenRouterTransport | None = None,
        base_url: str = "https://openrouter.ai/api/v1",
        app_url: str = "",
        app_name: str = "Workers Proficiency Assessment",
        qps_per_key: float = 0.15,
        burst_multiplier: float = 8.1,
        strategy: Literal["ROUND_ROBIN", "LEAST_BUSY"] = "ROUND_ROBIN",
        circuit_breaker_failure_threshold: int = 5,
        circuit_breaker_recovery_timeout: float = 60.0,
    ):
        """
        Initialize OpenRouter pool client.

        Args:
            api_keys: List of OpenRouter API keys
            model_text: Model for text generation
            model_vision: Model for vision tasks
            timeout_s: Request timeout in seconds
            max_retries: Maximum retry attempts per key
            transport: Custom transport (for testing)
            base_url: OpenRouter API base URL
            app_url: HTTP-Referer header value
            app_name: X-Title header value
            qps_per_key: Queries per second limit per key
            burst_multiplier: Burst size multiplier
            strategy: Key selection strategy
            circuit_breaker_failure_threshold: Failures before circuit opens
            circuit_breaker_recovery_timeout: Recovery timeout in seconds
        """
        if not api_keys:
            raise ValueError("At least one API key is required")

        self.api_keys = api_keys
        self.model_text = model_text
        self.model_vision = model_vision
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.base_url = base_url
        self.app_url = app_url
        self.app_name = app_name
        self.qps_per_key = qps_per_key
        self.burst_multiplier = burst_multiplier
        self.strategy = strategy

        # Create shared transport for all clients
        self._shared_transport = transport or HttpxTransport()

        # Create clients for each key
        self._clients: dict[str, OpenRouterClient] = {}
        for key in api_keys:
            self._clients[key] = OpenRouterClient(
                api_key=key,
                model_text=model_text,
                model_vision=model_vision,
                timeout_s=timeout_s,
                max_retries=1,  # Pool handles retries across keys
                transport=self._shared_transport,
                base_url=base_url,
                app_url=app_url,
                app_name=app_name,
            )

        # Per-key rate limiters
        burst_size = max(1, int(qps_per_key * burst_multiplier))
        self._rate_limiters: dict[str, RateLimiter] = {
            key: RateLimiter(qps=qps_per_key, burst_size=burst_size)
            for key in api_keys
        }

        # Per-key circuit breakers
        self._circuit_breakers: dict[str, CircuitBreaker] = {
            key: CircuitBreaker(
                failure_threshold=circuit_breaker_failure_threshold,
                recovery_timeout=circuit_breaker_recovery_timeout,
            )
            for key in api_keys
        }

        # Key statistics for monitoring
        self._key_stats: dict[str, dict] = {
            key: {"successes": 0, "failures": 0, "total_latency": 0.0}
            for key in api_keys
        }

        # Lock for thread-safe key selection
        self._lock = asyncio.Lock()

        # Round-robin index for key selection
        self._round_robin_index = 0

        logger.info(
            "openrouter_pool_initialized",
            extra={
                "num_keys": len(api_keys),
                "model_text": model_text,
                "model_vision": model_vision,
                "strategy": strategy,
                "qps_per_key": qps_per_key,
            },
        )

    def _get_next_key_round_robin(self) -> str:
        """Get next key using round-robin strategy."""
        key = self.api_keys[self._round_robin_index]
        self._round_robin_index = (self._round_robin_index + 1) % len(self.api_keys)
        return key

    def _get_next_key_least_busy(self) -> str:
        """Get key with most available rate limit tokens."""
        best_key = self.api_keys[0]
        best_tokens = -1.0

        for key in self.api_keys:
            # Skip keys with open circuit
            if self._circuit_breakers[key].state == CircuitState.OPEN:
                continue

            tokens = self._rate_limiters[key].available_tokens
            if tokens > best_tokens:
                best_tokens = tokens
                best_key = key

        return best_key

    async def _select_key(self) -> str | None:
        """Select next available key based on strategy."""
        async with self._lock:
            for _ in range(len(self.api_keys)):
                if self.strategy == "LEAST_BUSY":
                    key = self._get_next_key_least_busy()
                else:
                    key = self._get_next_key_round_robin()

                # Check circuit breaker
                cb = self._circuit_breakers[key]
                if cb.state == CircuitState.OPEN:
                    continue

                # Check rate limiter
                rl = self._rate_limiters[key]
                if not rl.try_acquire():
                    continue

                return key

            # No key available, wait for rate limiter
            if self.strategy == "LEAST_BUSY":
                key = self._get_next_key_least_busy()
            else:
                key = self._get_next_key_round_robin()
            await self._rate_limiters[key].acquire()
            return key

    def _record_key_success(self, key: str, latency: float) -> None:
        """Record successful request for a key."""
        stats = self._key_stats[key]
        stats["successes"] += 1
        stats["total_latency"] += latency

    def _record_key_failure(self, key: str, status_code: int) -> None:
        """Record failed request for a key."""
        stats = self._key_stats[key]
        stats["failures"] += 1
        stats["last_error_code"] = status_code

    def _get_key_stats(self, key: str) -> dict[str, Any]:
        """Get statistics for a specific key."""
        stats = self._key_stats[key]
        successes = stats["successes"]
        return {
            "successes": successes,
            "failures": stats["failures"],
            "avg_latency": stats["total_latency"] / successes if successes > 0 else 0.0,
        }

    async def _execute_with_pool(
        self,
        method: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute method with pool rotation and error handling."""
        start_time = time.monotonic()
        attempts = 0
        max_attempts = len(self.api_keys) * self.max_retries

        last_error: Exception | None = None

        while attempts < max_attempts:
            attempts += 1

            key = await self._select_key()
            if key is None:
                await asyncio.sleep(1)
                continue

            client = self._clients[key]
            cb = self._circuit_breakers[key]

            try:
                # Execute request
                if method == "generate_text":
                    result = await client.generate_text(**kwargs)
                elif method == "generate_from_image":
                    result = await client.generate_from_image(**kwargs)
                elif method == "generate_from_pdf":
                    result = await client.generate_from_pdf(**kwargs)
                else:
                    raise ValueError(f"Unknown method: {method}")

                # Record success
                cb.record_success()
                self._record_key_success(key, time.monotonic() - start_time)

                return result

            except OpenRouterRateLimitError as e:
                last_error = e
                cb.record_failure()
                cb.record_failure()
                cb.record_failure()  # Fast-track circuit opening
                self._record_key_failure(key, 429)

                logger.warning(
                    "openrouter_pool_rate_limit",
                    extra={"key_suffix": key[-8:], "retry_after": e.retry_after},
                )

                if e.retry_after:
                    await asyncio.sleep(min(e.retry_after, 30))

            except OpenRouterServiceError as e:
                last_error = e
                # Don't affect circuit breaker for service errors
                self._record_key_failure(key, e.status_code or 503)

                logger.warning(
                    "openrouter_pool_service_error",
                    extra={"error": str(e)},
                )
                await asyncio.sleep(30)

            except (OpenRouterServerError, OpenRouterTimeoutError) as e:
                last_error = e
                cb.record_failure()
                self._record_key_failure(key, getattr(e, "status_code", 500))

                logger.warning(
                    "openrouter_pool_transient_error",
                    extra={"key_suffix": key[-8:], "error": str(e)},
                )

            except (OpenRouterAuthError, OpenRouterValidationError) as e:
                # Non-retryable errors
                self._record_key_failure(key, getattr(e, "status_code", 400))
                raise

        # All retries exhausted
        if last_error:
            raise last_error
        raise OpenRouterClientError("All keys exhausted")

    async def generate_text(
        self,
        prompt: str,
        system_instructions: str | None = None,
        response_mime_type: str = "text/plain",
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Generate text using pool rotation."""
        return await self._execute_with_pool(
            "generate_text",
            prompt=prompt,
            system_instructions=system_instructions,
            response_mime_type=response_mime_type,
            timeout=timeout,
        )

    async def generate_from_image(
        self,
        prompt: str,
        image_data: bytes,
        mime_type: str = "image/png",
        response_mime_type: str = "application/json",
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Generate text from image using pool rotation."""
        return await self._execute_with_pool(
            "generate_from_image",
            prompt=prompt,
            image_data=image_data,
            mime_type=mime_type,
            response_mime_type=response_mime_type,
            timeout=timeout,
        )

    async def generate_from_pdf(
        self,
        prompt: str,
        pdf_data: bytes,
        system_instructions: str | None = None,
        response_mime_type: str = "text/plain",
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Generate text from PDF using pool rotation."""
        return await self._execute_with_pool(
            "generate_from_pdf",
            prompt=prompt,
            pdf_data=pdf_data,
            system_instructions=system_instructions,
            response_mime_type=response_mime_type,
            timeout=timeout,
        )

    def get_pool_stats(self) -> dict[str, Any]:
        """Get pool statistics for monitoring."""
        return {
            "num_keys": len(self.api_keys),
            "strategy": self.strategy,
            "keys": {
                key[-8:]: {
                    "circuit_state": self._circuit_breakers[key].state.value,
                    "rate_limiter_tokens": self._rate_limiters[key].available_tokens,
                    **self._get_key_stats(key),
                }
                for key in self.api_keys
            },
        }

    async def close(self) -> None:
        """Close all clients and shared transport."""
        await self._shared_transport.close()
        logger.debug("openrouter_pool_closed")

    def __repr__(self) -> str:
        return (
            f"OpenRouterPoolClient(num_keys={len(self.api_keys)}, "
            f"model_text={self.model_text!r}, strategy={self.strategy!r})"
        )
