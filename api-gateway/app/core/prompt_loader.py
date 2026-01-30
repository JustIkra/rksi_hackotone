"""
Utility for loading AI prompts from config files.

Provides centralized prompt management with:
- JSON file loading from config/prompts/
- Caching for performance
- Fallback support for missing files
- Type-safe access to prompt fields
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Search paths for prompts directory (in priority order)
# 1. Docker: /app/config/prompts (COPY config/ /app/config/)
# 2. Local: project_root/config/prompts (one level above api-gateway)
_PROMPTS_SEARCH_PATHS = [
    Path(__file__).parent.parent.parent / "config" / "prompts",  # /app/config/prompts in Docker
    Path(__file__).parent.parent.parent.parent / "config" / "prompts",  # ../config/prompts locally
]


def _find_prompts_dir() -> Path:
    """Find the prompts directory from search paths."""
    for path in _PROMPTS_SEARCH_PATHS:
        if path.exists():
            return path
    # Fallback to first path (will raise error on load if missing)
    return _PROMPTS_SEARCH_PATHS[0]


DEFAULT_PROMPTS_DIR = _find_prompts_dir()


class PromptNotFoundError(Exception):
    """Raised when a prompt file is not found and no fallback provided."""

    def __init__(self, prompt_name: str, path: Path):
        self.prompt_name = prompt_name
        self.path = path
        super().__init__(f"Prompt '{prompt_name}' not found at {path}")


class PromptLoader:
    """
    Loader for AI prompts from JSON config files.

    Usage:
        loader = PromptLoader()
        vision_config = loader.load("vision-extraction")
        prompt_text = loader.get_prompt_text("vision-extraction", "vision_prompt")
    """

    def __init__(self, prompts_dir: Path | None = None):
        """
        Initialize prompt loader.

        Args:
            prompts_dir: Directory containing prompt JSON files.
                        Defaults to config/prompts/ in project root.
        """
        self.prompts_dir = prompts_dir or DEFAULT_PROMPTS_DIR
        self._cache: dict[str, dict[str, Any]] = {}

    def load(
        self,
        prompt_name: str,
        fallback: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Load prompt configuration from JSON file.

        Args:
            prompt_name: Name of prompt file (without .json extension)
            fallback: Optional fallback data if file not found

        Returns:
            Parsed JSON content

        Raises:
            PromptNotFoundError: If file not found and no fallback
        """
        if prompt_name in self._cache:
            return self._cache[prompt_name]

        file_path = self.prompts_dir / f"{prompt_name}.json"

        if not file_path.exists():
            if fallback is not None:
                logger.warning(f"Prompt file not found: {file_path}, using fallback")
                return fallback
            raise PromptNotFoundError(prompt_name, file_path)

        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
            self._cache[prompt_name] = data
            logger.debug(f"Loaded prompt: {prompt_name} from {file_path}")
            return data
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in prompt file {file_path}: {e}")
            if fallback is not None:
                return fallback
            raise

    def get_prompt_text(
        self,
        prompt_name: str,
        key: str,
        fallback: str | None = None,
    ) -> str:
        """
        Get specific prompt text from config file.

        Args:
            prompt_name: Name of prompt file
            key: Key within the JSON to extract
            fallback: Fallback value if key not found

        Returns:
            Prompt text string
        """
        try:
            data = self.load(prompt_name)
            return data.get(key, fallback) if fallback else data[key]
        except (PromptNotFoundError, KeyError):
            if fallback is not None:
                return fallback
            raise

    def reload(self) -> None:
        """Clear cache to force reload on next access."""
        self._cache.clear()
        logger.info("Prompt cache cleared")


# Singleton instance for convenience
_default_loader: PromptLoader | None = None


def get_prompt_loader() -> PromptLoader:
    """Get default prompt loader instance."""
    global _default_loader
    if _default_loader is None:
        _default_loader = PromptLoader()
    return _default_loader
