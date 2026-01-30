"""
Prompt accessors for metric mapping decision.
"""

from functools import lru_cache

from app.core.prompt_loader import get_prompt_loader


@lru_cache(maxsize=1)
def get_metric_mapping_decision_system() -> str:
    """Get system prompt for metric mapping decision."""
    return get_prompt_loader().get_prompt_text("metric-mapping-decision", "decision_system")


@lru_cache(maxsize=1)
def get_metric_mapping_decision_user_prefix() -> str:
    """Get user prompt prefix for metric mapping decision."""
    return get_prompt_loader().get_prompt_text("metric-mapping-decision", "decision_user_prefix")
