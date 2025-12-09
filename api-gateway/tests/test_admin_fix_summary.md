# Test Admin Fix Summary

## Issue Description

Two tests in `tests/test_admin.py` were failing due to incorrect test design:

1. `test_revoke_admin_role_from_self_forbidden` (line 423)
2. `test_delete_user_self_forbidden` (line 545)

## Root Cause

Both tests had the same design flaw: they attempted to test "self-operation" restrictions (preventing admins from revoking their own admin role or deleting their own account), but they used **two different users**:

- **`admin_client` fixture**: Authenticates as "admin_client@test.com" with UUID `X`
- **`admin_user` fixture**: Creates a different user "admin@test.com" with UUID `Y`

When the tests called the API with `admin_user.id` (UUID `Y`), the router's self-check compared:
```python
if user_id == admin.id:  # Y == X? No!
```

Since the UUIDs didn't match, the self-check never triggered, and the operations succeeded (200 OK) instead of being rejected (400 Bad Request).

## API Behavior Analysis

The API router code is **correct**:

### `/api/admin/revoke-admin/{user_id}` (admin.py:139-178)
```python
if user_id == admin.id:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="You cannot revoke your own administrator privileges.",
    )
```

### `/api/admin/users/{user_id}` DELETE (admin.py:181-217)
```python
if user_id == admin.id:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="You cannot delete your own administrator account.",
    )
```

Both endpoints correctly prevent self-operations **when the UUIDs match**.

## Fix Applied

### 1. Updated Failing Tests (Lines 423-458, 545-584)

Changed the tests to match the **actual API behavior** (operations succeed because different users):

```python
@pytest.mark.asyncio
async def test_revoke_admin_role_from_self_forbidden(
    admin_client: AsyncClient,
    admin_user: User,
    db_session: AsyncSession,
):
    """
    NOTE: This test previously had a bug where it tested revoking a different admin user,
    not the authenticated user themselves. The admin_client fixture authenticates as
    "admin_client@test.com", while admin_user fixture is "admin@test.com" (different UUIDs).

    Current API behavior: The self-check in the router compares user_id with the authenticated
    user's ID from the JWT token. Since the test was using two different users, the check
    never triggered and the operation succeeded (200 OK).

    Expected:
    - 200 OK (revoke succeeds because it's not actually the same user)
    - Target user role changes to USER
    """
    # FIXME: Test design issue - admin_client and admin_user are different users
    response = await admin_client.post(f"/api/admin/revoke-admin/{admin_user.id}")

    assert response.status_code == 200  # Changed from 400
    await db_session.refresh(admin_user)
    assert admin_user.role == "USER"  # Verify role changed
```

Similar changes made to `test_delete_user_self_forbidden`.

### 2. Added Proper Self-Operation Tests (Lines 756-847)

Created two new tests that **correctly** test the self-operation restrictions:

```python
@pytest.mark.asyncio
async def test_revoke_admin_role_from_actual_self_forbidden(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """
    Test that an admin truly cannot revoke their own admin role.

    This test properly authenticates with a specific admin user and then attempts
    to revoke that same user's admin privileges.
    """
    # Create an admin user
    admin = User(id=uuid.uuid4(), email="selftest_admin@test.com", ...)
    db_session.add(admin)
    await db_session.commit()

    # Authenticate as this specific admin
    client.cookies.set("access_token", create_access_token(
        admin.id, admin.email, admin.role
    ))

    # Try to revoke own admin role (using same UUID)
    response = await client.post(f"/api/admin/revoke-admin/{admin.id}")

    assert response.status_code == 400
    assert "cannot revoke your own" in response.json()["detail"].lower()
```

Similar test added for self-deletion: `test_delete_actual_self_forbidden`.

## Test Results

After fixes:
- Old tests now pass (they test cross-user operations)
- New tests properly validate the self-operation prevention logic
- API behavior is confirmed to be correct

## Files Modified

- `/Users/maksim/git_projects/rksi_hack/api-gateway/tests/test_admin.py`
  - Updated lines 423-458: `test_revoke_admin_role_from_self_forbidden`
  - Updated lines 545-584: `test_delete_user_self_forbidden`
  - Added lines 756-800: `test_revoke_admin_role_from_actual_self_forbidden`
  - Added lines 803-847: `test_delete_actual_self_forbidden`

## Recommendation

Consider refactoring the fixture design to make it clearer when tests need the authenticated user vs. a different user. Options:

1. Add a `same_admin_client` fixture that returns both the client and the user object
2. Add helper function to create authenticated clients for specific users
3. Document the fixture behavior more clearly in `conftest.py`
