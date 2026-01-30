"""
Application configuration using Pydantic Settings.

Loads from ROOT .env file (one level up from api-gateway/).
Supports multiple profiles: dev, test, ci, prod.
"""

import logging
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Find project root (one level up from api-gateway/)
API_GATEWAY_DIR = Path(__file__).parent.parent.parent
PROJECT_ROOT = API_GATEWAY_DIR.parent
ENV_FILE = PROJECT_ROOT / ".env"

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """
    Application settings loaded from root .env file.

    All environment variables are loaded from PROJECT_ROOT/.env
    to ensure single source of truth for configuration.
    """

    # Application Settings
    app_port: int = Field(default=9187, description="Application HTTP port")
    uvicorn_proxy_headers: bool = Field(default=True, description="Trust X-Forwarded-* headers")
    forwarded_allow_ips: str = Field(default="*", description="Allowed proxy IPs")
    app_root_path: str = Field(default="", description="Root path for reverse proxy")

    # Environment Profile
    env: Literal["dev", "test", "ci", "prod"] = Field(
        default="dev", description="Environment profile"
    )
    deterministic: bool = Field(
        default=False, description="Deterministic mode for testing (freezes time, seeds, etc.)"
    )

    # Testing & Celery Configuration
    celery_task_always_eager: bool = Field(
        default=False, description="Run Celery tasks synchronously (test/ci mode)"
    )
    celery_eager_propagates_exceptions: bool = Field(
        default=False, description="Propagate exceptions in eager mode (test/ci mode)"
    )
    deterministic_seed: int = Field(
        default=42, description="Seed for random number generators in deterministic mode"
    )
    frozen_time: str | None = Field(
        default=None, description="Fixed timestamp for testing (ISO format: 2025-01-01T00:00:00Z)"
    )

    # Security
    jwt_secret: str = Field(..., description="JWT signing secret (MUST change in production)")
    jwt_alg: str = Field(default="HS256", description="JWT algorithm")
    access_token_ttl_min: int = Field(default=30, description="Access token TTL in minutes")

    # Database
    postgres_dsn: str = Field(..., description="PostgreSQL connection string (async)")

    # Cache & Queue
    redis_url: str = Field(default="redis://redis:6379/0", description="Redis URL")
    rabbitmq_url: str = Field(
        default="amqp://guest:guest@rabbitmq:5672//", description="RabbitMQ broker URL"
    )

    # File Storage
    file_storage: Literal["LOCAL", "MINIO"] = Field(default="LOCAL", description="Storage backend")
    file_storage_base: str = Field(
        default="/app/storage", description="Base path for LOCAL storage"
    )
    report_max_size_mb: int = Field(
        default=15, ge=1, description="Maximum allowed .docx report size in megabytes"
    )

    # CORS
    cors_allow_all: bool = Field(
        default=False, description="Allow all CORS origins (disable when behind NPM)"
    )
    allowed_origins: str = Field(default="", description="Comma-separated list of allowed origins")

    # Logging
    log_level: str = Field(default="INFO", description="Log level")
    log_mask_secrets: bool = Field(default=True, description="Mask secrets in logs")

    # OpenRouter Configuration (AI Provider)
    openrouter_api_keys: str = Field(
        default="", description="Comma-separated OpenRouter API keys for rotation"
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", description="OpenRouter API base URL"
    )
    openrouter_app_url: str = Field(
        default="", description="HTTP-Referer header for OpenRouter"
    )
    openrouter_app_name: str = Field(
        default="Workers Proficiency Assessment", description="X-Title header for OpenRouter"
    )
    openrouter_model_text: str = Field(
        default="google/gemini-2.0-flash-001", description="OpenRouter model for text generation"
    )
    openrouter_model_vision: str = Field(
        default="google/gemini-2.0-flash-001", description="OpenRouter model for vision tasks"
    )
    openrouter_qps_per_key: float = Field(
        default=0.15, description="QPS limit per API key"
    )
    openrouter_burst_multiplier: float = Field(
        default=8.1, description="Burst size multiplier for rate limiting"
    )
    openrouter_timeout_s: int = Field(
        default=30, description="OpenRouter API timeout in seconds"
    )
    openrouter_strategy: Literal["ROUND_ROBIN", "LEAST_BUSY"] = Field(
        default="ROUND_ROBIN", description="Key rotation strategy"
    )

    # AI Features
    ai_vision_enabled: bool = Field(
        default=True, description="Enable AI Vision processing pipeline"
    )

    # Metric Generation Feature
    enable_metric_generation: bool = Field(
        default=False, description="Enable AI metric generation from PDF/DOCX reports"
    )
    openrouter_metric_model: str = Field(
        default="google/gemini-2.0-flash-001",
        description="OpenRouter model for metric generation (vision-capable)",
    )

    # Embedding / Semantic Search Settings
    embedding_model: str = Field(
        default="openai/text-embedding-3-small",
        description="Model for generating metric embeddings via OpenRouter",
    )
    embedding_dimensions: int = Field(
        default=1536,
        description="Embedding vector dimensions (must match model output)",
    )
    embedding_similarity_threshold: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score for considering a match",
    )
    embedding_top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of similar metrics to retrieve for matching",
    )

    # Report RAG Settings
    report_rag_top_k: int = Field(
        default=5,
        ge=1,
        description="Default number of similar reports to retrieve for RAG context",
    )
    report_rag_max_top_k: int = Field(
        default=50,
        ge=1,
        description="Maximum allowed top_k value for report RAG queries",
    )
    report_rag_similarity_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score for report RAG matches",
    )
    report_rag_ambiguity_delta: float = Field(
        default=0.02,
        ge=0.0,
        le=1.0,
        description="Delta threshold for detecting ambiguous matches in RAG",
    )

    # Metric Mapping Decision Settings
    metric_mapping_top_k: int = Field(
        default=10,
        ge=1,
        description="Number of candidates to retrieve for metric mapping",
    )
    metric_mapping_llm_min_confidence: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Minimum confidence for LLM match in metric mapping",
    )

    # Metric Deduplication Settings
    metric_dedup_threshold: float = Field(
        default=0.92,
        ge=0.0,
        le=1.0,
        description="Semantic similarity threshold for pre-extraction deduplication",
    )
    rag_candidate_min_threshold: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Minimum similarity threshold for RAG candidates (lowered to catch more potential matches)",
    )
    rag_auto_match_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Auto-match threshold (skip LLM if similarity above this)",
    )

    # Computed Properties
    def _parse_comma_separated(self, value: str) -> list[str]:
        """Helper to parse comma-separated strings."""
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    @property
    def is_dev(self) -> bool:
        """Check if running in dev environment."""
        return self.env == "dev"

    @property
    def is_test(self) -> bool:
        """Check if running in test environment."""
        return self.env == "test"

    @property
    def is_prod(self) -> bool:
        """Check if running in production environment."""
        return self.env == "prod"

    @property
    def is_ci(self) -> bool:
        """Check if running in CI environment."""
        return self.env == "ci"

    @property
    def cors_origins(self) -> list[str]:
        """Get parsed CORS origins."""
        if self.cors_allow_all:
            return ["*"]
        return self._parse_comma_separated(self.allowed_origins)

    @property
    def openrouter_keys_list(self) -> list[str]:
        """Get parsed OpenRouter API keys as list."""
        return self._parse_comma_separated(self.openrouter_api_keys)

    @property
    def report_max_size_bytes(self) -> int:
        """Maximum allowed report size in bytes."""
        return self.report_max_size_mb * 1024 * 1024

    # Normalize empty strings to None for optional fields sourced from .env
    @field_validator("frozen_time", mode="before")
    @classmethod
    def _frozen_time_empty_is_none(cls, v: str | None) -> str | None:
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    # Profile Auto-Configuration
    @model_validator(mode="after")
    def apply_profile_defaults(self) -> "Settings":
        """
        Apply profile-specific defaults for test/ci environments.

        In test/ci profiles:
        - Enable deterministic mode (frozen time, seeds)
        - Run Celery tasks synchronously (eager mode)
        - Propagate exceptions in eager mode
        """
        if self.env in ("test", "ci"):
            # Enable deterministic mode
            if not self.deterministic:
                self.deterministic = True

            # Configure Celery for synchronous testing
            if not self.celery_task_always_eager:
                self.celery_task_always_eager = True

            if not self.celery_eager_propagates_exceptions:
                self.celery_eager_propagates_exceptions = True

            # Set default frozen time for tests if not set
            if not self.frozen_time:
                self.frozen_time = "2025-01-15T12:00:00Z"

        return self

    # Pydantic Settings Configuration
    model_config = SettingsConfigDict(
        # Load from ROOT .env file
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        # Case-insensitive environment variables
        case_sensitive=False,
        # Allow extra fields (for forward compatibility)
        extra="ignore",
        # Validate default values
        validate_default=True,
    )


# Global Settings Instance
def get_settings() -> Settings:
    """
    Get application settings (cached).

    Loads from PROJECT_ROOT/.env file.
    Use this function to access settings throughout the application.
    """
    return Settings()


# Create cached instance
settings = get_settings()


# Configuration Validation
def validate_config() -> None:
    """
    Validate critical configuration on startup.

    Raises:
        ValueError: If configuration is invalid
    """
    # Check JWT secret in production
    if settings.is_prod and settings.jwt_secret == "change_me":
        raise ValueError(
            "JWT_SECRET must be changed in production! "
            "Generate a strong secret: openssl rand -hex 32"
        )

    # Check database connection
    if not settings.postgres_dsn:
        raise ValueError("POSTGRES_DSN is required")

    # Check OpenRouter API keys if AI is enabled
    if settings.ai_vision_enabled:
        if not settings.openrouter_keys_list:
            raise ValueError(
                "OPENROUTER_API_KEYS required for AI features. "
                "Get keys at https://openrouter.ai/keys"
            )

    logger.info(
        "configuration_validated",
        extra={
            "event": "configuration_validated",
            "env_profile": settings.env,
            "config_path": str(ENV_FILE),
            "app_port": settings.app_port,
        },
    )

    # Show testing mode flags
    if settings.deterministic:
        logger.info("deterministic_mode_enabled")
    if settings.celery_task_always_eager:
        logger.info("celery_eager_mode_enabled")
    if settings.frozen_time:
        logger.info(
            "frozen_time_active",
            extra={"frozen_time": settings.frozen_time},
        )
