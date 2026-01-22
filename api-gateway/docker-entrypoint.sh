#!/usr/bin/env sh
set -eu

echo "=== Bootstrapping API service ==="

echo "Checking database state..."
# Detect broken state: alembic_version exists but core tables don't
# This can happen if migrations were interrupted or volume was corrupted
if python -c "
import sys
from sqlalchemy import create_engine, text
from app.core.config import settings

dsn = str(settings.POSTGRES_DSN).replace('+asyncpg', '')
engine = create_engine(dsn)
with engine.connect() as conn:
    # Check if alembic_version table exists and has records
    result = conn.execute(text(\"\"\"
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'alembic_version'
        )
    \"\"\"))
    has_alembic = result.scalar()

    if has_alembic:
        result = conn.execute(text('SELECT COUNT(*) FROM alembic_version'))
        version_count = result.scalar()

        # Check if 'user' table exists (core table created in first migration)
        result = conn.execute(text(\"\"\"
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'user'
            )
        \"\"\"))
        has_user_table = result.scalar()

        if version_count > 0 and not has_user_table:
            print('BROKEN_STATE')
            sys.exit(0)

    print('OK')
" 2>/dev/null | grep -q "BROKEN_STATE"; then
    echo "WARNING: Detected broken database state (alembic_version exists but tables missing)"
    echo "Resetting alembic_version to allow fresh migration..."
    python -c "
from sqlalchemy import create_engine, text
from app.core.config import settings
dsn = str(settings.POSTGRES_DSN).replace('+asyncpg', '')
engine = create_engine(dsn)
with engine.connect() as conn:
    conn.execute(text('DELETE FROM alembic_version'))
    conn.commit()
print('alembic_version reset successfully')
"
fi

echo "Applying database migrations..."
# Use 'heads' to handle multiple head revisions (merge migrations)
if ! alembic upgrade heads; then
    echo "ERROR: Failed to apply database migrations!" >&2
    exit 1
fi
echo "Database migrations applied successfully."

echo "Creating default admin user..."
python -c "
import asyncio
import uuid
from datetime import UTC, datetime
from app.db.models import User
from app.db.session import AsyncSessionLocal
from app.services.auth import get_user_by_email, hash_password

async def create_admin():
    email = 'admin@test.com'
    password = 'admin123'

    async with AsyncSessionLocal() as session:
        existing = await get_user_by_email(session, email)
        if existing:
            print(f'Admin user {email} already exists')
            return

        user = User(
            id=uuid.uuid4(),
            email=email,
            password_hash=hash_password(password),
            role='ADMIN',
            status='ACTIVE',
            approved_at=datetime.now(UTC),
        )
        session.add(user)
        await session.commit()
        print(f'Created admin user: {email}')

asyncio.run(create_admin())
" || echo "WARNING: Failed to create default admin user (may already exist)" >&2

echo "Starting application..."
exec python main.py
