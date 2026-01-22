#!/usr/bin/env sh
set -eu

echo "=== Bootstrapping Celery worker ==="

# Initialize metric definitions if database is empty
echo "Checking metric definitions in database..."
python -c "
import asyncio
import sys
from app.db.session import AsyncSessionLocal
from app.repositories.metric import MetricDefRepository

async def check_metrics():
    async with AsyncSessionLocal() as db:
        repo = MetricDefRepository(db)
        metrics = await repo.list_all(active_only=False)
        print(f'Found {len(metrics)} metric definitions in database')
        if len(metrics) == 0:
            print('WARNING: No metric definitions found. Wait for auto-seed on app startup.')

asyncio.run(check_metrics())
" || echo "WARNING: Failed to check metric definitions (database may not be ready yet)"

echo "Starting Celery worker for extraction queue..."
exec celery -A app.core.celery_app.celery_app worker -l info -Q extraction

