"""
Celery-safe database session factory.

Creates engine/session lazily to avoid asyncio event loop conflicts.
Use this in Celery tasks instead of AsyncSessionLocal from session.py.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


def get_celery_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    Create a new async session factory for use in Celery tasks.

    This creates a fresh engine in the current event loop context,
    avoiding "Future attached to a different loop" errors.

    Usage in Celery task:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            AsyncSessionLocal = get_celery_session_factory()
            async with AsyncSessionLocal() as db:
                # use db...
        finally:
            loop.close()

    Returns:
        async_sessionmaker bound to a fresh engine
    """
    engine = create_async_engine(
        settings.postgres_dsn,
        echo=False,  # No SQL logging in Celery workers
        pool_pre_ping=True,
        pool_size=5,  # Smaller pool for Celery workers
        max_overflow=10,
    )

    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
