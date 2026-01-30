#!/usr/bin/env python3
"""
Script to find and merge duplicate metrics in the database.

This script:
1. Finds duplicate metrics using embedding similarity
2. Proposes which metric should be canonical
3. Optionally executes the merge using CanonicalMetricService

Usage:
    # Dry run (default) - shows what would be merged
    python scripts/migrate_duplicate_metrics.py --dry-run

    # Execute the migration
    python scripts/migrate_duplicate_metrics.py --execute

    # Custom similarity threshold
    python scripts/migrate_duplicate_metrics.py --threshold 0.95 --execute
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

# Add api-gateway to path for imports
api_gateway_dir = Path(__file__).parent.parent
sys.path.insert(0, str(api_gateway_dir))

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.models import ExtractedMetric, MetricDef, MetricEmbedding, ParticipantMetric
from app.services.canonical_metric import CanonicalMetricService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def get_db_session() -> AsyncSession:
    """Create an async database session."""
    engine = create_async_engine(settings.postgres_dsn, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return async_session()


async def find_duplicates(
    db: AsyncSession,
    threshold: float = 0.90,
) -> list[tuple[str, str, float]]:
    """
    Find pairs of duplicate metrics using embedding similarity.

    Args:
        db: Database session
        threshold: Similarity threshold for considering duplicates

    Returns:
        List of tuples (code1, code2, similarity) where similarity >= threshold
    """
    # Get all metrics with embeddings
    result = await db.execute(
        select(
            MetricDef.code,
            MetricEmbedding.embedding,
        )
        .join(MetricEmbedding, MetricEmbedding.metric_def_id == MetricDef.id)
        .where(MetricDef.moderation_status == "APPROVED")
        .where(MetricDef.active == True)  # noqa: E712
        .where(MetricDef.canonical_metric_id.is_(None))  # Not already an alias
    )
    metrics = result.all()

    logger.info(f"Loaded {len(metrics)} metrics with embeddings")

    if len(metrics) < 2:
        return []

    # Compute pairwise similarities
    duplicates: list[tuple[str, str, float]] = []

    for i, (code1, emb1) in enumerate(metrics):
        for j, (code2, emb2) in enumerate(metrics[i + 1 :], start=i + 1):
            similarity = cosine_similarity(emb1, emb2)
            if similarity >= threshold:
                duplicates.append((code1, code2, round(similarity, 4)))

    # Sort by similarity descending
    duplicates.sort(key=lambda x: x[2], reverse=True)

    logger.info(f"Found {len(duplicates)} duplicate pairs with similarity >= {threshold}")

    return duplicates


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = sum(a * a for a in vec_a) ** 0.5
    norm_b = sum(b * b for b in vec_b) ** 0.5

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


async def get_metric_usage_stats(db: AsyncSession, code: str) -> dict[str, int]:
    """
    Get usage statistics for a metric.

    Returns:
        Dict with participant_metric_count, extracted_metric_count
    """
    # Count ParticipantMetric records
    result = await db.execute(
        select(func.count()).where(ParticipantMetric.metric_code == code)
    )
    pm_count = result.scalar() or 0

    # Count ExtractedMetric records
    result = await db.execute(
        select(MetricDef.id).where(MetricDef.code == code)
    )
    metric_id = result.scalar_one_or_none()

    em_count = 0
    if metric_id:
        result = await db.execute(
            select(func.count()).where(ExtractedMetric.metric_def_id == metric_id)
        )
        em_count = result.scalar() or 0

    return {
        "participant_metric_count": pm_count,
        "extracted_metric_count": em_count,
    }


async def get_metric_info(db: AsyncSession, code: str) -> dict[str, Any]:
    """Get full metric info for display."""
    result = await db.execute(
        select(MetricDef).where(MetricDef.code == code)
    )
    metric = result.scalar_one_or_none()

    if not metric:
        return {"code": code, "error": "not found"}

    stats = await get_metric_usage_stats(db, code)

    return {
        "code": metric.code,
        "name": metric.name,
        "name_ru": metric.name_ru,
        "created_at": str(metric.created_at) if hasattr(metric, "created_at") else "N/A",
        **stats,
    }


async def propose_canonical(
    db: AsyncSession,
    duplicates: list[tuple[str, str, float]],
) -> list[dict[str, Any]]:
    """
    Propose which metric should be canonical for each duplicate pair.

    Selection criteria (in order):
    1. More ParticipantMetric records
    2. More ExtractedMetric records
    3. Shorter code (more canonical-looking)

    Args:
        db: Database session
        duplicates: List of (code1, code2, similarity) tuples

    Returns:
        List of proposals: {alias_code, canonical_code, similarity, reason, stats}
    """
    proposals: list[dict[str, Any]] = []

    # Track already processed codes to avoid conflicts
    processed: set[str] = set()

    for code1, code2, similarity in duplicates:
        # Skip if either code already processed
        if code1 in processed or code2 in processed:
            logger.debug(f"Skipping {code1} <-> {code2}: one already processed")
            continue

        stats1 = await get_metric_usage_stats(db, code1)
        stats2 = await get_metric_usage_stats(db, code2)

        # Decision logic
        canonical_code, alias_code, reason = _choose_canonical(
            code1, stats1, code2, stats2
        )

        proposals.append({
            "alias_code": alias_code,
            "canonical_code": canonical_code,
            "similarity": similarity,
            "reason": reason,
            "alias_stats": stats1 if alias_code == code1 else stats2,
            "canonical_stats": stats1 if canonical_code == code1 else stats2,
        })

        processed.add(code1)
        processed.add(code2)

    return proposals


def _choose_canonical(
    code1: str,
    stats1: dict[str, int],
    code2: str,
    stats2: dict[str, int],
) -> tuple[str, str, str]:
    """
    Choose which metric should be canonical.

    Returns:
        (canonical_code, alias_code, reason)
    """
    pm1 = stats1["participant_metric_count"]
    pm2 = stats2["participant_metric_count"]

    if pm1 > pm2:
        return code1, code2, f"More participant metrics ({pm1} vs {pm2})"
    if pm2 > pm1:
        return code2, code1, f"More participant metrics ({pm2} vs {pm1})"

    em1 = stats1["extracted_metric_count"]
    em2 = stats2["extracted_metric_count"]

    if em1 > em2:
        return code1, code2, f"More extracted metrics ({em1} vs {em2})"
    if em2 > em1:
        return code2, code1, f"More extracted metrics ({em2} vs {em1})"

    # Tie: prefer shorter code
    if len(code1) <= len(code2):
        return code1, code2, f"Shorter code ({len(code1)} vs {len(code2)})"
    return code2, code1, f"Shorter code ({len(code2)} vs {len(code1)})"


async def execute_migration(
    db: AsyncSession,
    proposals: list[dict[str, Any]],
    dry_run: bool = True,
) -> dict[str, Any]:
    """
    Execute the migration of duplicates to canonical metrics.

    Args:
        db: Database session
        proposals: List of proposals from propose_canonical
        dry_run: If True, only print what would be done

    Returns:
        Summary statistics
    """
    service = CanonicalMetricService(db)

    results = {
        "total_proposals": len(proposals),
        "merged": 0,
        "errors": 0,
        "details": [],
    }

    for proposal in proposals:
        alias_code = proposal["alias_code"]
        canonical_code = proposal["canonical_code"]

        print(f"\n{'=' * 60}")
        print(f"Merge: {alias_code} -> {canonical_code}")
        print(f"  Similarity: {proposal['similarity']}")
        print(f"  Reason: {proposal['reason']}")
        print(f"  Alias stats: {proposal['alias_stats']}")
        print(f"  Canonical stats: {proposal['canonical_stats']}")

        if dry_run:
            print("  [DRY RUN] Would merge")
            results["details"].append({
                "alias_code": alias_code,
                "canonical_code": canonical_code,
                "status": "dry_run",
            })
        else:
            try:
                merge_stats = await service.merge_metrics(alias_code, canonical_code)
                print(f"  [MERGED] {merge_stats}")
                results["merged"] += 1
                results["details"].append({
                    "alias_code": alias_code,
                    "canonical_code": canonical_code,
                    "status": "merged",
                    "stats": merge_stats,
                })
            except Exception as e:
                print(f"  [ERROR] {e}")
                results["errors"] += 1
                results["details"].append({
                    "alias_code": alias_code,
                    "canonical_code": canonical_code,
                    "status": "error",
                    "error": str(e),
                })

    return results


async def main():
    parser = argparse.ArgumentParser(
        description="Find and merge duplicate metrics using embedding similarity"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.90,
        help="Similarity threshold for considering duplicates (default: 0.90)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Show what would be done without making changes (default)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the migration (overrides --dry-run)",
    )

    args = parser.parse_args()
    dry_run = not args.execute

    print(f"Duplicate Metric Migration")
    print(f"{'=' * 60}")
    print(f"Threshold: {args.threshold}")
    print(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    print(f"{'=' * 60}\n")

    async with await get_db_session() as db:
        # Step 1: Find duplicates
        print("Step 1: Finding duplicate metrics...")
        duplicates = await find_duplicates(db, threshold=args.threshold)

        if not duplicates:
            print("No duplicates found!")
            return

        print(f"\nFound {len(duplicates)} duplicate pairs:\n")
        for code1, code2, sim in duplicates[:20]:  # Show first 20
            info1 = await get_metric_info(db, code1)
            info2 = await get_metric_info(db, code2)
            print(f"  {code1} <-> {code2} (sim: {sim})")
            print(f"    {code1}: {info1.get('name_ru', info1.get('name', 'N/A'))}")
            print(f"    {code2}: {info2.get('name_ru', info2.get('name', 'N/A'))}")

        if len(duplicates) > 20:
            print(f"  ... and {len(duplicates) - 20} more pairs")

        # Step 2: Propose canonical
        print("\nStep 2: Proposing canonical metrics...")
        proposals = await propose_canonical(db, duplicates)

        print(f"\nGenerated {len(proposals)} merge proposals")

        # Step 3: Execute or dry-run
        print(f"\nStep 3: {'Executing' if not dry_run else 'Dry run'} migration...")
        results = await execute_migration(db, proposals, dry_run=dry_run)

        # Summary
        print(f"\n{'=' * 60}")
        print("Summary:")
        print(f"  Total proposals: {results['total_proposals']}")
        if dry_run:
            print(f"  Would merge: {results['total_proposals']} pairs")
            print("\nTo execute, run with --execute flag")
        else:
            print(f"  Merged: {results['merged']}")
            print(f"  Errors: {results['errors']}")


if __name__ == "__main__":
    asyncio.run(main())
