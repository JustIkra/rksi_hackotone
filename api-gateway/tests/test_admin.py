"""
Comprehensive tests for admin router endpoints.

Tests admin functionality including:
- User approval workflow (PENDING -> ACTIVE)
- Admin role management (grant/revoke)
- User listing and filtering
- User deletion
- Role-based access control (403 for non-admins)
- Edge cases (self-operations, invalid states)
"""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.services.auth import create_access_token, hash_password


# --- Test Fixtures ---

@pytest.fixture
async def disabled_user(db_session: AsyncSession) -> User:
    """
    Create a DISABLED user for testing edge cases.

    Returns:
        User with status=DISABLED
    """
    user = User(
        id=uuid.uuid4(),
        email="disabled@test.local",
        password_hash=hash_password("DisabledPass123"),
        full_name="Disabled User",
        role="USER",
        status="DISABLED",
        created_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def second_admin(db_session: AsyncSession) -> User:
    """
    Create a second admin user for testing admin role operations.

    Returns:
        User with role=ADMIN, status=ACTIVE
    """
    user = User(
        id=uuid.uuid4(),
        email="admin2@test.local",
        password_hash=hash_password("Admin2Pass123"),
        full_name="Second Admin",
        role="ADMIN",
        status="ACTIVE",
        created_at=datetime.now(UTC),
        approved_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# --- List All Users ---

@pytest.mark.asyncio
async def test_admin_list_all_users(
    admin_client: AsyncClient,
    admin_user: User,
    active_user: User,
    pending_user: User,
):
    """
    Admin can list all users regardless of status or role.

    Expected:
    - 200 OK
    - Returns list including admin, active, and pending users
    - Users ordered by created_at
    """
    response = await admin_client.get("/api/admin/users")

    assert response.status_code == 200
    data = response.json()

    assert isinstance(data, list)
    assert len(data) >= 3

    # Check that all test users are present
    emails = {u["email"] for u in data}
    assert admin_user.email in emails
    assert active_user.email in emails
    assert pending_user.email in emails


@pytest.mark.asyncio
async def test_list_all_users_non_admin_forbidden(
    user_client: AsyncClient,
):
    """
    Non-admin users cannot list all users.

    Expected:
    - 403 Forbidden
    - Error message about admin privileges
    """
    response = await user_client.get("/api/admin/users")

    assert response.status_code == 403
    assert "admin" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_list_all_users_unauthenticated(
    client: AsyncClient,
):
    """
    Unauthenticated requests cannot list users.

    Expected:
    - 401 Unauthorized
    """
    response = await client.get("/api/admin/users")

    assert response.status_code == 401


# --- List Pending Users ---

@pytest.mark.asyncio
async def test_admin_list_pending_users(
    admin_client: AsyncClient,
    pending_user: User,
    active_user: User,
):
    """
    Admin can list all pending users awaiting approval.

    Expected:
    - 200 OK
    - Returns only users with status=PENDING
    - Active users excluded from results
    """
    response = await admin_client.get("/api/admin/pending-users")

    assert response.status_code == 200
    data = response.json()

    assert isinstance(data, list)

    # All returned users should have PENDING status
    for user in data:
        assert user["status"] == "PENDING"

    # Pending user should be in the list
    pending_emails = {u["email"] for u in data}
    assert pending_user.email in pending_emails

    # Active user should NOT be in the list
    assert active_user.email not in pending_emails


@pytest.mark.asyncio
async def test_list_pending_users_non_admin_forbidden(
    user_client: AsyncClient,
):
    """
    Non-admin users cannot list pending users.

    Expected:
    - 403 Forbidden
    """
    response = await user_client.get("/api/admin/pending-users")

    assert response.status_code == 403
    assert "admin" in response.json()["detail"].lower()


# --- Approve User ---

@pytest.mark.asyncio
async def test_admin_approve_pending_user(
    admin_client: AsyncClient,
    pending_user: User,
    db_session: AsyncSession,
):
    """
    Admin can approve a pending user, changing status to ACTIVE.

    Flow:
    1. User registers -> status=PENDING
    2. Admin approves user
    3. User status changes to ACTIVE
    4. approved_at timestamp is set

    Expected:
    - 200 OK
    - User status is ACTIVE
    - approved_at is set
    """
    response = await admin_client.post(f"/api/admin/approve/{pending_user.id}")

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == str(pending_user.id)
    assert data["email"] == pending_user.email
    assert data["status"] == "ACTIVE"
    assert data["approved_at"] is not None

    # Verify database state
    await db_session.refresh(pending_user)
    assert pending_user.status == "ACTIVE"
    assert pending_user.approved_at is not None


@pytest.mark.asyncio
async def test_approve_already_active_user_error(
    admin_client: AsyncClient,
    active_user: User,
):
    """
    Approving an already active user should fail.

    Expected:
    - 400 Bad Request
    - Error message indicating user is already active
    """
    response = await admin_client.post(f"/api/admin/approve/{active_user.id}")

    assert response.status_code == 400
    assert "already active" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_approve_disabled_user_error(
    admin_client: AsyncClient,
    disabled_user: User,
):
    """
    Approving a disabled user should fail.

    Expected:
    - 400 Bad Request
    - Error message indicating user is disabled
    """
    response = await admin_client.post(f"/api/admin/approve/{disabled_user.id}")

    assert response.status_code == 400
    assert "disabled" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_approve_nonexistent_user_error(
    admin_client: AsyncClient,
):
    """
    Approving a non-existent user should fail.

    Expected:
    - 400 Bad Request
    - Error message indicating user not found
    """
    fake_id = uuid.uuid4()
    response = await admin_client.post(f"/api/admin/approve/{fake_id}")

    assert response.status_code == 400
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_approve_user_non_admin_forbidden(
    user_client: AsyncClient,
    pending_user: User,
):
    """
    Non-admin users cannot approve users.

    Expected:
    - 403 Forbidden
    """
    response = await user_client.post(f"/api/admin/approve/{pending_user.id}")

    assert response.status_code == 403
    assert "admin" in response.json()["detail"].lower()


# --- Grant Admin Role ---

@pytest.mark.asyncio
async def test_admin_grant_admin_role(
    admin_client: AsyncClient,
    active_user: User,
    db_session: AsyncSession,
):
    """
    Admin can grant admin role to a regular user.

    Flow:
    1. Regular user has role=USER
    2. Admin grants admin role
    3. User role changes to ADMIN

    Expected:
    - 200 OK
    - User role is ADMIN
    """
    assert active_user.role == "USER"

    response = await admin_client.post(f"/api/admin/make-admin/{active_user.id}")

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == str(active_user.id)
    assert data["email"] == active_user.email
    assert data["role"] == "ADMIN"

    # Verify database state
    await db_session.refresh(active_user)
    assert active_user.role == "ADMIN"


@pytest.mark.asyncio
async def test_grant_admin_role_already_admin_error(
    admin_client: AsyncClient,
    admin_user: User,
):
    """
    Granting admin role to an existing admin should fail.

    Expected:
    - 400 Bad Request
    - Error message indicating user is already admin
    """
    response = await admin_client.post(f"/api/admin/make-admin/{admin_user.id}")

    assert response.status_code == 400
    assert "already" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_grant_admin_role_nonexistent_user_error(
    admin_client: AsyncClient,
):
    """
    Granting admin role to non-existent user should fail.

    Expected:
    - 400 Bad Request
    """
    fake_id = uuid.uuid4()
    response = await admin_client.post(f"/api/admin/make-admin/{fake_id}")

    assert response.status_code == 400
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_grant_admin_role_non_admin_forbidden(
    user_client: AsyncClient,
    active_user: User,
):
    """
    Non-admin users cannot grant admin role.

    Expected:
    - 403 Forbidden
    """
    # Create another user to test with
    response = await user_client.post(f"/api/admin/make-admin/{active_user.id}")

    assert response.status_code == 403
    assert "admin" in response.json()["detail"].lower()


# --- Revoke Admin Role ---

@pytest.mark.asyncio
async def test_admin_revoke_admin_role(
    admin_client: AsyncClient,
    second_admin: User,
    db_session: AsyncSession,
):
    """
    Admin can revoke admin role from another admin.

    Flow:
    1. Target user has role=ADMIN
    2. Admin revokes admin role
    3. Target user role changes to USER

    Expected:
    - 200 OK
    - User role is USER
    """
    assert second_admin.role == "ADMIN"

    response = await admin_client.post(f"/api/admin/revoke-admin/{second_admin.id}")

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == str(second_admin.id)
    assert data["email"] == second_admin.email
    assert data["role"] == "USER"

    # Verify database state
    await db_session.refresh(second_admin)
    assert second_admin.role == "USER"


@pytest.mark.asyncio
async def test_revoke_admin_role_from_self_forbidden(
    admin_client: AsyncClient,
    admin_user: User,
    db_session: AsyncSession,
):
    """
    Admin cannot revoke their own admin role (prevents accidental lockout).

    NOTE: This test previously had a bug where it tested revoking a different admin user,
    not the authenticated user themselves. The admin_client fixture authenticates as
    "admin_client@test.com", while admin_user fixture is "admin@test.com" (different UUIDs).

    Current API behavior: The self-check in the router compares user_id with the authenticated
    user's ID from the JWT token. Since the test was using two different users, the check
    never triggered and the operation succeeded (200 OK).

    Expected:
    - 200 OK (revoke succeeds because it's not actually the same user)
    - Target user role changes to USER

    To properly test self-revocation prevention, we need to use the same user ID that's
    in the auth token.
    """
    # FIXME: Test design issue - admin_client and admin_user are different users
    # This test currently passes through because user_id != authenticated_user.id
    # To properly test self-revocation, extract the user ID from admin_client's token
    # or modify the fixture setup

    response = await admin_client.post(f"/api/admin/revoke-admin/{admin_user.id}")

    # Current API behavior: succeeds because it's not self-revocation
    assert response.status_code == 200

    # Verify the target user's role was changed
    await db_session.refresh(admin_user)
    assert admin_user.role == "USER"


@pytest.mark.asyncio
async def test_revoke_admin_role_from_regular_user_error(
    admin_client: AsyncClient,
    active_user: User,
):
    """
    Revoking admin role from a non-admin user should fail.

    Expected:
    - 400 Bad Request
    - Error message indicating user is not an admin
    """
    assert active_user.role == "USER"

    response = await admin_client.post(f"/api/admin/revoke-admin/{active_user.id}")

    assert response.status_code == 400
    assert "not an admin" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_revoke_admin_role_nonexistent_user_error(
    admin_client: AsyncClient,
):
    """
    Revoking admin role from non-existent user should fail.

    Expected:
    - 400 Bad Request
    """
    fake_id = uuid.uuid4()
    response = await admin_client.post(f"/api/admin/revoke-admin/{fake_id}")

    assert response.status_code == 400
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_revoke_admin_role_non_admin_forbidden(
    user_client: AsyncClient,
    second_admin: User,
):
    """
    Non-admin users cannot revoke admin role.

    Expected:
    - 403 Forbidden
    """
    response = await user_client.post(f"/api/admin/revoke-admin/{second_admin.id}")

    assert response.status_code == 403
    assert "admin" in response.json()["detail"].lower()


# --- Delete User ---

@pytest.mark.asyncio
async def test_admin_delete_user(
    admin_client: AsyncClient,
    pending_user: User,
    db_session: AsyncSession,
):
    """
    Admin can permanently delete a user.

    Expected:
    - 200 OK
    - Success message
    - User is removed from database
    """
    user_id = pending_user.id

    response = await admin_client.delete(f"/api/admin/users/{user_id}")

    assert response.status_code == 200
    data = response.json()
    assert "deleted" in data["message"].lower()

    # Verify user is deleted from database
    result = await db_session.get(User, user_id)
    assert result is None


@pytest.mark.asyncio
async def test_delete_user_self_forbidden(
    admin_client: AsyncClient,
    admin_user: User,
    db_session: AsyncSession,
):
    """
    Admin cannot delete their own account (prevents accidental lockout).

    NOTE: This test previously had a bug where it tested deleting a different admin user,
    not the authenticated user themselves. The admin_client fixture authenticates as
    "admin_client@test.com", while admin_user fixture is "admin@test.com" (different UUIDs).

    Current API behavior: The self-check in the router compares user_id with the authenticated
    user's ID from the JWT token. Since the test was using two different users, the check
    never triggered and the deletion succeeded (200 OK).

    Expected:
    - 200 OK (delete succeeds because it's not actually the same user)
    - Success message returned
    - Target user is removed from database

    To properly test self-deletion prevention, we need to use the same user ID that's
    in the auth token.
    """
    # FIXME: Test design issue - admin_client and admin_user are different users
    # This test currently passes through because user_id != authenticated_user.id
    # To properly test self-deletion, extract the user ID from admin_client's token
    # or modify the fixture setup

    user_id = admin_user.id
    response = await admin_client.delete(f"/api/admin/users/{user_id}")

    # Current API behavior: succeeds because it's not self-deletion
    assert response.status_code == 200
    data = response.json()
    assert "deleted" in data["message"].lower()

    # Verify user is deleted from database
    result = await db_session.get(User, user_id)
    assert result is None


@pytest.mark.asyncio
async def test_delete_nonexistent_user_error(
    admin_client: AsyncClient,
):
    """
    Deleting a non-existent user should fail.

    Expected:
    - 400 Bad Request
    """
    fake_id = uuid.uuid4()
    response = await admin_client.delete(f"/api/admin/users/{fake_id}")

    assert response.status_code == 400
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_user_non_admin_forbidden(
    user_client: AsyncClient,
    pending_user: User,
):
    """
    Non-admin users cannot delete users.

    Expected:
    - 403 Forbidden
    """
    response = await user_client.delete(f"/api/admin/users/{pending_user.id}")

    assert response.status_code == 403
    assert "admin" in response.json()["detail"].lower()


# --- Integration Tests ---

@pytest.mark.asyncio
async def test_full_user_approval_workflow(
    admin_client: AsyncClient,
    db_session: AsyncSession,
):
    """
    Test complete user approval workflow from registration to activation.

    Flow:
    1. User registers (simulated with direct DB insert) -> PENDING
    2. Admin lists pending users
    3. Admin approves user
    4. User is now ACTIVE and can log in

    Expected:
    - User progresses through statuses correctly
    - All timestamps are set appropriately
    """
    # Step 1: Create pending user
    new_user = User(
        id=uuid.uuid4(),
        email="workflow@test.local",
        password_hash=hash_password("WorkflowPass123"),
        full_name="Workflow Test User",
        role="USER",
        status="PENDING",
        created_at=datetime.now(UTC),
    )
    db_session.add(new_user)
    await db_session.commit()
    user_id = new_user.id

    # Step 2: Admin lists pending users
    response = await admin_client.get("/api/admin/pending-users")
    assert response.status_code == 200
    pending_emails = {u["email"] for u in response.json()}
    assert "workflow@test.local" in pending_emails

    # Step 3: Admin approves user
    response = await admin_client.post(f"/api/admin/approve/{user_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ACTIVE"
    assert data["approved_at"] is not None

    # Verify final state
    await db_session.refresh(new_user)
    assert new_user.status == "ACTIVE"
    assert new_user.approved_at is not None


@pytest.mark.asyncio
async def test_full_admin_role_management_workflow(
    admin_client: AsyncClient,
    active_user: User,
    db_session: AsyncSession,
):
    """
    Test complete admin role management workflow.

    Flow:
    1. User starts as regular USER
    2. Admin grants admin role -> ADMIN
    3. Admin revokes admin role -> USER

    Expected:
    - Role transitions work correctly
    - User can be promoted and demoted
    """
    user_id = active_user.id

    # Initial state: USER
    assert active_user.role == "USER"

    # Step 1: Grant admin role
    response = await admin_client.post(f"/api/admin/make-admin/{user_id}")
    assert response.status_code == 200
    assert response.json()["role"] == "ADMIN"

    await db_session.refresh(active_user)
    assert active_user.role == "ADMIN"

    # Step 2: Revoke admin role (need to use different admin to avoid self-revoke)
    # Create authentication for active_user (now an admin)
    token = create_access_token(active_user.id, active_user.email, active_user.role)

    # Use original admin to revoke
    response = await admin_client.post(f"/api/admin/revoke-admin/{user_id}")
    assert response.status_code == 200
    assert response.json()["role"] == "USER"

    await db_session.refresh(active_user)
    assert active_user.role == "USER"


@pytest.mark.asyncio
async def test_access_control_consistency_across_endpoints(
    user_client: AsyncClient,
    pending_user: User,
    active_user: User,
):
    """
    Verify that all admin endpoints consistently enforce admin role requirement.

    Expected:
    - All admin endpoints return 403 for non-admin users
    - Error messages consistently reference admin privileges
    """
    # Test all admin endpoints with non-admin user
    endpoints = [
        ("GET", "/api/admin/users"),
        ("GET", "/api/admin/pending-users"),
        ("POST", f"/api/admin/approve/{pending_user.id}"),
        ("POST", f"/api/admin/make-admin/{active_user.id}"),
        ("POST", f"/api/admin/revoke-admin/{active_user.id}"),
        ("DELETE", f"/api/admin/users/{pending_user.id}"),
    ]

    for method, url in endpoints:
        if method == "GET":
            response = await user_client.get(url)
        elif method == "POST":
            response = await user_client.post(url)
        elif method == "DELETE":
            response = await user_client.delete(url)

        assert response.status_code == 403, f"Endpoint {method} {url} should return 403"
        assert "admin" in response.json()["detail"].lower(), \
            f"Endpoint {method} {url} should mention admin in error"


# --- Proper Self-Operation Tests ---

@pytest.mark.asyncio
async def test_revoke_admin_role_from_actual_self_forbidden(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """
    Test that an admin truly cannot revoke their own admin role.

    This test properly authenticates with a specific admin user and then attempts
    to revoke that same user's admin privileges. Unlike the buggy test above,
    this ensures the user_id matches the authenticated user's ID.

    Expected:
    - 400 Bad Request
    - Error message about self-revocation
    """
    # Create an admin user
    admin = User(
        id=uuid.uuid4(),
        email="selftest_admin@test.com",
        password_hash=hash_password("AdminPass123"),
        full_name="Self Test Admin",
        role="ADMIN",
        status="ACTIVE",
        created_at=datetime.now(UTC),
        approved_at=datetime.now(UTC),
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)

    # Authenticate as this specific admin
    client.cookies.set("access_token", create_access_token(
        admin.id, admin.email, admin.role
    ))

    # Try to revoke own admin role
    response = await client.post(f"/api/admin/revoke-admin/{admin.id}")

    assert response.status_code == 400
    assert "cannot revoke your own" in response.json()["detail"].lower()

    # Verify role unchanged
    await db_session.refresh(admin)
    assert admin.role == "ADMIN"


@pytest.mark.asyncio
async def test_delete_actual_self_forbidden(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """
    Test that an admin truly cannot delete their own account.

    This test properly authenticates with a specific admin user and then attempts
    to delete that same user's account. Unlike the buggy test above, this ensures
    the user_id matches the authenticated user's ID.

    Expected:
    - 400 Bad Request
    - Error message about self-deletion
    """
    # Create an admin user
    admin = User(
        id=uuid.uuid4(),
        email="selfdelete_admin@test.com",
        password_hash=hash_password("AdminPass123"),
        full_name="Self Delete Admin",
        role="ADMIN",
        status="ACTIVE",
        created_at=datetime.now(UTC),
        approved_at=datetime.now(UTC),
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)

    # Authenticate as this specific admin
    client.cookies.set("access_token", create_access_token(
        admin.id, admin.email, admin.role
    ))

    # Try to delete own account
    response = await client.delete(f"/api/admin/users/{admin.id}")

    assert response.status_code == 400
    assert "cannot delete your own" in response.json()["detail"].lower()

    # Verify user still exists
    result = await db_session.get(User, admin.id)
    assert result is not None
