"""
RAG mapping service for label-to-metric_code resolution.

Provides semantic search with LLM-based decision making.
Uses EmbeddingService for vector similarity search and LLM for final decision.

The service flow:
1. Get candidates from RAG (embedding similarity search)
2. Optionally add YAML mapping as top candidate
3. Always use LLM to decide the best match from candidates

The service handles three mapping statuses:
- "mapped": Successfully matched to a metric code
- "ambiguous": LLM detected ambiguity between candidates
- "unknown": No suitable candidates found
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_factory import AIClient, create_ai_client
from app.core.config import settings
from app.services.embedding import EmbeddingService
from app.services.metric_mapping import get_metric_mapping_service
from app.services.metric_mapping_llm_decision import (
    decide_metric_mapping,
    decide_metric_mapping_batch,
)

logger = logging.getLogger(__name__)


def _norm(s: str) -> str:
    """
    Normalize text for comparison.

    Collapses whitespace (spaces, tabs, newlines) to single space,
    strips leading/trailing whitespace, and converts to Title Case.

    Title Case is used because indexed metric texts are stored in Title Case,
    and embedding similarity is significantly higher when query and indexed text
    have the same case (0.8 vs 0.42 for UPPERCASE).

    Args:
        s: Input string

    Returns:
        Normalized Title Case string
    """
    return re.sub(r"\s+", " ", s).strip().title()


class RagMappingService:
    """
    Service for mapping extracted labels to metric codes using RAG + LLM.

    Combines direct YAML lookup with semantic vector search,
    then uses LLM to make the final decision from candidates.
    """

    # Default configuration
    DEFAULT_TOP_K = 10
    DEFAULT_MIN_CONFIDENCE = 0.6

    def __init__(
        self,
        db: AsyncSession,
        embedding_service: EmbeddingService | None = None,
        ai_client: AIClient | None = None,
        top_k: int | None = None,
        min_confidence: float | None = None,
    ):
        """
        Initialize RAG mapping service.

        Args:
            db: Async database session
            embedding_service: Optional EmbeddingService instance
            ai_client: Optional AIClient instance for LLM decisions
            top_k: Number of candidates to retrieve (default 10)
            min_confidence: Minimum confidence for LLM decision (default 0.6)
        """
        self.db = db
        self._embedding_service = embedding_service
        self._ai_client = ai_client
        self.top_k = top_k or self.DEFAULT_TOP_K
        self.min_confidence = min_confidence or self.DEFAULT_MIN_CONFIDENCE

    def _get_embedding_service(self) -> EmbeddingService:
        """Get or create embedding service."""
        if self._embedding_service is None:
            self._embedding_service = EmbeddingService(self.db)
        return self._embedding_service

    def _get_ai_client(self) -> AIClient:
        """Get or create AI client for LLM decisions."""
        if self._ai_client is None:
            self._ai_client = create_ai_client()
        return self._ai_client

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

    async def map_label(self, label: str) -> dict[str, Any]:
        """
        Map a metric label to a metric code.

        Flow:
        1. Get candidates from RAG (all candidates, no threshold filtering)
        2. Optionally add YAML match as top candidate
        3. Always use LLM to decide the best match

        Args:
            label: Metric label extracted from document

        Returns:
            Dict with:
            - code: Matched metric code or None
            - status: "mapped", "ambiguous", or "unknown"
            - source: "llm" or None
            - similarity: Confidence score from LLM
            - candidates: Top candidates considered
            - llm_reason: Explanation from LLM
        """
        normalized_label = _norm(label)

        # Step 1: Get candidates from RAG with minimum threshold
        embedding_service = self._get_embedding_service()
        candidate_min_threshold = settings.rag_candidate_min_threshold
        auto_match_threshold = settings.rag_auto_match_threshold

        try:
            candidates = await embedding_service.find_similar(
                query_text=normalized_label,
                top_k=self.top_k,
                threshold=candidate_min_threshold,
            )
        except Exception as e:
            logger.error(
                "rag_search_failed",
                extra={"label": label, "error": str(e)},
            )
            candidates = []

        # Auto-match: if top candidate has very high similarity, skip LLM
        if candidates and candidates[0]["similarity"] >= auto_match_threshold:
            best = candidates[0]
            logger.info(
                "auto_match_high_similarity",
                extra={
                    "label": label,
                    "code": best["code"],
                    "similarity": best["similarity"],
                    "threshold": auto_match_threshold,
                },
            )
            return {
                "code": best["code"],
                "status": "mapped",
                "source": "auto",
                "similarity": best["similarity"],
                "candidates": candidates[:5],
                "llm_reason": f"Auto-matched with similarity {best['similarity']} >= {auto_match_threshold}",
            }

        # Step 2: Optionally add YAML match as top candidate
        yaml_code = self.try_yaml_mapping(label)
        if yaml_code:
            logger.debug(
                "yaml_mapping_found",
                extra={"label": label, "code": yaml_code},
            )
            # Insert YAML match at top with similarity=1.0
            candidates.insert(0, {
                "code": yaml_code,
                "similarity": 1.0,
                "name_ru": f"YAML: {yaml_code}",
                "indexed_text": f"Direct YAML mapping for {label}",
                "description": None,
            })

        if not candidates:
            logger.debug(
                "no_candidates_found",
                extra={"label": label, "normalized": normalized_label},
            )
            return {
                "code": None,
                "status": "unknown",
                "source": None,
                "similarity": None,
                "candidates": [],
                "llm_reason": "No candidates available",
            }

        # Step 3: Always use LLM to decide
        ai_client = self._get_ai_client()

        try:
            decision = await decide_metric_mapping(
                ai_client=ai_client,
                label=label,
                candidates=candidates,
                min_confidence=self.min_confidence,
            )
        except Exception as e:
            logger.error(
                "llm_decision_failed",
                extra={"label": label, "error": str(e)},
            )
            return {
                "code": None,
                "status": "unknown",
                "source": None,
                "similarity": None,
                "candidates": candidates[:5],
                "llm_reason": f"LLM decision error: {str(e)}",
            }

        logger.info(
            "metric_mapping_decision",
            extra={
                "label": label,
                "normalized_label": normalized_label,
                "candidates_count": len(candidates),
                "top_candidates": [
                    {"code": c["code"], "similarity": c["similarity"]}
                    for c in candidates[:3]
                ],
                "yaml_match": yaml_code,
                "llm_decision": decision["status"],
                "chosen_code": decision.get("code"),
                "confidence": decision.get("confidence"),
                "reason": (decision.get("reason") or "")[:100],
            },
        )

        # Transform result
        result = {
            "code": decision["code"],
            "status": decision["status"],
            "source": "llm" if decision["code"] else None,
            "similarity": decision.get("confidence"),
            "candidates": candidates[:5],
            "llm_reason": decision.get("reason"),
        }

        if decision["code"]:
            logger.debug(
                "llm_mapping_success",
                extra={
                    "label": label,
                    "code": decision["code"],
                    "confidence": decision.get("confidence"),
                    "reason": decision.get("reason"),
                },
            )

        return result

    async def map_labels_batch(self, labels: list[str]) -> list[dict[str, Any]]:
        """
        Map multiple labels to metric codes using batch embeddings and batch LLM decision.

        Optimizes API calls by:
        1. Generating embeddings for all labels in a single API call
        2. Running similarity search for each embedding (DB queries)
        3. Using batch LLM decision for all labels in a single API call

        Args:
            labels: List of metric labels

        Returns:
            List of result dicts (same format as map_label)
        """
        if not labels:
            return []

        # Normalize all labels
        normalized_labels = [_norm(label) for label in labels]

        # Step 1: Generate embeddings for all labels in one batch
        embedding_service = self._get_embedding_service()
        ai_client = self._get_ai_client()

        try:
            embeddings = await embedding_service.generate_embeddings(normalized_labels)
        except Exception as e:
            logger.error(
                "batch_embeddings_failed",
                extra={"labels_count": len(labels), "error": str(e)},
            )
            # Fallback to sequential processing
            results = []
            for label in labels:
                result = await self.map_label(label)
                result["label"] = label
                results.append(result)
            return results

        # Step 2: Find candidates for each embedding and prepare LLM items
        candidate_min_threshold = settings.rag_candidate_min_threshold
        auto_match_threshold = settings.rag_auto_match_threshold

        llm_items: list[dict[str, Any]] = []
        item_indices: list[int] = []  # Track which items need LLM decision
        results: list[dict[str, Any]] = [
            {
                "label": label,
                "code": None,
                "status": "unknown",
                "source": None,
                "similarity": None,
                "candidates": [],
                "llm_reason": "No candidates available",
            }
            for label in labels
        ]

        for i, (label, normalized_label, embedding) in enumerate(
            zip(labels, normalized_labels, embeddings)
        ):
            try:
                # Find similar using pre-computed embedding with minimum threshold
                candidates = await embedding_service.find_similar_by_embedding(
                    query_embedding=embedding,
                    top_k=self.top_k,
                    threshold=candidate_min_threshold,
                )
            except Exception as e:
                logger.error(
                    "rag_search_by_embedding_failed",
                    extra={"label": label, "error": str(e)},
                )
                candidates = []

            # Add YAML mapping if found
            yaml_code = self.try_yaml_mapping(label)
            if yaml_code:
                candidates.insert(0, {
                    "code": yaml_code,
                    "similarity": 1.0,
                    "name_ru": f"YAML: {yaml_code}",
                    "indexed_text": f"Direct YAML mapping for {label}",
                    "description": None,
                })

            if not candidates:
                continue

            # Auto-match: if top candidate has very high similarity, skip LLM
            if candidates[0]["similarity"] >= auto_match_threshold:
                best = candidates[0]
                logger.info(
                    "batch_auto_match_high_similarity",
                    extra={
                        "label": label,
                        "code": best["code"],
                        "similarity": best["similarity"],
                    },
                )
                results[i] = {
                    "label": label,
                    "code": best["code"],
                    "status": "mapped",
                    "source": "auto",
                    "similarity": best["similarity"],
                    "candidates": candidates[:5],
                    "llm_reason": f"Auto-matched with similarity {best['similarity']} >= {auto_match_threshold}",
                }
            else:
                # Need LLM decision
                llm_items.append({"label": label, "candidates": candidates})
                item_indices.append(i)
                results[i]["candidates"] = candidates[:5]

        # Step 3: Use batch LLM decision for all items with candidates
        if llm_items:
            try:
                decisions = await decide_metric_mapping_batch(
                    ai_client=ai_client,
                    items=llm_items,
                    min_confidence=self.min_confidence,
                )

                # Apply decisions to results
                for j, (idx, decision) in enumerate(zip(item_indices, decisions)):
                    results[idx]["code"] = decision["code"]
                    results[idx]["status"] = decision["status"]
                    results[idx]["source"] = "llm" if decision["code"] else None
                    results[idx]["similarity"] = decision.get("confidence")
                    results[idx]["llm_reason"] = decision.get("reason")

            except Exception as e:
                logger.error(
                    "batch_llm_decision_failed",
                    extra={"items_count": len(llm_items), "error": str(e)},
                )
                # Mark all items with candidates as unknown on error
                for idx in item_indices:
                    results[idx]["llm_reason"] = f"LLM decision error: {str(e)}"

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
                "batch_llm_items": len(llm_items),
            },
        )

        return results

    async def close(self) -> None:
        """Close service resources."""
        if self._embedding_service:
            await self._embedding_service.close()
            self._embedding_service = None
