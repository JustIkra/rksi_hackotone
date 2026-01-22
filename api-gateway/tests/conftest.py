"""
Pytest configuration and fixtures for api-gateway tests.

Provides:
- Async test client for FastAPI
- Test database session with transaction rollback
- User fixtures (admin, active user, pending user)
- Authentication helpers
"""

import os
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import User
from app.db.session import get_db
from app.services.auth import create_access_token, hash_password

# Test database URL - use POSTGRES_DSN_TEST if set, otherwise derive from settings
# This allows running tests against a different database instance
#
# IMPORTANT: If running tests locally and you have both local PostgreSQL and Docker PostgreSQL
# on port 5432, you need to either:
# 1. Set POSTGRES_DSN_TEST to point to the correct instance, e.g.:
#    export POSTGRES_DSN_TEST="postgresql+asyncpg://app:app@127.0.0.1:5432/app?ssl=disable"
# 2. Stop your local PostgreSQL: brew services stop postgresql (macOS)
# 3. Run tests inside Docker: docker exec -it tsmuk-app pytest tests/test_auth.py
#
TEST_DATABASE_URL = os.environ.get("POSTGRES_DSN_TEST")
if not TEST_DATABASE_URL:
    # Check if we're running inside Docker by looking for /.dockerenv
    is_docker = os.path.exists("/.dockerenv")

    if is_docker:
        # Inside Docker, use the original DSN with 'postgres' host
        TEST_DATABASE_URL = settings.postgres_dsn
    else:
        # Outside Docker (local dev), replace 'postgres' host with 127.0.0.1
        # Note: 'localhost' may resolve to ::1 (IPv6) first, which might connect to local PostgreSQL
        TEST_DATABASE_URL = settings.postgres_dsn.replace("@postgres:", "@127.0.0.1:")

    # Disable SSL for testing
    if "?" not in TEST_DATABASE_URL:
        TEST_DATABASE_URL += "?ssl=disable"
    elif "ssl=" not in TEST_DATABASE_URL:
        TEST_DATABASE_URL += "&ssl=disable"


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Create a test database session with automatic rollback.

    Each test runs in its own transaction that is rolled back after the test,
    ensuring test isolation without requiring database cleanup.
    """
    # Create engine for this test
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
    )

    # Create session factory bound to this engine
    TestAsyncSessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with engine.connect() as connection:
        # Begin a non-ORM transaction
        transaction = await connection.begin()

        # Bind an individual session to the connection
        async_session = TestAsyncSessionLocal(bind=connection)

        # Begin a nested transaction (using SAVEPOINT)
        nested = await connection.begin_nested()

        # If the application code calls session.commit, it will end the nested
        # transaction. We need to start a new one when that happens.
        @event.listens_for(async_session.sync_session, "after_transaction_end")
        def end_savepoint(session: Session, transaction_obj: Any) -> None:
            nonlocal nested
            if not nested.is_active:
                nested = connection.sync_connection.begin_nested()  # type: ignore

        try:
            yield async_session
        finally:
            await async_session.close()
            await transaction.rollback()

    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Create an async HTTP test client with database dependency override.

    The client uses the test database session, ensuring all requests
    use the same transaction that will be rolled back.
    """
    from main import app

    # Override the get_db dependency to use our test session
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    # Clean up override
    app.dependency_overrides.clear()


# User Fixtures

@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """
    Create an ACTIVE admin user for testing.

    Returns:
        User with role=ADMIN, status=ACTIVE
    """
    user = User(
        id=uuid.uuid4(),
        email="admin@test.com",
        password_hash=hash_password("AdminPass123"),
        full_name="Test Admin",
        role="ADMIN",
        status="ACTIVE",
        created_at=datetime.now(UTC),
        approved_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def active_user(db_session: AsyncSession) -> User:
    """
    Create an ACTIVE regular user for testing.

    Returns:
        User with role=USER, status=ACTIVE
    """
    user = User(
        id=uuid.uuid4(),
        email="user@test.com",
        password_hash=hash_password("UserPass123"),
        full_name="Test User",
        role="USER",
        status="ACTIVE",
        created_at=datetime.now(UTC),
        approved_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def pending_user(db_session: AsyncSession) -> User:
    """
    Create a PENDING user for testing.

    Returns:
        User with role=USER, status=PENDING
    """
    user = User(
        id=uuid.uuid4(),
        email="pending@test.com",
        password_hash=hash_password("PendingPass123"),
        full_name="Pending User",
        role="USER",
        status="PENDING",
        created_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# Authentication Helpers

def get_auth_cookie(user: User) -> dict[str, str]:
    """
    Generate authentication cookie for a user.

    Args:
        user: User to authenticate as

    Returns:
        Cookie dict for use in test client requests
    """
    token = create_access_token(user.id, user.email, user.role)
    return {"access_token": token}


def get_auth_header(user: User) -> dict[str, str]:
    """
    Generate Authorization header for a user.

    Args:
        user: User to authenticate as

    Returns:
        Headers dict with Bearer token
    """
    token = create_access_token(user.id, user.email, user.role)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def admin_client(client: AsyncClient, db_session: AsyncSession) -> AsyncClient:
    """
    Create a test client authenticated as admin.

    Sets the access_token cookie for all requests.
    Note: Creates admin user inline to share db_session with client.
    """
    # Create admin user in the same session used by client
    admin_user = User(
        id=uuid.uuid4(),
        email="admin_client@test.com",  # Different email to avoid conflicts
        password_hash=hash_password("AdminPass123"),
        full_name="Test Admin",
        role="ADMIN",
        status="ACTIVE",
        created_at=datetime.now(UTC),
        approved_at=datetime.now(UTC),
    )
    db_session.add(admin_user)
    await db_session.commit()
    await db_session.refresh(admin_user)

    client.cookies.set("access_token", create_access_token(
        admin_user.id, admin_user.email, admin_user.role
    ))
    return client


@pytest_asyncio.fixture
async def user_client(client: AsyncClient, db_session: AsyncSession) -> AsyncClient:
    """
    Create a test client authenticated as regular user.

    Sets the access_token cookie for all requests.
    Note: Creates user inline to share db_session with client.
    """
    # Create active user in the same session used by client
    active_user = User(
        id=uuid.uuid4(),
        email="user_client@test.com",  # Different email to avoid conflicts
        password_hash=hash_password("UserPass123"),
        full_name="Test User",
        role="USER",
        status="ACTIVE",
        created_at=datetime.now(UTC),
        approved_at=datetime.now(UTC),
    )
    db_session.add(active_user)
    await db_session.commit()
    await db_session.refresh(active_user)

    client.cookies.set("access_token", create_access_token(
        active_user.id, active_user.email, active_user.role
    ))
    return client


@pytest_asyncio.fixture
async def admin_only_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Create an independent test client authenticated as admin.

    Unlike admin_client, this fixture creates its own AsyncClient instance,
    allowing it to be used alongside user_client in the same test without
    cookie conflicts.
    """
    from main import app

    # Override the get_db dependency to use our test session
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # Create admin user
    admin_user = User(
        id=uuid.uuid4(),
        email=f"admin_only_{uuid.uuid4().hex[:8]}@test.com",
        password_hash=hash_password("AdminPass123"),
        full_name="Test Admin Only",
        role="ADMIN",
        status="ACTIVE",
        created_at=datetime.now(UTC),
        approved_at=datetime.now(UTC),
    )
    db_session.add(admin_user)
    await db_session.commit()
    await db_session.refresh(admin_user)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        ac.cookies.set("access_token", create_access_token(
            admin_user.id, admin_user.email, admin_user.role
        ))
        yield ac


@pytest_asyncio.fixture
async def user_only_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Create an independent test client authenticated as regular user.

    Unlike user_client, this fixture creates its own AsyncClient instance,
    allowing it to be used alongside admin_client in the same test without
    cookie conflicts.
    """
    from main import app

    # Override the get_db dependency to use our test session
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # Create user
    active_user = User(
        id=uuid.uuid4(),
        email=f"user_only_{uuid.uuid4().hex[:8]}@test.com",
        password_hash=hash_password("UserPass123"),
        full_name="Test User Only",
        role="USER",
        status="ACTIVE",
        created_at=datetime.now(UTC),
        approved_at=datetime.now(UTC),
    )
    db_session.add(active_user)
    await db_session.commit()
    await db_session.refresh(active_user)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        ac.cookies.set("access_token", create_access_token(
            active_user.id, active_user.email, active_user.role
        ))
        yield ac
