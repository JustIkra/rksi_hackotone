"""
Service for loading and managing metric label-to-code mappings from YAML configuration.

Provides unified mapping from extracted metric labels (from documents) to internal MetricDef codes.
Uses a single header_map for all report types.
"""

import logging
import re
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


class MetricMappingService:
    """
    Service for managing metric label-to-code mappings.

    Loads YAML configuration and provides lookup methods for mapping
    extracted labels to metric codes. Uses a unified mapping for all report types.
    """

    def __init__(self, config_path: str | Path | None = None):
        """
        Initialize metric mapping service.

        Args:
            config_path: Path to YAML configuration file.
                        Defaults to config/app/metric-mapping.yaml
        """
        if config_path is None:
            # Default path relative to project root
            # Try multiple possible locations:
            # 1. In Docker: /app/app/services/metric_mapping.py -> /app/config/app/metric-mapping.yaml
            # 2. In local dev: api-gateway/app/services/metric_mapping.py -> ../config/app/metric-mapping.yaml
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config" / "app" / "metric-mapping.yaml"

            # If not found, try parent directory (for local dev where api-gateway is a subdirectory)
            if not config_path.exists() and project_root.name == "api-gateway":
                config_path = project_root.parent / "config" / "app" / "metric-mapping.yaml"
        else:
            config_path = Path(config_path)

        self.config_path = config_path
        self._mapping: dict[str, str] = {}
        self._loaded = False

    def load(self) -> None:
        """
        Load mappings from YAML configuration file.

        Raises:
            FileNotFoundError: If configuration file doesn't exist
            yaml.YAMLError: If YAML parsing fails
            ValueError: If configuration structure is invalid
        """
        if not self.config_path.exists():
            raise FileNotFoundError(f"Metric mapping config not found: {self.config_path}")

        logger.info(f"Loading metric mappings from {self.config_path}")

        with open(self.config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        if not isinstance(config, dict):
            raise ValueError(f"Invalid config structure: expected dict, got {type(config)}")

        if "header_map" not in config:
            raise ValueError("Missing 'header_map' key in config")

        header_map = config["header_map"]
        if not isinstance(header_map, dict):
            raise ValueError(
                f"Invalid header_map structure: expected dict, got {type(header_map)}"
            )

        # Store normalized mapping (uppercase keys)
        self._mapping = {
            label.upper().strip(): code.strip() for label, code in header_map.items()
        }

        self._loaded = True
        logger.info(f"Successfully loaded {len(self._mapping)} metric mappings")

    def _normalize_paired_label(self, label: str) -> str:
        """
        Normalize a paired metric label for matching.

        Handles:
        - Multiple consecutive spaces → single space
        - Whitespace around delimiters (–, -, /) → standardized format

        Args:
            label: Label to normalize (already uppercased and stripped)

        Returns:
            Normalized label
        """
        # Replace multiple spaces with single space
        normalized = re.sub(r'\s+', ' ', label)

        # Normalize whitespace around delimiters
        # "A  –  B" → "A–B", "A - B" → "A - B" (standardized single space)
        normalized = re.sub(r'\s*([–/])\s*', r'\1', normalized)  # Remove spaces around – and /
        normalized = re.sub(r'\s+-\s+', ' - ', normalized)  # Standardize hyphen spacing

        return normalized

    def get_metric_code(self, label: str) -> str | None:
        """
        Get metric code for a given label.

        Supports paired metrics with intelligent normalization:
        - Handles various delimiters (–, -, /)
        - Normalizes whitespace (multiple spaces → single space)
        - Tries reversed order for paired metrics

        Args:
            label: Metric label from document (will be normalized to uppercase)

        Returns:
            Metric code if found, None otherwise
        """
        if not self._loaded:
            self.load()

        # Basic normalization
        normalized_label = label.upper().strip()

        # Try direct lookup first
        result = self._mapping.get(normalized_label)
        if result:
            return result

        # Try with normalized whitespace
        normalized_whitespace = self._normalize_paired_label(normalized_label)
        result = self._mapping.get(normalized_whitespace)
        if result:
            return result

        # Try reversed order for paired metrics
        # Detect paired metrics by presence of delimiters
        for delimiter in ['–', ' - ', '-', '/', ' / ']:
            if delimiter in normalized_whitespace:
                parts = normalized_whitespace.split(delimiter, 1)
                if len(parts) == 2:
                    # Reverse the order
                    reversed_label = delimiter.join(reversed(parts))
                    result = self._mapping.get(reversed_label)
                    if result:
                        return result

        return None

    def get_mapping(self) -> dict[str, str]:
        """
        Get all mappings.

        Returns:
            Dictionary of label -> metric_code mappings
        """
        if not self._loaded:
            self.load()

        return self._mapping.copy()

    def get_all_mappings(self) -> dict[str, str]:
        """
        Get all mappings (alias for get_mapping for backwards compatibility).

        Returns:
            Dictionary of label -> metric_code mappings
        """
        return self.get_mapping()

    def reload(self) -> None:
        """Reload mappings from configuration file."""
        logger.info("Reloading metric mappings")
        self._loaded = False
        self._mapping = {}
        self.load()


# Global singleton instance
_mapping_service: MetricMappingService | None = None


def get_metric_mapping_service(config_path: str | Path | None = None) -> MetricMappingService:
    """
    Get global MetricMappingService instance.

    Args:
        config_path: Optional path to configuration file (only used on first call)

    Returns:
        MetricMappingService instance
    """
    global _mapping_service
    if _mapping_service is None:
        _mapping_service = MetricMappingService(config_path)
        _mapping_service.load()
    return _mapping_service


def reset_metric_mapping_service() -> None:
    """
    Reset global MetricMappingService instance.

    Useful for testing or reloading configuration.
    """
    global _mapping_service
    _mapping_service = None
