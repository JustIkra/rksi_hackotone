#!/usr/bin/env python3
"""
Add missing synonyms to metrics based on common short forms from reports.

Run: docker exec -w /app tsmuk-app python scripts/add_metric_synonyms.py
"""

import asyncio
import logging
import sys

sys.path.insert(0, "/app")

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.models import MetricDef, MetricSynonym
from app.services.embedding import EmbeddingService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mapping: metric_code -> list of synonyms to add
SYNONYMS_TO_ADD = {
    # From Biznes-Profil reports - short forms used in documents
    "motivatsiya_k_rukovodstvu": ["Руководство", "Мотивация руководства"],
    "potentsial_k_rukovodstvu": ["Потенциал руководства", "Управленческий потенциал"],
    "delovaya_kommunikatsiya": ["Связи", "Деловые связи", "Коммуникация"],
    "obschiy_intellekt": ["Общий балл интеллекта", "Интеллект", "IQ"],
    "liderstvo": ["Мотиватор", "Лидер"],
    "generator_idey": ["Творчество", "Креативность", "Творческое мышление"],
    "interes_k_protsessu": ["Интерес к процессу", "Процесс"],
    "sluzhenie_obschestvu": ["Служение обществу", "Помощь людям"],
    "organizatsiya_raboty": ["Организованность", "Организация"],
    "prinyatie_resheniy": ["Аналитик", "Решения", "Принятие решений"],
    "stressoustoychivost": ["Стрессоустойчивость", "Устойчивость к стрессу"],
    "konfliktnost": ["Конфликтность", "Конфликт"],
    "normativnost": ["Нормативность", "Моральность"],
    # Personality traits - paired metrics
    "zamknutost": ["Замкнутость", "Интроверсия"],
    "passivnost": ["Пассивность", "Активность"],
    "trevozhnost": ["Тревожность", "Тревога"],
    "senzitivnost": ["Сензитивность", "Чувствительность"],
}


async def add_synonyms():
    """Add synonyms to metrics and reindex embeddings."""
    engine = create_async_engine(settings.postgres_dsn)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        added_count = 0
        skipped_count = 0
        metrics_to_reindex = set()

        for metric_code, synonyms in SYNONYMS_TO_ADD.items():
            # Find metric
            result = await db.execute(
                select(MetricDef).where(MetricDef.code == metric_code)
            )
            metric = result.scalar_one_or_none()

            if not metric:
                logger.warning(f"Metric not found: {metric_code}")
                continue

            for synonym in synonyms:
                # Check if synonym already exists (case-insensitive)
                result = await db.execute(
                    select(MetricSynonym).where(
                        MetricSynonym.synonym.ilike(synonym)
                    )
                )
                existing = result.scalar_one_or_none()

                if existing:
                    logger.debug(f"Synonym already exists: {synonym}")
                    skipped_count += 1
                    continue

                # Add new synonym
                new_synonym = MetricSynonym(
                    metric_def_id=metric.id,
                    synonym=synonym,
                )
                db.add(new_synonym)
                logger.info(f"Added synonym: '{synonym}' -> {metric_code}")
                added_count += 1
                metrics_to_reindex.add(metric.id)

        await db.commit()
        logger.info(f"Added {added_count} synonyms, skipped {skipped_count} existing")

        # Reindex metrics with new synonyms
        if metrics_to_reindex:
            logger.info(f"Reindexing {len(metrics_to_reindex)} metrics...")
            embedding_service = EmbeddingService(db)
            try:
                for metric_id in metrics_to_reindex:
                    await embedding_service.index_metric(metric_id)
                    logger.info(f"Reindexed metric: {metric_id}")
                await db.commit()
            finally:
                await embedding_service.close()

            logger.info("Reindexing complete")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(add_synonyms())
