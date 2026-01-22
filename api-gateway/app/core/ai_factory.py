"""
Factory for creating OpenRouter AI API clients.

Provides dependency injection for FastAPI routes and Celery tasks.
"""

from __future__ import annotations

import logging
from typing import Union

from app.clients import OpenRouterClient, OpenRouterPoolClient
from app.core.config import settings

logger = logging.getLogger(__name__)

# Type alias for AI client
AIClient = Union[OpenRouterClient, OpenRouterPoolClient]


def create_ai_client(api_key: str | None = None) -> AIClient:
    """
    Create OpenRouter client configured from application settings.

    Args:
        api_key: Optional API key override. If provided, uses single client.

    Returns:
        Configured OpenRouterClient or OpenRouterPoolClient instance
    """
    if not settings.openrouter_keys_list:
        raise ValueError(
            "No OpenRouter API keys configured. "
            "Set OPENROUTER_API_KEYS in .env"
        )

    # If specific key provided, use single client
    if api_key is not None:
        client = OpenRouterClient(
            api_key=api_key,
            model_text=settings.openrouter_model_text,
            model_vision=settings.openrouter_model_vision,
            timeout_s=settings.openrouter_timeout_s,
            max_retries=3,
            base_url=settings.openrouter_base_url,
            app_url=settings.openrouter_app_url,
            app_name=settings.openrouter_app_name,
        )

        logger.debug(
            "openrouter_single_client_created",
            extra={
                "model_text": settings.openrouter_model_text,
                "model_vision": settings.openrouter_model_vision,
            },
        )

        return client

    # Multiple keys: use pool client
    if len(settings.openrouter_keys_list) > 1:
        client = OpenRouterPoolClient(
            api_keys=settings.openrouter_keys_list,
            model_text=settings.openrouter_model_text,
            model_vision=settings.openrouter_model_vision,
            timeout_s=settings.openrouter_timeout_s,
            max_retries=3,
            base_url=settings.openrouter_base_url,
            app_url=settings.openrouter_app_url,
            app_name=settings.openrouter_app_name,
            qps_per_key=settings.openrouter_qps_per_key,
            burst_multiplier=settings.openrouter_burst_multiplier,
            strategy=settings.openrouter_strategy,
        )

        logger.info(
            "openrouter_pool_client_created",
            extra={
                "total_keys": len(settings.openrouter_keys_list),
                "qps_per_key": settings.openrouter_qps_per_key,
                "strategy": settings.openrouter_strategy,
                "model_text": settings.openrouter_model_text,
            },
        )

        return client

    # Single key: use simple client
    client = OpenRouterClient(
        api_key=settings.openrouter_keys_list[0],
        model_text=settings.openrouter_model_text,
        model_vision=settings.openrouter_model_vision,
        timeout_s=settings.openrouter_timeout_s,
        max_retries=3,
        base_url=settings.openrouter_base_url,
        app_url=settings.openrouter_app_url,
        app_name=settings.openrouter_app_name,
    )

    logger.debug(
        "openrouter_single_client_created",
        extra={
            "model_text": settings.openrouter_model_text,
            "model_vision": settings.openrouter_model_vision,
        },
    )

    return client


async def get_ai_client() -> AIClient:
    """
    FastAPI dependency for injecting AI client.

    Example:
        ```python
        @router.post("/analyze")
        async def analyze(client = Depends(get_ai_client)):
            response = await client.generate_text("Analyze this...")
            return response
        ```

    Returns:
        Configured AI client instance
    """
    return create_ai_client()


def extract_text_from_response(response: dict) -> str:
    """
    Extract text content from OpenRouter API response.

    Args:
        response: Raw API response

    Returns:
        Extracted text content
    """
    # OpenRouter format: choices[0].message.content
    if "choices" in response:
        return response["choices"][0]["message"]["content"]

    raise ValueError(f"Unknown response format: {list(response.keys())}")
