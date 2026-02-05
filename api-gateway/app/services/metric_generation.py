"""
Service for AI-powered metric generation from PDF/DOCX reports.

Handles:
- PDF/DOCX file processing (DOCX converted to PDF via LibreOffice)
- AI extraction using OpenRouter PDF Inputs API
- Multi-pass generation (extraction + review)
- Deduplication and matching with existing metrics
- Progress tracking via Redis
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any

from redis import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.openrouter import OpenRouterClient
from app.core.config import settings
from app.db.models import MetricCategory, MetricDef, MetricSynonym
from app.schemas.metric_generation import (
    AIRationale,
    AIReviewResult,
    ExtractedMetricData,
    TaskStatus,
)
from app.services.embedding import EmbeddingService

logger = logging.getLogger(__name__)

# Path candidates for Docker and local environments
# In Docker: /app/app/services/metric_generation.py -> /app/config/prompts/...
# Locally: .../api-gateway/app/services/metric_generation.py -> .../config/prompts/...
_PROMPTS_CANDIDATES = [
    Path(__file__).parent.parent.parent / "config" / "prompts" / "metric-extraction.json",  # Docker: /app/config/...
    Path(__file__).parent.parent.parent.parent / "config" / "prompts" / "metric-extraction.json",  # Local: ../config/...
]
PROMPTS_PATH = next((p for p in _PROMPTS_CANDIDATES if p.exists()), _PROMPTS_CANDIDATES[0])
MAX_PDF_SIZE = 10 * 1024 * 1024  # 10MB limit for OpenRouter PDF inputs


class MetricGenerationService:
    """Service for generating metrics from PDF/DOCX documents using AI."""

    def __init__(
        self,
        db: AsyncSession,
        redis: Redis | None = None,
        openrouter_client: OpenRouterClient | None = None,
        embedding_service: EmbeddingService | None = None,
    ):
        self.db = db
        self.redis = redis
        self._prompts: dict[str, Any] | None = None

        # Initialize OpenRouter client with metric generation model
        if openrouter_client:
            self._client = openrouter_client
        else:
            api_keys = settings.openrouter_keys_list
            if not api_keys:
                raise ValueError("OPENROUTER_API_KEYS required for metric generation")

            self._client = OpenRouterClient(
                api_key=api_keys[0],
                model_vision=settings.openrouter_metric_model,
                model_text=settings.openrouter_metric_model,
                timeout_s=120,  # Longer timeout for vision processing
            )

        # Initialize embedding service for semantic matching
        self.embedding_service = embedding_service or EmbeddingService(db, self._client)

    @property
    def prompts(self) -> dict[str, Any]:
        """Load prompts from config file (cached)."""
        if self._prompts is None:
            if PROMPTS_PATH.exists():
                with open(PROMPTS_PATH, encoding="utf-8") as f:
                    self._prompts = json.load(f)
            else:
                logger.warning(f"Prompts file not found: {PROMPTS_PATH}")
                self._prompts = {
                    "system_prompt": "Extract metrics from the document.",
                    "extraction_prompt": "Extract metrics as JSON.",
                    "review_prompt": "Review and deduplicate metrics.",
                }
        return self._prompts

    # ==================== Progress Tracking ====================

    def _get_task_key(self, task_id: str) -> str:
        """Get Redis key for task progress."""
        return f"metric_gen:{task_id}"

    async def update_progress(
        self,
        task_id: str,
        status: TaskStatus,
        progress: int = 0,
        current_step: str | None = None,
        **extra: Any,
    ) -> None:
        """Update task progress in Redis."""
        if not self.redis:
            return

        data = {
            "status": status.value,
            "progress": progress,
            "current_step": current_step,
            **extra,
        }
        self.redis.setex(
            self._get_task_key(task_id),
            3600,  # 1 hour TTL
            json.dumps(data),
        )

    async def get_progress(self, task_id: str) -> dict[str, Any]:
        """Get task progress from Redis."""
        if not self.redis:
            return {"status": TaskStatus.PENDING.value, "progress": 0}

        data = self.redis.get(self._get_task_key(task_id))
        if data:
            return json.loads(data)
        return {"status": TaskStatus.PENDING.value, "progress": 0}

    # ==================== File Processing ====================

    def compute_file_hash(self, file_data: bytes) -> str:
        """Compute SHA-256 hash of file for deduplication."""
        return hashlib.sha256(file_data).hexdigest()

    def convert_docx_to_pdf(self, docx_data: bytes) -> bytes:
        """Convert DOCX document to PDF.

        Args:
            docx_data: DOCX file content bytes

        Returns:
            PDF file content bytes

        Raises:
            RuntimeError: If LibreOffice is not installed or conversion fails
        """
        from app.services.docx_to_pdf import convert_docx_bytes_to_pdf_bytes
        return convert_docx_bytes_to_pdf_bytes(docx_data)

    # ==================== Context Loading ====================

    async def get_existing_metrics(self) -> list[dict[str, Any]]:
        """Get all existing metric definitions for context."""
        result = await self.db.execute(
            select(MetricDef).where(MetricDef.moderation_status == "APPROVED")
        )
        metrics = result.scalars().all()

        return [
            {
                "code": m.code,
                "name": m.name,
                "name_ru": m.name_ru,
                "description": m.description,
            }
            for m in metrics
        ]

    async def get_existing_synonyms(self) -> list[dict[str, str]]:
        """Get all existing synonyms for matching."""
        result = await self.db.execute(
            select(MetricSynonym, MetricDef)
            .join(MetricDef)
            .where(MetricDef.moderation_status == "APPROVED")
        )
        rows = result.all()

        return [
            {"synonym": row[0].synonym, "metric_code": row[1].code}
            for row in rows
        ]

    async def get_existing_categories(self) -> list[dict[str, str]]:
        """Get all existing categories."""
        result = await self.db.execute(select(MetricCategory))
        categories = result.scalars().all()

        return [
            {"code": c.code, "name": c.name}
            for c in categories
        ]

    # ==================== Validation ====================

    def _is_valid_metric_value(self, value: Any) -> bool:
        """
        Check if metric has a valid numeric value (1-10).

        Metrics without numeric values are likely recommendations
        or textual observations, not actual scored metrics.
        """
        if value is None:
            return False
        try:
            num = float(value)
            return 1.0 <= num <= 10.0
        except (ValueError, TypeError):
            return False

    def _filter_metrics_with_values(
        self,
        metrics: list[ExtractedMetricData],
        source: str = "extraction",
    ) -> list[ExtractedMetricData]:
        """
        Filter metrics to keep only those with valid numeric values.

        This prevents recommendations and textual observations from
        being saved as metrics. Logs filtered items for debugging.

        Args:
            metrics: List of extracted metrics
            source: Source identifier for logging (extraction/review)

        Returns:
            Filtered list containing only metrics with valid values
        """
        valid_metrics = []
        filtered_count = 0

        for m in metrics:
            if self._is_valid_metric_value(m.value):
                valid_metrics.append(m)
            else:
                filtered_count += 1
                logger.info(
                    f"Filtered metric without value ({source}): '{m.name}' "
                    f"(value={m.value}) - likely a recommendation, not a metric"
                )

        if filtered_count > 0:
            logger.info(
                f"Filtered {filtered_count} metrics without numeric values "
                f"from {source} pass (kept {len(valid_metrics)})"
            )

        return valid_metrics

    # ==================== AI Extraction ====================

    def _build_extraction_prompt(
        self,
        existing_metrics: list[dict[str, Any]],
        existing_synonyms: list[dict[str, str]],
        existing_categories: list[dict[str, str]],
    ) -> str:
        """Build prompt for metric extraction."""
        template = self.prompts.get("extraction_prompt", "Extract metrics as JSON.")

        metrics_str = "\n".join(
            f"- {m['name']} ({m['code']}): {m.get('description', '')}"
            for m in existing_metrics[:50]  # Limit to avoid token overflow
        )

        synonyms_str = "\n".join(
            f"- {s['synonym']} → {s['metric_code']}"
            for s in existing_synonyms[:100]
        )

        categories_str = "\n".join(
            f"- {c['name']} ({c['code']})"
            for c in existing_categories
        )

        # Use replace() instead of format() to avoid conflicts with JSON {} in prompt
        return (
            template
            .replace("{existing_metrics}", metrics_str or "Нет существующих метрик")
            .replace("{existing_synonyms}", synonyms_str or "Нет синонимов")
            .replace("{existing_categories}", categories_str or "Нет категорий")
        )

    def _build_review_prompt(
        self,
        extracted_metrics: list[ExtractedMetricData],
        existing_metrics: list[dict[str, Any]],
    ) -> str:
        """Build prompt for review pass."""
        template = self.prompts.get("review_prompt", "Review and deduplicate metrics.")

        metrics_json = json.dumps(
            [m.model_dump() for m in extracted_metrics],
            ensure_ascii=False,
            indent=2,
        )

        existing_str = "\n".join(
            f"- {m['name']} ({m['code']})"
            for m in existing_metrics[:50]
        )

        # Use replace() instead of format() to avoid conflicts with JSON {} in prompt
        return (
            template
            .replace("{extracted_metrics}", metrics_json)
            .replace("{existing_metrics}", existing_str or "Нет существующих метрик")
        )

    def _parse_ai_response(self, response: dict[str, Any]) -> dict[str, Any]:
        """Parse AI response and extract JSON content."""
        try:
            content = response["choices"][0]["message"]["content"]

            # Try to parse as JSON directly
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                pass

            # Try to extract JSON from markdown code block
            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
            if json_match:
                return json.loads(json_match.group(1))

            # Try to find JSON object/array in text
            for pattern in [r"\{[\s\S]*\}", r"\[[\s\S]*\]"]:
                match = re.search(pattern, content)
                if match:
                    try:
                        return json.loads(match.group(0))
                    except json.JSONDecodeError:
                        continue

            logger.error(f"Failed to parse AI response: {content[:500]}")
            return {"metrics": [], "error": "Failed to parse response"}

        except (KeyError, IndexError) as e:
            logger.error(f"Invalid AI response structure: {e}")
            return {"metrics": [], "error": str(e)}

    async def extract_metrics_from_pdf(
        self,
        pdf_data: bytes,
        existing_metrics: list[dict[str, Any]],
        existing_synonyms: list[dict[str, str]],
        existing_categories: list[dict[str, str]],
    ) -> list[ExtractedMetricData]:
        """
        Extract metrics from entire PDF document using OpenRouter PDF Inputs.

        Sends the complete PDF to the LLM for analysis, allowing it to see
        the full document context including charts and graphs.

        Args:
            pdf_data: PDF file bytes
            existing_*: Context about existing data for matching

        Returns:
            List of extracted metrics with numeric values
        """
        # Use PDF-specific prompt if available
        template = self.prompts.get("extraction_prompt_pdf") or self.prompts.get("extraction_prompt", "Extract metrics as JSON.")

        metrics_str = "\n".join(
            f"- {m['name']} ({m['code']}): {m.get('description', '')}"
            for m in existing_metrics[:50]
        )

        synonyms_str = "\n".join(
            f"- {s['synonym']} → {s['metric_code']}"
            for s in existing_synonyms[:100]
        )

        categories_str = "\n".join(
            f"- {c['name']} ({c['code']})"
            for c in existing_categories
        )

        prompt = (
            template
            .replace("{existing_metrics}", metrics_str or "Нет существующих метрик")
            .replace("{existing_synonyms}", synonyms_str or "Нет синонимов")
            .replace("{existing_categories}", categories_str or "Нет категорий")
        )

        response = await self._client.generate_from_pdf(
            prompt=prompt,
            pdf_data=pdf_data,
            system_instructions=self.prompts.get("system_prompt"),
            response_mime_type="application/json",
            timeout=180,
        )

        parsed = self._parse_ai_response(response)
        metrics: list[ExtractedMetricData] = []

        logger.info(f"PDF extraction AI response: {json.dumps(parsed, ensure_ascii=False, default=str)[:2000]}")

        if isinstance(parsed, list):
            # Handle case where LLM returns [{"metrics": [...]}] instead of [{...}, {...}]
            if len(parsed) == 1 and isinstance(parsed[0], dict) and "metrics" in parsed[0]:
                metrics_list = parsed[0]["metrics"]
                logger.debug("Unwrapped nested metrics array from [{'metrics': [...]}]")
            else:
                metrics_list = parsed
        elif isinstance(parsed, dict):
            metrics_list = parsed.get("metrics", [])
        else:
            logger.warning(f"Unexpected PDF AI response type: {type(parsed).__name__}")
            metrics_list = []

        logger.info(f"PDF extraction: Found {len(metrics_list)} metrics in AI response")

        for m in metrics_list:
            try:
                if not isinstance(m, dict):
                    continue

                name = m.get("name") or m.get("metric_name") or m.get("название") or m.get("title")
                if not name:
                    continue

                value = m.get("value") or m.get("metric_value") or m.get("значение")

                rationale = None
                if m.get("rationale") and isinstance(m.get("rationale"), dict):
                    rationale = AIRationale(
                        quotes=m["rationale"].get("quotes", []),
                        page_numbers=m["rationale"].get("page_numbers", []),
                        confidence=m["rationale"].get("confidence", 0.5),
                    )

                metrics.append(ExtractedMetricData(
                    name=name,
                    description=m.get("description") or m.get("описание"),
                    value=value,
                    category=m.get("category") or m.get("категория"),
                    synonyms=m.get("synonyms", []),
                    rationale=rationale,
                ))
            except (KeyError, ValueError, TypeError) as e:
                logger.warning(f"Failed to parse PDF metric: {e}, data: {m}")
                continue

        filtered = self._filter_metrics_with_values(metrics, source="pdf_extraction")
        logger.info(f"PDF extraction: After filtering: {len(filtered)} metrics")

        return filtered

    async def review_extracted_metrics(
        self,
        metrics: list[ExtractedMetricData],
        existing_metrics: list[dict[str, Any]],
    ) -> AIReviewResult:
        """
        Review and deduplicate extracted metrics (Pass 2).

        Args:
            metrics: Metrics from extraction pass
            existing_metrics: Context about existing metrics

        Returns:
            Reviewed and deduplicated metrics
        """
        if not metrics:
            return AIReviewResult(metrics=[], removed_duplicates=0, corrections_made=0)

        prompt = self._build_review_prompt(metrics, existing_metrics)

        response = await self._client.generate_text(
            prompt=prompt,
            system_instructions=self.prompts.get("system_prompt"),
            response_mime_type="application/json",
            timeout=120,
        )

        parsed = self._parse_ai_response(response)
        reviewed_metrics: list[ExtractedMetricData] = []

        # Handle case where AI returns a list directly instead of {"metrics": [...]}
        if isinstance(parsed, list):
            metrics_list = parsed
        elif isinstance(parsed, dict):
            metrics_list = parsed.get("metrics", [])
        else:
            logger.warning(f"Unexpected AI review response type: {type(parsed).__name__}, value: {str(parsed)[:200]}")
            metrics_list = []

        for m in metrics_list:
            try:
                # Skip non-dict items
                if not isinstance(m, dict):
                    logger.warning(f"Skipping non-dict metric item: {type(m).__name__}")
                    continue

                # Handle alternative key names from AI responses
                name = m.get("name") or m.get("metric_name") or m.get("название") or m.get("title")
                if not name:
                    logger.warning(f"Skipping reviewed metric without name: {m}")
                    continue

                # Handle alternative value keys
                value = m.get("value") or m.get("metric_value") or m.get("значение")

                rationale = None
                if m.get("rationale") and isinstance(m.get("rationale"), dict):
                    rationale = AIRationale(
                        quotes=m["rationale"].get("quotes", []),
                        page_numbers=m["rationale"].get("page_numbers"),
                        confidence=m["rationale"].get("confidence", 0.5),
                    )

                reviewed_metrics.append(ExtractedMetricData(
                    name=name,
                    description=m.get("description") or m.get("описание"),
                    value=value,
                    category=m.get("category") or m.get("категория"),
                    synonyms=m.get("synonyms", []),
                    rationale=rationale,
                ))
            except (KeyError, ValueError, TypeError) as e:
                logger.warning(f"Failed to parse reviewed metric: {e}")
                continue

        # Handle case where parsed is a list (no metadata) vs dict (with metadata)
        if isinstance(parsed, dict):
            removed_duplicates = parsed.get("removed_duplicates", 0)
            corrections_made = parsed.get("corrections_made", 0)
            removed_recommendations = parsed.get("removed_recommendations", 0)
        else:
            removed_duplicates = 0
            corrections_made = 0
            removed_recommendations = 0

        # Filter out metrics without numeric values (safety net)
        filtered_metrics = self._filter_metrics_with_values(reviewed_metrics, source="review")
        code_filtered = len(reviewed_metrics) - len(filtered_metrics)

        return AIReviewResult(
            metrics=filtered_metrics,
            removed_duplicates=removed_duplicates + code_filtered + removed_recommendations,
            corrections_made=corrections_made,
        )

    # ==================== Database Operations ====================

    def _generate_metric_code(self, name: str) -> str:
        """Generate metric code from name (deterministic, no UUID suffix).

        Same name = same code = same metric/category (duplicate/synonym).
        """
        # Transliterate Russian to Latin
        translit_map = {
            'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
            'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
            'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
            'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
            'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
        }

        result = []
        for char in name.lower():
            if char in translit_map:
                result.append(translit_map[char])
            elif char.isalnum():
                result.append(char)
            elif char in ' _-':
                result.append('_')

        code = ''.join(result)
        code = re.sub(r'_+', '_', code).strip('_')

        # Limit length (no UUID suffix - deterministic code)
        if len(code) > 50:
            code = code[:50]

        return code

    async def get_or_create_category(self, category_name: str) -> MetricCategory:
        """
        Get existing category or create new one.

        Uses deterministic code generation: same name = same code = same category.
        If category with this code exists, returns it (treats as synonym/duplicate).
        """
        from sqlalchemy.exc import IntegrityError

        # Generate deterministic code from name
        code = self._generate_metric_code(category_name)

        # Try to find existing by code (exact match)
        result = await self.db.execute(
            select(MetricCategory).where(MetricCategory.code == code)
        )
        existing = result.scalars().first()
        if existing:
            logger.debug(f"Category '{category_name}' matched existing '{existing.name}' by code '{code}'")
            return existing

        # Get max sort_order
        result = await self.db.execute(
            select(MetricCategory.sort_order).order_by(MetricCategory.sort_order.desc()).limit(1)
        )
        max_order = result.scalar() or 0

        category = MetricCategory(
            code=code,
            name=category_name,
            sort_order=max_order + 1,
        )

        try:
            async with self.db.begin_nested():
                self.db.add(category)
                await self.db.flush()
            return category
        except IntegrityError:
            # Concurrent creation - fetch existing by code
            logger.info(f"Category '{category_name}' created concurrently, fetching existing")
            await self.db.rollback()
            result = await self.db.execute(
                select(MetricCategory).where(MetricCategory.code == code)
            )
            existing = result.scalars().first()
            if existing:
                return existing
            raise

    async def get_or_create_pending_metric(
        self,
        metric_data: ExtractedMetricData,
    ) -> tuple[MetricDef, bool]:
        """
        Get existing metric by code or create new one in PENDING status.

        Uses deterministic code generation: same name = same code = same metric.
        Returns tuple of (metric, created) where created=False if metric existed.
        """
        from sqlalchemy.exc import IntegrityError

        code = self._generate_metric_code(metric_data.name)

        # Check if metric with this code already exists
        result = await self.db.execute(
            select(MetricDef).where(MetricDef.code == code)
        )
        existing = result.scalars().first()
        if existing:
            logger.debug(f"Metric '{metric_data.name}' matched existing '{existing.name}' by code '{code}'")
            return existing, False

        # Get or create category
        category_id = None
        if metric_data.category:
            category = await self.get_or_create_category(metric_data.category)
            category_id = category.id

        # Prepare rationale JSONB
        rationale_json = None
        if metric_data.rationale:
            rationale_json = metric_data.rationale.model_dump()

        # Get max sort_order
        result = await self.db.execute(
            select(MetricDef.sort_order).order_by(MetricDef.sort_order.desc()).limit(1)
        )
        max_order = result.scalar() or 0

        metric = MetricDef(
            code=code,
            name=metric_data.name,
            name_ru=metric_data.name,
            description=metric_data.description,
            min_value=1,
            max_value=10,
            category_id=category_id,
            sort_order=max_order + 1,
            moderation_status="PENDING",
            ai_rationale=rationale_json,
        )

        try:
            async with self.db.begin_nested():
                self.db.add(metric)
                await self.db.flush()

                # Add suggested synonyms
                for synonym in metric_data.synonyms[:5]:
                    existing_syn = await self.db.execute(
                        select(MetricSynonym).where(MetricSynonym.synonym == synonym)
                    )
                    if not existing_syn.scalars().first():
                        self.db.add(MetricSynonym(
                            metric_def_id=metric.id,
                            synonym=synonym,
                        ))

                await self.db.flush()
            return metric, True
        except IntegrityError:
            # Concurrent creation - fetch existing by code
            logger.info(f"Metric '{metric_data.name}' created concurrently, fetching existing")
            await self.db.rollback()
            result = await self.db.execute(
                select(MetricDef).where(MetricDef.code == code)
            )
            existing = result.scalars().first()
            if existing:
                return existing, False
            raise

    async def match_existing_metric(
        self,
        metric_data: ExtractedMetricData,
        existing_metrics: list[dict[str, Any]],
        existing_synonyms: list[dict[str, str]],
    ) -> MetricDef | None:
        """
        Try to match metric with existing definition.

        Uses normalized comparison to handle:
        - Case differences (Нормативность vs нормативность)
        - Unicode variations (NFKC normalization)
        - Extra whitespace
        """
        import unicodedata

        def normalize_name(name: str | None) -> str:
            """Normalize name for comparison: lowercase, strip, unicode NFKC."""
            if not name:
                return ""
            # NFKC normalization handles compatibility characters
            return unicodedata.normalize("NFKC", name.lower().strip())

        name_normalized = normalize_name(metric_data.name)
        if not name_normalized:
            return None

        # Check exact name match (both name and name_ru)
        for m in existing_metrics:
            if normalize_name(m["name"]) == name_normalized:
                result = await self.db.execute(
                    select(MetricDef).where(MetricDef.code == m["code"])
                )
                return result.scalars().first()

            if normalize_name(m.get("name_ru")) == name_normalized:
                result = await self.db.execute(
                    select(MetricDef).where(MetricDef.code == m["code"])
                )
                return result.scalars().first()

        # Check synonym match
        for s in existing_synonyms:
            if normalize_name(s["synonym"]) == name_normalized:
                result = await self.db.execute(
                    select(MetricDef).where(MetricDef.code == s["metric_code"])
                )
                return result.scalars().first()

        return None

    async def match_metric_semantic(
        self,
        extracted: ExtractedMetricData,
    ) -> tuple[MetricDef | None, float]:
        """
        Semantic matching of extracted metric using RAG + LLM decision.

        Uses embedding service to find similar metrics (RAG), then AI to decide
        if it's a true duplicate or a new metric. This method uses the same
        logic as the PDF extraction RAG mapping to ensure consistency.

        Args:
            extracted: Extracted metric data from document

        Returns:
            (matched_metric, similarity) or (None, 0.0) if no match
        """
        from app.services.metric_mapping_llm_decision import decide_metric_mapping
        from app.core.ai_factory import create_ai_client

        # Build search text - prioritize name for better matching
        search_text = extracted.name

        # Find similar metrics using vector search (RAG)
        # Use lower threshold to get more candidates for LLM to decide
        try:
            candidates = await self.embedding_service.find_similar(
                search_text,
                top_k=10,  # Get more candidates for LLM
                threshold=settings.rag_candidate_min_threshold,  # Use same threshold as RAG mapping (0.5)
            )
        except Exception as e:
            logger.warning(f"Semantic search failed: {e}")
            return None, 0.0

        if not candidates:
            # No similar metrics found - return None to trigger new metric creation.
            # NOTE: Previously used category fallback here, but this caused false matches
            # because LLM would match against unrelated metrics from the same category.
            # See: docs/issues/2026-02-05-metric-generation-no-new-metrics.md
            logger.debug(
                "no_rag_candidates_returning_none",
                extra={"extracted_name": extracted.name, "category": extracted.category},
            )
            return None, 0.0

        # Auto-match: if top candidate has very high similarity (>= 0.95), skip LLM
        auto_match_threshold = settings.rag_auto_match_threshold  # 0.95
        if candidates[0]["similarity"] >= auto_match_threshold:
            metric = await self.db.get(MetricDef, candidates[0]["metric_def_id"])
            logger.info(
                "semantic_auto_match",
                extra={
                    "extracted_name": extracted.name,
                    "matched_code": candidates[0]["code"],
                    "similarity": candidates[0]["similarity"],
                    "threshold": auto_match_threshold,
                },
            )
            return metric, candidates[0]["similarity"]

        # Use LLM to decide the best match from candidates
        # This uses the same logic as report_rag_mapping.py for consistency
        ai_client = create_ai_client()
        try:
            decision = await decide_metric_mapping(
                ai_client=ai_client,
                label=extracted.name,
                candidates=candidates,
                min_confidence=0.6,
                description=extracted.description,
            )
        except Exception as e:
            logger.error(f"LLM decision failed: {e}")
            return None, 0.0
        finally:
            await ai_client.close()

        if decision["status"] == "mapped" and decision["code"]:
            # Find the metric by code
            result = await self.db.execute(
                select(MetricDef).where(MetricDef.code == decision["code"])
            )
            metric = result.scalars().first()
            if metric:
                logger.info(
                    "semantic_llm_match",
                    extra={
                        "extracted_name": extracted.name,
                        "matched_code": decision["code"],
                        "confidence": decision.get("confidence", 0.0),
                        "reason": decision.get("reason", ""),
                    },
                )
                return metric, decision.get("confidence", 0.8)

        # LLM decided unknown or ambiguous - treat as no match (create new)
        logger.debug(
            "semantic_llm_no_match",
            extra={
                "extracted_name": extracted.name,
                "status": decision["status"],
                "reason": decision.get("reason", ""),
            },
        )
        return None, 0.0

    async def _get_category_fallback_candidates(
        self,
        extracted: ExtractedMetricData,
        max_candidates: int = 15,
    ) -> list[dict[str, Any]]:
        """
        Fallback: get metrics from same category for LLM matching.

        Used when RAG doesn't find candidates (similarity too low).
        Returns metrics formatted as candidates for LLM decision.
        """
        from sqlalchemy.orm import selectinload

        query = select(MetricDef).where(
            MetricDef.moderation_status == "APPROVED"
        ).options(selectinload(MetricDef.category))

        # Filter by category if specified
        if extracted.category:
            category_code = self._generate_metric_code(extracted.category)
            query = query.join(MetricCategory).where(
                MetricCategory.code == category_code
            )

        query = query.limit(max_candidates)
        result = await self.db.execute(query)
        metrics = result.scalars().all()

        if not metrics:
            return []

        # Format as candidates (similarity=0 since not from RAG)
        candidates = []
        for m in metrics:
            candidates.append({
                "metric_def_id": m.id,
                "code": m.code,
                "name": m.name,
                "name_ru": m.name_ru,
                "description": m.description or "",
                "category": m.category.name if m.category else None,
                "similarity": 0.0,  # Not from RAG, just category match
            })

        logger.debug(
            "category_fallback_candidates",
            extra={
                "extracted_name": extracted.name,
                "category": extracted.category,
                "found_count": len(candidates),
            },
        )
        return candidates

    async def _add_synonym_if_new(
        self,
        metric_def_id: uuid.UUID,
        synonym_text: str,
    ) -> bool:
        """
        Add extracted name as synonym if not already exists.

        Uses savepoint pattern to handle concurrent insertion gracefully.

        Args:
            metric_def_id: Metric to add synonym to
            synonym_text: Text to add as synonym

        Returns:
            True if synonym was added, False if already exists
        """
        from sqlalchemy.exc import IntegrityError

        # Normalize synonym
        synonym_normalized = synonym_text.strip()
        if not synonym_normalized:
            return False

        # Check if synonym already exists (case-insensitive)
        result = await self.db.execute(
            select(MetricSynonym).where(
                MetricSynonym.synonym.ilike(synonym_normalized)
            )
        )
        if result.scalars().first():
            return False

        # Add new synonym with savepoint protection
        new_synonym = MetricSynonym(
            metric_def_id=metric_def_id,
            synonym=synonym_normalized,
        )

        try:
            async with self.db.begin_nested():
                self.db.add(new_synonym)
                await self.db.flush()
            logger.info(
                "synonym_added_from_extraction",
                extra={
                    "metric_def_id": str(metric_def_id),
                    "synonym": synonym_normalized,
                },
            )
            return True
        except IntegrityError:
            # Synonym was created concurrently, that's fine
            logger.debug(f"Synonym '{synonym_normalized}' already exists (concurrent insert)")
            await self.db.rollback()
            return False

    # ==================== Main Processing ====================

    async def process_document(
        self,
        task_id: str,
        file_data: bytes,
        filename: str,
    ) -> dict[str, Any]:
        """
        Process document and generate metrics.

        Args:
            task_id: Celery task ID for progress tracking
            file_data: File content bytes
            filename: Original filename

        Returns:
            Result summary with created/matched metrics
        """
        result = {
            "metrics_created": 0,
            "metrics_matched": 0,
            "categories_created": 0,
            "synonyms_suggested": 0,
            "errors": [],
            "warnings": [],
        }

        try:
            # Step 1: Convert DOCX to PDF if needed
            await self.update_progress(
                task_id, TaskStatus.PROCESSING, 5,
                current_step="Подготовка документа..."
            )

            # Convert DOCX to PDF if needed
            pdf_data = file_data
            if filename.lower().endswith(".docx"):
                await self.update_progress(
                    task_id, TaskStatus.PROCESSING, 3,
                    current_step="Конвертация DOCX в PDF..."
                )
                try:
                    pdf_data = self.convert_docx_to_pdf(file_data)
                    result["warnings"].append("DOCX автоматически конвертирован в PDF")
                except RuntimeError as e:
                    result["errors"].append(str(e))
                    await self.update_progress(
                        task_id, TaskStatus.FAILED, 0,
                        error=f"Ошибка конвертации DOCX: {e}"
                    )
                    return result

            # Validate PDF size
            if len(pdf_data) > MAX_PDF_SIZE:
                error_msg = f"PDF слишком большой: {len(pdf_data) / 1024 / 1024:.1f}MB (макс: 10MB)"
                result["errors"].append(error_msg)
                await self.update_progress(
                    task_id, TaskStatus.FAILED, 0,
                    error=error_msg
                )
                return result

            # Step 2: Load context
            existing_metrics = await self.get_existing_metrics()
            existing_synonyms = await self.get_existing_synonyms()
            existing_categories = await self.get_existing_categories()

            # Step 3: Extract metrics from PDF directly
            await self.update_progress(
                task_id, TaskStatus.PROCESSING, 20,
                current_step="Анализ PDF документа..."
            )

            all_extracted = await self.extract_metrics_from_pdf(
                pdf_data,
                existing_metrics, existing_synonyms, existing_categories,
            )

            await self.update_progress(
                task_id, TaskStatus.PROCESSING, 70,
                current_step=f"Найдено {len(all_extracted)} метрик",
                metrics_found=len(all_extracted),
            )

            await self.update_progress(
                task_id, TaskStatus.PROCESSING, 75,
                current_step="Проверка и дедупликация метрик...",
                metrics_found=len(all_extracted),
            )

            # Step 4: Review pass
            reviewed = await self.review_extracted_metrics(all_extracted, existing_metrics)

            await self.update_progress(
                task_id, TaskStatus.PROCESSING, 85,
                current_step="Сохранение результатов...",
                metrics_found=len(reviewed.metrics),
            )

            # Step 5: Save to database with semantic matching
            for metric_data in reviewed.metrics:
                try:
                    # First try exact match (fast)
                    existing = await self.match_existing_metric(
                        metric_data, existing_metrics, existing_synonyms
                    )

                    if existing:
                        result["metrics_matched"] += 1
                        logger.debug(f"Exact match: '{metric_data.name}' → '{existing.name}'")
                        continue

                    # Try semantic matching (slower but smarter)
                    matched, similarity = await self.match_metric_semantic(metric_data)

                    if matched:
                        result["metrics_matched"] += 1
                        # Add extracted name as synonym to help future matching
                        await self._add_synonym_if_new(matched.id, metric_data.name)
                        logger.info(
                            f"Semantic match: '{metric_data.name}' → '{matched.name}' "
                            f"(similarity={similarity:.2f})"
                        )
                    else:
                        # Get or create metric (same name = same code = duplicate)
                        metric, created = await self.get_or_create_pending_metric(metric_data)
                        if created:
                            result["metrics_created"] += 1
                            result["synonyms_suggested"] += len(metric_data.synonyms)
                        else:
                            result["metrics_matched"] += 1
                            logger.info(f"Duplicate by code: '{metric_data.name}' → '{metric.name}'")

                except Exception as e:
                    # Log error but continue processing remaining metrics
                    logger.warning(
                        f"Error processing metric '{metric_data.name}': {e}",
                        exc_info=True,
                    )
                    result["warnings"].append(f"Ошибка обработки метрики '{metric_data.name}': {str(e)}")
                    # Ensure transaction is in clean state
                    try:
                        await self.db.rollback()
                    except Exception:
                        pass  # Already rolled back
                    continue

            await self.db.commit()

            await self.update_progress(
                task_id, TaskStatus.COMPLETED, 100,
                current_step="Готово",
                result=result,
            )

        except Exception as e:
            logger.exception(f"Failed to process document: {e}")
            result["errors"].append(str(e))
            await self.update_progress(
                task_id, TaskStatus.FAILED, 0,
                error=str(e),
            )
            raise

        return result

    async def close(self) -> None:
        """Close client resources."""
        await self._client.close()
        if self.embedding_service:
            await self.embedding_service.close()
