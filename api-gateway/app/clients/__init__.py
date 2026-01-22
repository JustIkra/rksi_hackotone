"""
External API clients for third-party services.

This package contains clients for external APIs (OpenRouter) with
proper error handling, retry logic, and mocking support for tests.
"""

from app.clients.circuit_breaker import CircuitBreaker, CircuitState
from app.clients.exceptions import (
    # OpenRouter Exceptions
    OpenRouterAuthError,
    OpenRouterClientError,
    OpenRouterRateLimitError,
    OpenRouterServerError,
    OpenRouterServiceError,
    OpenRouterTimeoutError,
    OpenRouterValidationError,
)
from app.clients.key_pool import KeyMetrics, KeyPool, KeyPoolStats, KeySelectionStrategy
from app.clients.openrouter import HttpxTransport as OpenRouterHttpxTransport
from app.clients.openrouter import OpenRouterClient, OpenRouterTransport
from app.clients.openrouter_pool import OpenRouterPoolClient
from app.clients.rate_limiter import RateLimiter, TokenBucket

__all__ = [
    # OpenRouter Client
    "OpenRouterClient",
    "OpenRouterTransport",
    "OpenRouterHttpxTransport",
    "OpenRouterPoolClient",
    # Key Pool
    "KeyPool",
    "KeyPoolStats",
    "KeyMetrics",
    "KeySelectionStrategy",
    # Rate Limiter
    "RateLimiter",
    "TokenBucket",
    # Circuit Breaker
    "CircuitBreaker",
    "CircuitState",
    # OpenRouter Exceptions
    "OpenRouterClientError",
    "OpenRouterRateLimitError",
    "OpenRouterServerError",
    "OpenRouterServiceError",
    "OpenRouterTimeoutError",
    "OpenRouterValidationError",
    "OpenRouterAuthError",
]
