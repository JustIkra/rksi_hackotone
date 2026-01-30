"""
Semantic deduplication service for extracted metrics.

Provides pre-processing deduplication of semantically identical metric labels
before RAG mapping, reducing duplicate metric creation.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.openrouter import OpenRouterClient
from app.core.config import settings
from app.services.embedding import EmbeddingService

logger = logging.getLogger(__name__)


class SemanticDeduplicationService:
    """
    Service for deduplicating semantically identical metric items.

    Groups items with similar labels using embedding similarity,
    keeping only the item with the highest value in each group.
    This prevents duplicate metrics like "Творчество" and "Творческое мышление"
    from being processed separately.
    """

    def __init__(
        self,
        db: AsyncSession,
        client: OpenRouterClient | None = None,
        threshold: float | None = None,
    ):
        """
        Initialize deduplication service.

        Args:
            db: Async database session
            client: Optional OpenRouter client (creates default if not provided)
            threshold: Similarity threshold for grouping (default from config)
        """
        self.db = db
        self._embedding_service = EmbeddingService(db, client=client)
        self.threshold = threshold if threshold is not None else settings.metric_dedup_threshold

    async def deduplicate_items(
        self,
        items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Group semantically identical items and keep best from each group.

        Workflow:
        1. Generate embeddings for all labels in a single batch call
        2. Compute pairwise similarity matrix
        3. Group items with similarity >= threshold using union-find
        4. From each group, keep item with highest numeric value

        Args:
            items: List of dicts with keys: label, value, quotes, page_numbers

        Returns:
            Deduplicated list of items
        """
        if len(items) <= 1:
            return items

        labels = [item["label"] for item in items]

        # Generate embeddings for all labels in batch
        try:
            embeddings = await self._embedding_service.generate_embeddings(labels)
        except Exception as e:
            logger.warning(
                "dedup_embedding_failed",
                extra={"error": str(e), "item_count": len(items)},
            )
            # On failure, return original items unchanged
            return items

        # Build similarity groups using union-find
        n = len(items)
        parent = list(range(n))

        def find(x: int) -> int:
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(x: int, y: int) -> None:
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        # Compute pairwise cosine similarity and group similar items
        for i in range(n):
            for j in range(i + 1, n):
                similarity = self._cosine_similarity(embeddings[i], embeddings[j])
                if similarity >= self.threshold:
                    union(i, j)
                    logger.debug(
                        "dedup_similar_labels",
                        extra={
                            "label_a": labels[i],
                            "label_b": labels[j],
                            "similarity": round(similarity, 4),
                        },
                    )

        # Group items by their root parent
        groups: dict[int, list[int]] = {}
        for i in range(n):
            root = find(i)
            if root not in groups:
                groups[root] = []
            groups[root].append(i)

        # Select best item from each group (highest numeric value)
        result: list[dict[str, Any]] = []
        for indices in groups.values():
            if len(indices) == 1:
                result.append(items[indices[0]])
            else:
                # Multiple items in group - pick the one with highest value
                best_idx = self._select_best_item(items, indices)
                best_item = items[best_idx]

                # Log deduplication
                removed_labels = [items[i]["label"] for i in indices if i != best_idx]
                logger.info(
                    "dedup_merged_items",
                    extra={
                        "kept_label": best_item["label"],
                        "kept_value": best_item["value"],
                        "removed_labels": removed_labels,
                        "group_size": len(indices),
                    },
                )
                result.append(best_item)

        logger.info(
            "dedup_completed",
            extra={
                "input_count": len(items),
                "output_count": len(result),
                "removed_count": len(items) - len(result),
            },
        )

        return result

    def _cosine_similarity(self, vec_a: list[float], vec_b: list[float]) -> float:
        """
        Compute cosine similarity between two vectors.

        Args:
            vec_a: First embedding vector
            vec_b: Second embedding vector

        Returns:
            Cosine similarity in range [-1, 1], typically [0, 1] for embeddings
        """
        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = sum(a * a for a in vec_a) ** 0.5
        norm_b = sum(b * b for b in vec_b) ** 0.5

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)

    def _select_best_item(
        self,
        items: list[dict[str, Any]],
        indices: list[int],
    ) -> int:
        """
        Select the best item from a group of similar items.

        Selection criteria (in order):
        1. Highest numeric value
        2. Shortest label (more canonical)

        Args:
            items: All items list
            indices: Indices of items in this group

        Returns:
            Index of the best item
        """
        best_idx = indices[0]
        best_value = self._parse_numeric_value(items[best_idx]["value"])

        for idx in indices[1:]:
            value = self._parse_numeric_value(items[idx]["value"])

            # Prefer higher value
            if value > best_value:
                best_idx = idx
                best_value = value
            elif value == best_value:
                # Tie-break: prefer shorter label (more canonical)
                if len(items[idx]["label"]) < len(items[best_idx]["label"]):
                    best_idx = idx

        return best_idx

    def _parse_numeric_value(self, value_str: str) -> float:
        """
        Parse value string to float for comparison.

        Args:
            value_str: Value string (e.g., "7.5", "8,0")

        Returns:
            Parsed float value, or -inf if parsing fails
        """
        try:
            normalized = value_str.replace(",", ".").strip()
            return float(normalized)
        except (ValueError, AttributeError):
            return float("-inf")

    async def close(self) -> None:
        """Close embedding service resources."""
        await self._embedding_service.close()
