"""
RAG mapping service for label-to-metric_code resolution.

Provides semantic search with progressive widening and ambiguity detection.
Uses EmbeddingService for vector similarity search and implements
a multi-step resolution strategy:

1. First try direct YAML mapping (MetricMappingService)
2. Fall back to RAG/vector search with threshold and ambiguity detection
3. Support progressive widening of search parameters

The service handles three mapping statuses:
- "mapped": Successfully matched to a metric code
- "ambiguous": Multiple candidates with similar scores (within delta)
- "unknown": No candidates above threshold
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.embedding import EmbeddingService
from app.services.metric_mapping import get_metric_mapping_service

logger = logging.getLogger(__name__)


def _norm(s: str) -> str:
    """
    Normalize text for comparison.

    Collapses whitespace (spaces, tabs, newlines) to single space,
    strips leading/trailing whitespace, and converts to uppercase.

    Args:
        s: Input string

    Returns:
        Normalized uppercase string
    """
    return re.sub(r"\s+", " ", s).strip().upper()


def _select_candidate(
    candidates: list[dict[str, Any]],
    threshold: float,
    ambiguity_delta: float,
) -> tuple[str | None, str]:
    """
    Select best candidate from similarity search results.

    Implements ambiguity detection: if the top two candidates are both
    above threshold and their similarity difference is within ambiguity_delta,
    the result is considered ambiguous.

    Args:
        candidates: List of candidate dicts with 'code' and 'similarity' keys
        threshold: Minimum similarity score to accept a match
        ambiguity_delta: Maximum difference between top two scores to be
                        considered ambiguous

    Returns:
        Tuple of (code, status) where:
        - code: The selected metric code or None
        - status: One of "mapped", "ambiguous", or "unknown"
    """
    if not candidates:
        return None, "unknown"

    # Sort by similarity descending
    ordered = sorted(
        candidates,
        key=lambda c: float(c.get("similarity", 0)),
        reverse=True
    )

    top1_similarity = float(ordered[0].get("similarity", 0))

    # Check if top candidate is above threshold
    if top1_similarity < threshold:
        return None, "unknown"

    # Check for ambiguity if we have multiple candidates
    if len(ordered) > 1:
        top2_similarity = float(ordered[1].get("similarity", 0))
        # Ambiguity: both above threshold and within delta
        if top2_similarity >= threshold and (top1_similarity - top2_similarity) <= ambiguity_delta:
            logger.debug(
                "ambiguous_candidates",
                extra={
                    "top1_code": ordered[0].get("code"),
                    "top1_similarity": top1_similarity,
                    "top2_code": ordered[1].get("code"),
                    "top2_similarity": top2_similarity,
                    "delta": top1_similarity - top2_similarity,
                    "ambiguity_delta": ambiguity_delta,
                },
            )
            return None, "ambiguous"

    # Clear winner
    code = ordered[0].get("code")
    return (str(code), "mapped") if code else (None, "unknown")


class RagMappingService:
    """
    Service for mapping extracted labels to metric codes using RAG.

    Combines direct YAML lookup with semantic vector search.
    Supports progressive widening of search parameters when initial
    searches fail to find matches.
    """

    # Default configuration for progressive widening
    DEFAULT_THRESHOLDS = [0.85, 0.80, 0.75]
    DEFAULT_TOP_K_VALUES = [5, 10, 20]
    DEFAULT_AMBIGUITY_DELTA = 0.02

    def __init__(
        self,
        db: AsyncSession,
        embedding_service: EmbeddingService | None = None,
        thresholds: list[float] | None = None,
        top_k_values: list[int] | None = None,
        ambiguity_delta: float | None = None,
    ):
        """
        Initialize RAG mapping service.

        Args:
            db: Async database session
            embedding_service: Optional EmbeddingService instance
            thresholds: List of similarity thresholds for progressive widening
            top_k_values: List of top_k values for progressive widening
            ambiguity_delta: Delta for ambiguity detection
        """
        self.db = db
        self._embedding_service = embedding_service
        self.thresholds = thresholds or self.DEFAULT_THRESHOLDS
        self.top_k_values = top_k_values or self.DEFAULT_TOP_K_VALUES
        self.ambiguity_delta = ambiguity_delta or self.DEFAULT_AMBIGUITY_DELTA

    def _get_embedding_service(self) -> EmbeddingService:
        """Get or create embedding service."""
        if self._embedding_service is None:
            self._embedding_service = EmbeddingService(self.db)
        return self._embedding_service

    def try_yaml_mapping(self, label: str) -> str | None:
        """
        Try to map label using YAML configuration.

        Args:
            label: Metric label from document

        Returns:
            Metric code if found in YAML mapping, None otherwise
        """
        try:
            mapping_service = get_metric_mapping_service()
            return mapping_service.get_metric_code(label)
        except Exception as e:
            logger.warning(
                "yaml_mapping_failed",
                extra={"label": label, "error": str(e)},
            )
            return None

    async def map_label(
        self,
        label: str,
        use_progressive_widening: bool = True,
    ) -> dict[str, Any]:
        """
        Map a metric label to a metric code.

        First tries direct YAML mapping, then falls back to RAG search
        with optional progressive widening.

        Args:
            label: Metric label extracted from document
            use_progressive_widening: Whether to try multiple threshold/top_k
                                     combinations

        Returns:
            Dict with:
            - code: Matched metric code or None
            - status: "mapped", "ambiguous", or "unknown"
            - source: "yaml", "rag", or None
            - similarity: Similarity score (for RAG matches)
            - candidates: Top candidates considered (for debugging)
        """
        normalized_label = _norm(label)

        # Step 1: Try YAML mapping
        yaml_code = self.try_yaml_mapping(label)
        if yaml_code:
            logger.debug(
                "yaml_mapping_success",
                extra={"label": label, "code": yaml_code},
            )
            return {
                "code": yaml_code,
                "status": "mapped",
                "source": "yaml",
                "similarity": 1.0,
                "candidates": [],
            }

        # Step 2: RAG search with progressive widening
        embedding_service = self._get_embedding_service()

        if use_progressive_widening:
            # Try progressively relaxed parameters
            for threshold in self.thresholds:
                for top_k in self.top_k_values:
                    result = await self._rag_search(
                        embedding_service,
                        normalized_label,
                        top_k=top_k,
                        threshold=threshold,
                    )
                    if result["status"] == "mapped":
                        return result
                    # If ambiguous, return immediately (don't widen further)
                    if result["status"] == "ambiguous":
                        return result
        else:
            # Single search with default parameters
            result = await self._rag_search(
                embedding_service,
                normalized_label,
                top_k=self.top_k_values[0],
                threshold=self.thresholds[0],
            )
            return result

        # No match found after all attempts
        logger.debug(
            "mapping_not_found",
            extra={"label": label, "normalized": normalized_label},
        )
        return {
            "code": None,
            "status": "unknown",
            "source": None,
            "similarity": None,
            "candidates": [],
        }

    async def _rag_search(
        self,
        embedding_service: EmbeddingService,
        query: str,
        top_k: int,
        threshold: float,
    ) -> dict[str, Any]:
        """
        Perform RAG search for metric matching.

        Args:
            embedding_service: EmbeddingService instance
            query: Normalized query text
            top_k: Number of candidates to retrieve
            threshold: Minimum similarity threshold

        Returns:
            Result dict with code, status, source, similarity, candidates
        """
        try:
            candidates = await embedding_service.find_similar(
                query_text=query,
                top_k=top_k,
                threshold=threshold,
            )
        except Exception as e:
            logger.error(
                "rag_search_failed",
                extra={"query": query, "error": str(e)},
            )
            return {
                "code": None,
                "status": "unknown",
                "source": None,
                "similarity": None,
                "candidates": [],
            }

        code, status = _select_candidate(
            candidates,
            threshold=threshold,
            ambiguity_delta=self.ambiguity_delta,
        )

        result = {
            "code": code,
            "status": status,
            "source": "rag" if code else None,
            "similarity": candidates[0]["similarity"] if candidates else None,
            "candidates": candidates[:3],  # Top 3 for debugging
        }

        if code:
            logger.debug(
                "rag_mapping_success",
                extra={
                    "query": query,
                    "code": code,
                    "similarity": result["similarity"],
                    "top_k": top_k,
                    "threshold": threshold,
                },
            )

        return result

    async def map_labels_batch(
        self,
        labels: list[str],
        use_progressive_widening: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Map multiple labels to metric codes.

        Args:
            labels: List of metric labels
            use_progressive_widening: Whether to use progressive widening

        Returns:
            List of result dicts (same format as map_label)
        """
        results = []
        for label in labels:
            result = await self.map_label(
                label,
                use_progressive_widening=use_progressive_widening,
            )
            result["label"] = label
            results.append(result)

        # Log summary
        mapped_count = sum(1 for r in results if r["status"] == "mapped")
        ambiguous_count = sum(1 for r in results if r["status"] == "ambiguous")
        unknown_count = sum(1 for r in results if r["status"] == "unknown")

        logger.info(
            "batch_mapping_completed",
            extra={
                "total": len(labels),
                "mapped": mapped_count,
                "ambiguous": ambiguous_count,
                "unknown": unknown_count,
            },
        )

        return results

    async def close(self) -> None:
        """Close service resources."""
        if self._embedding_service:
            await self._embedding_service.close()
            self._embedding_service = None
