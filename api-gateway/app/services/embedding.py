"""
Embedding service for semantic metric matching.

Provides:
- Vector embedding generation via OpenRouter API
- Metric indexing with pgvector storage
- Semantic similarity search for metric matching
- Batch and single-metric indexing operations

Based on Context7 documentation:
- OpenRouter: POST /api/v1/embeddings with model "openai/text-embedding-3-small"
- pgvector: cosine distance operator <=> for similarity search
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.openrouter import OpenRouterClient
from app.core.config import settings
from app.db.models import MetricDef, MetricEmbedding, MetricSynonym

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Service for managing metric embeddings and semantic search.

    Handles:
    - Generating embeddings via OpenRouter API (openai/text-embedding-3-small)
    - Storing embeddings in PostgreSQL with pgvector
    - Searching for similar metrics using cosine similarity
    - Auto-indexing when metrics are created/updated
    """

    def __init__(
        self,
        db: AsyncSession,
        client: OpenRouterClient | None = None,
    ):
        """
        Initialize embedding service.

        Args:
            db: Async database session
            client: Optional OpenRouter client (creates default if not provided)
        """
        self.db = db
        self._client = client
        self._owns_client = client is None

    async def _get_client(self) -> OpenRouterClient:
        """Get or create OpenRouter client (lazy initialization)."""
        if self._client is None:
            api_keys = settings.openrouter_keys_list
            if not api_keys:
                raise ValueError("OPENROUTER_API_KEYS required for embedding service")

            self._client = OpenRouterClient(
                api_key=api_keys[0],
                model_text=settings.embedding_model,
                model_vision=settings.embedding_model,
                timeout_s=60,
            )
        return self._client

    def _build_index_text(self, metric: MetricDef, synonyms: list[str]) -> str:
        """
        Build text for embedding from metric data.

        Combines name, Russian name, description, and synonyms
        with separators for better embedding quality.
        """
        parts = [
            metric.name,
            metric.name_ru or "",
            metric.description or "",
            " ".join(synonyms) if synonyms else "",
        ]
        # Filter empty parts and join with separator
        return " | ".join(filter(None, parts))

    async def generate_embedding(self, text: str) -> list[float]:
        """
        Generate embedding vector for given text.

        Uses OpenRouter API with model openai/text-embedding-3-small (1536 dimensions).

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding vector (1536 dimensions)

        Raises:
            ValueError: If API response is invalid
        """
        client = await self._get_client()

        response = await client.create_embedding(
            input_text=text,
            model=settings.embedding_model,
            timeout=60.0,
        )

        # Extract embedding from response
        # Response format: {"data": [{"embedding": [...], "index": 0}], "model": "...", "usage": {...}}
        try:
            embedding = response["data"][0]["embedding"]
            logger.debug(
                "embedding_generated",
                extra={
                    "text_length": len(text),
                    "embedding_dims": len(embedding),
                    "model": settings.embedding_model,
                    "usage": response.get("usage"),
                },
            )
            return embedding
        except (KeyError, IndexError) as e:
            logger.error(f"Invalid embedding response: {response}")
            raise ValueError(f"Failed to extract embedding from response: {e}") from e

    async def index_metric(self, metric_def_id: uuid.UUID) -> MetricEmbedding:
        """
        Index a single metric by generating and storing its embedding.

        Args:
            metric_def_id: UUID of the metric definition to index

        Returns:
            The created or updated MetricEmbedding record

        Raises:
            ValueError: If metric not found
        """
        # Load metric
        result = await self.db.execute(
            select(MetricDef).where(MetricDef.id == metric_def_id)
        )
        metric = result.scalar_one_or_none()
        if not metric:
            raise ValueError(f"MetricDef {metric_def_id} not found")

        # Load synonyms
        result = await self.db.execute(
            select(MetricSynonym.synonym).where(
                MetricSynonym.metric_def_id == metric_def_id
            )
        )
        synonyms = [row[0] for row in result.all()]

        # Build text and generate embedding
        index_text = self._build_index_text(metric, synonyms)
        embedding = await self.generate_embedding(index_text)

        # Upsert embedding record
        result = await self.db.execute(
            select(MetricEmbedding).where(
                MetricEmbedding.metric_def_id == metric_def_id
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.embedding = embedding
            existing.indexed_text = index_text
            existing.model = settings.embedding_model
            existing.indexed_at = datetime.now(timezone.utc)
            logger.info(
                "metric_embedding_updated",
                extra={"metric_def_id": str(metric_def_id), "metric_name": metric.name},
            )
            return existing
        else:
            new_embedding = MetricEmbedding(
                metric_def_id=metric_def_id,
                embedding=embedding,
                indexed_text=index_text,
                model=settings.embedding_model,
            )
            self.db.add(new_embedding)
            logger.info(
                "metric_embedding_created",
                extra={"metric_def_id": str(metric_def_id), "metric_name": metric.name},
            )
            return new_embedding

    async def index_all_metrics(self, batch_size: int = 50) -> dict[str, int]:
        """
        Index all APPROVED metrics.

        Args:
            batch_size: Number of metrics to process before committing

        Returns:
            Summary dict with indexed, errors, and total counts
        """
        # Get all APPROVED metric IDs
        result = await self.db.execute(
            select(MetricDef.id).where(MetricDef.moderation_status == "APPROVED")
        )
        metric_ids = [row[0] for row in result.all()]

        indexed = 0
        errors = 0
        total = len(metric_ids)

        logger.info(
            "index_all_metrics_started",
            extra={"total_metrics": total},
        )

        for i, metric_id in enumerate(metric_ids):
            try:
                await self.index_metric(metric_id)
                indexed += 1

                # Commit in batches
                if (i + 1) % batch_size == 0:
                    await self.db.commit()
                    logger.debug(f"Committed batch {(i + 1) // batch_size}")

            except Exception as e:
                logger.error(
                    "index_metric_failed",
                    extra={"metric_id": str(metric_id), "error": str(e)},
                )
                errors += 1

        # Final commit
        await self.db.commit()

        logger.info(
            "index_all_metrics_completed",
            extra={"indexed": indexed, "errors": errors, "total": total},
        )

        return {"indexed": indexed, "errors": errors, "total": total}

    async def find_similar(
        self,
        query_text: str,
        top_k: int | None = None,
        threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Find metrics similar to the given text using vector search.

        Uses pgvector cosine distance operator (<=>) for similarity search.
        Cosine similarity = 1 - cosine_distance.

        Args:
            query_text: Text to search for (e.g., extracted metric name)
            top_k: Number of results to return (default from settings)
            threshold: Minimum similarity score (default from settings)

        Returns:
            List of dicts with metric info and similarity scores
        """
        top_k = top_k or settings.embedding_top_k
        threshold = threshold or settings.embedding_similarity_threshold

        # Generate embedding for query
        query_embedding = await self.generate_embedding(query_text)

        # Vector search using cosine distance operator <=>
        # Cosine similarity = 1 - cosine_distance
        # Based on Context7 pgvector docs: ORDER BY embedding <=> :embedding
        sql = text("""
            SELECT
                me.metric_def_id,
                md.code,
                md.name,
                md.name_ru,
                md.description,
                1 - (me.embedding <=> :embedding::vector) as similarity
            FROM metric_embedding me
            JOIN metric_def md ON md.id = me.metric_def_id
            WHERE md.moderation_status = 'APPROVED'
            ORDER BY me.embedding <=> :embedding::vector
            LIMIT :top_k
        """)

        result = await self.db.execute(
            sql,
            {
                "embedding": str(query_embedding),
                "top_k": top_k,
            },
        )

        matches = []
        for row in result.all():
            similarity = float(row.similarity)
            if similarity >= threshold:
                matches.append({
                    "metric_def_id": row.metric_def_id,
                    "code": row.code,
                    "name": row.name,
                    "name_ru": row.name_ru,
                    "description": row.description,
                    "similarity": round(similarity, 4),
                })

        logger.debug(
            "find_similar_completed",
            extra={
                "query_text": query_text[:50],
                "matches_found": len(matches),
                "top_k": top_k,
                "threshold": threshold,
            },
        )

        return matches

    async def delete_embedding(self, metric_def_id: uuid.UUID) -> bool:
        """
        Delete embedding for a metric.

        Args:
            metric_def_id: UUID of the metric

        Returns:
            True if deleted, False if not found
        """
        result = await self.db.execute(
            select(MetricEmbedding).where(
                MetricEmbedding.metric_def_id == metric_def_id
            )
        )
        embedding = result.scalar_one_or_none()

        if embedding:
            await self.db.delete(embedding)
            logger.info(
                "metric_embedding_deleted",
                extra={"metric_def_id": str(metric_def_id)},
            )
            return True
        return False

    async def get_embedding_stats(self) -> dict[str, Any]:
        """
        Get statistics about the embedding index.

        Returns:
            Dict with counts and coverage statistics
        """
        # Total APPROVED metrics
        result = await self.db.execute(
            select(MetricDef.id).where(MetricDef.moderation_status == "APPROVED")
        )
        total_approved = len(result.all())

        # Total embeddings
        result = await self.db.execute(select(MetricEmbedding.id))
        total_embeddings = len(result.all())

        # Metrics missing embeddings
        missing = total_approved - total_embeddings

        return {
            "total_approved_metrics": total_approved,
            "total_embeddings": total_embeddings,
            "missing_embeddings": max(0, missing),
            "coverage_percent": round(
                (total_embeddings / total_approved * 100) if total_approved > 0 else 0,
                2,
            ),
            "model": settings.embedding_model,
            "dimensions": settings.embedding_dimensions,
        }

    async def close(self) -> None:
        """Close client resources if we own them."""
        if self._owns_client and self._client is not None:
            await self._client.close()
            self._client = None
