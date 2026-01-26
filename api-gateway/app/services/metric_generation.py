"""
Service for AI-powered metric generation from PDF/DOCX reports.

Handles:
- PDF/DOCX file processing and conversion to images
- AI extraction using OpenRouter Vision API
- Multi-pass generation (extraction + review)
- Deduplication and matching with existing metrics
- Progress tracking via Redis
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
from PIL import Image
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
MAX_IMAGE_SIZE = 4 * 1024 * 1024  # 4MB per image
DPI = 150  # Resolution for PDF rendering


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
        """
        Convert DOCX to PDF using pypandoc (requires pandoc installed).

        Args:
            docx_data: DOCX file content bytes

        Returns:
            PDF file content bytes

        Raises:
            RuntimeError: If pandoc is not installed or conversion fails
        """
        import tempfile
        import shutil

        # Check if pandoc is available
        if not shutil.which("pandoc"):
            logger.warning("Pandoc not installed, attempting to use pypandoc auto-download")

        try:
            import pypandoc

            # Create temp files for input/output
            with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as docx_file:
                docx_file.write(docx_data)
                docx_path = docx_file.name

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as pdf_file:
                pdf_path = pdf_file.name

            try:
                # Convert DOCX to PDF
                pypandoc.convert_file(
                    docx_path,
                    "pdf",
                    outputfile=pdf_path,
                    extra_args=["--pdf-engine=pdflatex"]
                )

                # Read resulting PDF
                with open(pdf_path, "rb") as f:
                    pdf_data = f.read()

                if not pdf_data:
                    raise RuntimeError("Conversion produced empty PDF")

                return pdf_data

            finally:
                # Cleanup temp files
                import os
                try:
                    os.unlink(docx_path)
                    os.unlink(pdf_path)
                except OSError:
                    pass

        except ImportError:
            raise RuntimeError(
                "pypandoc not installed. Run: pip install pypandoc"
            )
        except Exception as e:
            logger.exception(f"DOCX→PDF conversion failed: {e}")
            raise RuntimeError(
                f"DOCX to PDF conversion failed: {e}. "
                "Ensure pandoc and pdflatex are installed."
            )

    def pdf_to_images(self, pdf_data: bytes) -> list[tuple[bytes, int]]:
        """
        Convert PDF pages to images.

        Returns:
            List of (image_bytes, page_number) tuples
        """
        images: list[tuple[bytes, int]] = []

        with fitz.open(stream=pdf_data, filetype="pdf") as doc:
            for page_num in range(len(doc)):
                page = doc[page_num]

                # Render page to image
                mat = fitz.Matrix(DPI / 72, DPI / 72)
                pix = page.get_pixmap(matrix=mat)

                # Convert to PNG bytes
                img_data = pix.tobytes("png")

                # Resize if too large
                if len(img_data) > MAX_IMAGE_SIZE:
                    img = Image.open(io.BytesIO(img_data))
                    # Reduce size by 50%
                    new_size = (img.width // 2, img.height // 2)
                    img = img.resize(new_size, Image.Resampling.LANCZOS)

                    buffer = io.BytesIO()
                    img.save(buffer, format="PNG", optimize=True)
                    img_data = buffer.getvalue()

                images.append((img_data, page_num + 1))

        return images

    def smart_chunk_images(
        self, images: list[tuple[bytes, int]], max_pages_per_chunk: int = 5
    ) -> list[list[tuple[bytes, int]]]:
        """
        Split images into chunks for processing.

        Args:
            images: List of (image_bytes, page_number) tuples
            max_pages_per_chunk: Maximum pages per AI call

        Returns:
            List of chunks, each containing up to max_pages_per_chunk images
        """
        chunks: list[list[tuple[bytes, int]]] = []
        current_chunk: list[tuple[bytes, int]] = []

        for img in images:
            current_chunk.append(img)
            if len(current_chunk) >= max_pages_per_chunk:
                chunks.append(current_chunk)
                current_chunk = []

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

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

    async def extract_metrics_from_image(
        self,
        image_data: bytes,
        page_number: int,
        existing_metrics: list[dict[str, Any]],
        existing_synonyms: list[dict[str, str]],
        existing_categories: list[dict[str, str]],
    ) -> list[ExtractedMetricData]:
        """
        Extract metrics from a single page image.

        Args:
            image_data: PNG image bytes
            page_number: Page number for context
            existing_*: Context about existing data

        Returns:
            List of extracted metrics
        """
        prompt = self._build_extraction_prompt(
            existing_metrics, existing_synonyms, existing_categories
        )

        # Add page context
        prompt = f"Страница {page_number}.\n\n{prompt}"

        response = await self._client.generate_from_image(
            prompt=prompt,
            image_data=image_data,
            mime_type="image/png",
            response_mime_type="application/json",
            timeout=120,
        )

        parsed = self._parse_ai_response(response)
        metrics: list[ExtractedMetricData] = []

        # Handle case where AI returns a list directly instead of {"metrics": [...]}
        if isinstance(parsed, list):
            metrics_list = parsed
        elif isinstance(parsed, dict):
            metrics_list = parsed.get("metrics", [])
        else:
            logger.warning(f"Unexpected AI response type: {type(parsed).__name__}, value: {str(parsed)[:200]}")
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
                    logger.warning(f"Skipping metric without name: {m}")
                    continue

                # Handle alternative value keys
                value = m.get("value") or m.get("metric_value") or m.get("значение")

                rationale = None
                if m.get("rationale") and isinstance(m.get("rationale"), dict):
                    rationale = AIRationale(
                        quotes=m["rationale"].get("quotes", []),
                        page_numbers=m["rationale"].get("page_numbers", [page_number]),
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
                logger.warning(f"Failed to parse metric: {e}, data: {m}")
                continue

        return metrics

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
        else:
            removed_duplicates = 0
            corrections_made = 0

        return AIReviewResult(
            metrics=reviewed_metrics,
            removed_duplicates=removed_duplicates,
            corrections_made=corrections_made,
        )

    # ==================== Database Operations ====================

    def _generate_metric_code(self, name: str) -> str:
        """Generate unique metric code from name."""
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

        # Limit length and add uniqueness
        if len(code) > 40:
            code = code[:40]

        code = f"{code}_{uuid.uuid4().hex[:6]}"
        return code

    async def get_or_create_category(self, category_name: str) -> MetricCategory:
        """
        Get existing category or create new one.

        Uses savepoint pattern to handle concurrent creation attempts gracefully.
        If IntegrityError occurs (duplicate code), rolls back to savepoint and
        returns the existing category.
        """
        from sqlalchemy.exc import IntegrityError

        # Try to find existing (case-insensitive partial match)
        result = await self.db.execute(
            select(MetricCategory).where(
                MetricCategory.name.ilike(f"%{category_name}%")
            )
        )
        existing = result.scalars().first()
        if existing:
            return existing

        # Create new category with savepoint protection
        code = self._generate_metric_code(category_name)[:50]

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
            # Use savepoint so IntegrityError doesn't abort outer transaction
            async with self.db.begin_nested():
                self.db.add(category)
                await self.db.flush()
            return category
        except IntegrityError:
            # Another request created the same category concurrently
            # Rollback handled by begin_nested context manager
            logger.info(f"Category '{category_name}' created concurrently, fetching existing")
            await self.db.rollback()  # Ensure clean state
            result = await self.db.execute(
                select(MetricCategory).where(
                    MetricCategory.name.ilike(f"%{category_name}%")
                )
            )
            existing = result.scalars().first()
            if existing:
                return existing
            # If still not found, re-raise (shouldn't happen)
            raise

    async def create_pending_metric(
        self,
        metric_data: ExtractedMetricData,
    ) -> MetricDef:
        """
        Create a new metric in PENDING moderation status.

        Uses savepoint pattern to handle potential constraint violations gracefully.
        """
        from sqlalchemy.exc import IntegrityError

        code = self._generate_metric_code(metric_data.name)

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
                    # Check if synonym already exists
                    existing = await self.db.execute(
                        select(MetricSynonym).where(MetricSynonym.synonym == synonym)
                    )
                    if not existing.scalars().first():
                        self.db.add(MetricSynonym(
                            metric_def_id=metric.id,
                            synonym=synonym,
                        ))

                await self.db.flush()
            return metric
        except IntegrityError as e:
            logger.warning(f"IntegrityError creating metric '{metric_data.name}': {e}")
            await self.db.rollback()
            raise

    async def match_existing_metric(
        self,
        metric_data: ExtractedMetricData,
        existing_metrics: list[dict[str, Any]],
        existing_synonyms: list[dict[str, str]],
    ) -> MetricDef | None:
        """Try to match metric with existing definition."""
        name_lower = metric_data.name.lower().strip()

        # Check exact name match
        for m in existing_metrics:
            if m["name"].lower() == name_lower or (m.get("name_ru") and m["name_ru"].lower() == name_lower):
                result = await self.db.execute(
                    select(MetricDef).where(MetricDef.code == m["code"])
                )
                return result.scalars().first()

        # Check synonym match
        for s in existing_synonyms:
            if s["synonym"].lower() == name_lower:
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
        Semantic matching of extracted metric using vector similarity.

        Uses embedding service to find similar metrics, then AI to decide
        if it's a true duplicate or a new metric.

        Args:
            extracted: Extracted metric data from document

        Returns:
            (matched_metric, similarity) or (None, 0.0) if no match
        """
        # Build search text from name and description
        search_text = f"{extracted.name} | {extracted.description or ''}"

        # Find similar metrics using vector search
        try:
            similar = await self.embedding_service.find_similar(
                search_text,
                top_k=5,
                threshold=settings.embedding_similarity_threshold,
            )
        except Exception as e:
            logger.warning(f"Semantic search failed, falling back to exact match: {e}")
            return None, 0.0

        if not similar:
            return None, 0.0

        # If only one candidate with very high similarity (>0.9) - auto-match
        if len(similar) == 1 and similar[0]["similarity"] > 0.9:
            metric = await self.db.get(MetricDef, similar[0]["metric_def_id"])
            logger.info(
                "semantic_auto_match",
                extra={
                    "extracted_name": extracted.name,
                    "matched_code": similar[0]["code"],
                    "similarity": similar[0]["similarity"],
                },
            )
            return metric, similar[0]["similarity"]

        # Multiple candidates or lower similarity - ask AI to decide
        decision = await self._ai_decide_match(extracted, similar)

        if decision.get("is_duplicate") and decision.get("matched_code"):
            result = await self.db.execute(
                select(MetricDef).where(MetricDef.code == decision["matched_code"])
            )
            metric = result.scalars().first()
            if metric:
                logger.info(
                    "semantic_ai_match",
                    extra={
                        "extracted_name": extracted.name,
                        "matched_code": decision["matched_code"],
                        "confidence": decision.get("confidence", 0.8),
                        "reasoning": decision.get("reasoning", ""),
                    },
                )
                return metric, decision.get("confidence", 0.8)

        return None, 0.0

    async def _ai_decide_match(
        self,
        extracted: ExtractedMetricData,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Use AI to decide if extracted metric is a duplicate of any candidate.

        Args:
            extracted: Extracted metric data
            candidates: List of similar metrics from vector search

        Returns:
            Dict with is_duplicate, matched_code, confidence, reasoning
        """
        candidates_str = "\n".join(
            f"- {c['name']} ({c['code']}): {c.get('description', 'нет описания')} "
            f"[сходство: {c['similarity']:.2f}]"
            for c in candidates
        )

        prompt = f"""
Извлечённая метрика из документа:
- Название: {extracted.name}
- Описание: {extracted.description or 'нет'}

Похожие метрики из справочника (найдены через semantic search):
{candidates_str}

Задача: Определи, является ли извлечённая метрика дубликатом одной из метрик в справочнике.

Критерии дубликата:
1. Семантически идентичное или очень близкое значение
2. Одна метрика может быть переформулировкой другой
3. Разные формулировки одного и того же показателя

Ответь строго в JSON формате:
{{
  "is_duplicate": true/false,
  "matched_code": "код_метрики" или null,
  "confidence": 0.0-1.0,
  "reasoning": "краткое объяснение решения"
}}
"""
        try:
            response = await self._client.generate_text(
                prompt=prompt,
                response_mime_type="application/json",
                timeout=30,
            )
            parsed = self._parse_ai_response(response)

            if isinstance(parsed, dict) and "is_duplicate" in parsed:
                return parsed
            else:
                logger.warning(f"AI match decision missing required fields or wrong type: {type(parsed).__name__}, {str(parsed)[:200]}")
                return {"is_duplicate": False, "matched_code": None, "confidence": 0.0}

        except Exception as e:
            logger.error(f"AI match decision failed: {e}")
            return {"is_duplicate": False, "matched_code": None, "confidence": 0.0}

    async def _add_synonym_if_new(
        self,
        metric_def_id: uuid.UUID,
        synonym_text: str,
    ) -> bool:
        """
        Add extracted name as synonym if not already exists.

        Args:
            metric_def_id: Metric to add synonym to
            synonym_text: Text to add as synonym

        Returns:
            True if synonym was added, False if already exists
        """
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

        # Add new synonym
        new_synonym = MetricSynonym(
            metric_def_id=metric_def_id,
            synonym=synonym_normalized,
        )
        self.db.add(new_synonym)
        logger.info(
            "synonym_added_from_extraction",
            extra={
                "metric_def_id": str(metric_def_id),
                "synonym": synonym_normalized,
            },
        )
        return True

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
            # Step 1: Convert to images
            await self.update_progress(
                task_id, TaskStatus.PROCESSING, 5,
                current_step="Конвертация документа в изображения..."
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

            images = self.pdf_to_images(pdf_data)
            total_pages = len(images)

            await self.update_progress(
                task_id, TaskStatus.PROCESSING, 10,
                current_step=f"Найдено {total_pages} страниц",
                total_pages=total_pages,
            )

            # Step 2: Load context
            existing_metrics = await self.get_existing_metrics()
            existing_synonyms = await self.get_existing_synonyms()
            existing_categories = await self.get_existing_categories()

            # Step 3: Extract metrics from each page
            all_extracted: list[ExtractedMetricData] = []
            chunks = self.smart_chunk_images(images)

            for chunk_idx, chunk in enumerate(chunks):
                for img_data, page_num in chunk:
                    progress = 10 + int((page_num / total_pages) * 60)
                    await self.update_progress(
                        task_id, TaskStatus.PROCESSING, progress,
                        current_step=f"Обработка страницы {page_num}/{total_pages}",
                        processed_pages=page_num,
                        total_pages=total_pages,
                    )

                    try:
                        page_metrics = await self.extract_metrics_from_image(
                            img_data, page_num,
                            existing_metrics, existing_synonyms, existing_categories,
                        )
                        all_extracted.extend(page_metrics)
                    except Exception as e:
                        logger.warning(f"Failed to process page {page_num}: {e}")
                        result["warnings"].append(f"Ошибка на странице {page_num}: {str(e)}")

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
                    # Create new pending metric
                    await self.create_pending_metric(metric_data)
                    result["metrics_created"] += 1
                    result["synonyms_suggested"] += len(metric_data.synonyms)

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
