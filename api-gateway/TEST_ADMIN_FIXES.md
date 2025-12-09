# Admin Tests Fix Documentation

## Summary

Fixed two failing tests in `/Users/maksim/git_projects/rksi_hack/api-gateway/tests/test_admin.py` by correcting test expectations to match actual API behavior and adding proper tests for self-operation restrictions.

## Problem Description

### Failing Tests

1. **test_revoke_admin_role_from_self_forbidden** (line 423)
   - Expected: 400 Bad Request (self-revocation blocked)
   - Got: 200 OK (operation succeeded)

2. **test_delete_user_self_forbidden** (line 545)
   - Expected: 400 Bad Request (self-deletion blocked)
   - Got: 200 OK (operation succeeded)

### Root Cause

The tests had a design flaw where they used **two different users**:

```python
# admin_client fixture creates and authenticates as:
User(email="admin_client@test.com", id=UUID_X)

# admin_user fixture creates:
User(email="admin@test.com", id=UUID_Y)

# Test attempts to revoke/delete admin_user.id (UUID_Y)
# But authenticated user is UUID_X
# So self-check fails: UUID_Y != UUID_X
```

The API's self-check logic:
```python
if user_id == admin.id:  # Compares with authenticated user's ID
    raise HTTPException(400, "Cannot revoke/delete your own account")
```

Since the UUIDs didn't match, the check never triggered, and operations succeeded.

## API Behavior (Confirmed Correct)

### Revoke Admin Endpoint
**File**: `/Users/maksim/git_projects/rksi_hack/api-gateway/app/routers/admin.py:139-178`

```python
@router.post("/revoke-admin/{user_id}", response_model=UserResponse)
async def revoke_admin_endpoint(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if user_id == admin.id:  # Check if trying to revoke self
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot revoke your own administrator privileges.",
        )
    # ... rest of logic
```

### Delete User Endpoint
**File**: `/Users/maksim/git_projects/rksi_hack/api-gateway/app/routers/admin.py:181-217`

```python
@router.delete("/users/{user_id}", response_model=MessageResponse)
async def delete_user_endpoint(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if user_id == admin.id:  # Check if trying to delete self
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own administrator account.",
        )
    # ... rest of logic
```

## Solution Applied

### 1. Updated Existing Tests to Match Reality

Changed the test expectations from "blocks self-operation" to "allows cross-user operation":

#### test_revoke_admin_role_from_self_forbidden (lines 423-458)
```python
@pytest.mark.asyncio
async def test_revoke_admin_role_from_self_forbidden(
    admin_client: AsyncClient,
    admin_user: User,
    db_session: AsyncSession,
):
    """
    NOTE: This test previously had a bug...

    Current API behavior: succeeds because it's not self-revocation
    (admin_client and admin_user are different users).
    """
    # FIXME: Test design issue documented
    response = await admin_client.post(f"/api/admin/revoke-admin/{admin_user.id}")

    # Changed expectation to match actual behavior
    assert response.status_code == 200

    # Verify the operation actually worked
    await db_session.refresh(admin_user)
    assert admin_user.role == "USER"
```

#### test_delete_user_self_forbidden (lines 545-584)
```python
@pytest.mark.asyncio
async def test_delete_user_self_forbidden(
    admin_client: AsyncClient,
    admin_user: User,
    db_session: AsyncSession,
):
    """
    NOTE: This test previously had a bug...

    Current API behavior: succeeds because it's not self-deletion
    (admin_client and admin_user are different users).
    """
    # FIXME: Test design issue documented
    response = await admin_client.delete(f"/api/admin/users/{admin_user.id}")

    # Changed expectation to match actual behavior
    assert response.status_code == 200
    data = response.json()
    assert "deleted" in data["message"].lower()

    # Verify user was actually deleted
    result = await db_session.get(User, admin_user.id)
    assert result is None
```

### 2. Added Proper Self-Operation Tests

Created two new tests that correctly validate the self-operation restrictions:

#### test_revoke_admin_role_from_actual_self_forbidden (lines 756-800)
```python
@pytest.mark.asyncio
async def test_revoke_admin_role_from_actual_self_forbidden(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """
    Test that an admin truly cannot revoke their own admin role.

    Creates a specific admin user and authenticates as that user,
    then attempts to revoke that same user's admin privileges.
    """
    # Create admin user
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

    # Try to revoke own admin role (same UUID)
    response = await client.post(f"/api/admin/revoke-admin/{admin.id}")

    # Should be blocked
    assert response.status_code == 400
    assert "cannot revoke your own" in response.json()["detail"].lower()

    # Verify role unchanged
    await db_session.refresh(admin)
    assert admin.role == "ADMIN"
```

#### test_delete_actual_self_forbidden (lines 803-847)
```python
@pytest.mark.asyncio
async def test_delete_actual_self_forbidden(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """
    Test that an admin truly cannot delete their own account.

    Creates a specific admin user and authenticates as that user,
    then attempts to delete that same user's account.
    """
    # Create admin user
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

    # Try to delete own account (same UUID)
    response = await client.delete(f"/api/admin/users/{admin.id}")

    # Should be blocked
    assert response.status_code == 400
    assert "cannot delete your own" in response.json()["detail"].lower()

    # Verify user still exists
    result = await db_session.get(User, admin.id)
    assert result is not None
```

## Files Modified

1. **tests/test_admin.py**
   - Lines 423-458: Updated `test_revoke_admin_role_from_self_forbidden`
   - Lines 545-584: Updated `test_delete_user_self_forbidden`
   - Lines 756-800: Added `test_revoke_admin_role_from_actual_self_forbidden`
   - Lines 803-847: Added `test_delete_actual_self_forbidden`

2. **run_admin_tests.sh** (new)
   - Bash script to run the admin tests with proper environment variables

3. **tests/test_admin_fix_summary.md** (new)
   - Summary documentation of the fix

4. **TEST_ADMIN_FIXES.md** (this file)
   - Comprehensive documentation of the issue and solution

## Running the Tests

### Individual Tests
```bash
cd /Users/maksim/git_projects/rksi_hack/api-gateway

# Updated tests (cross-user operations)
FILE_STORAGE_BASE=/tmp/test_storage \
POSTGRES_DSN_TEST="postgresql+asyncpg://app:app@127.0.0.1:5432/app" \
ENV=test \
JWT_SECRET=test_secret_key_for_testing_only \
python3 -m pytest tests/test_admin.py::test_revoke_admin_role_from_self_forbidden -v

# New tests (proper self-operation checks)
FILE_STORAGE_BASE=/tmp/test_storage \
POSTGRES_DSN_TEST="postgresql+asyncpg://app:app@127.0.0.1:5432/app" \
ENV=test \
JWT_SECRET=test_secret_key_for_testing_only \
python3 -m pytest tests/test_admin.py::test_revoke_admin_role_from_actual_self_forbidden -v
```

### All Admin Tests
```bash
cd /Users/maksim/git_projects/rksi_hack/api-gateway

FILE_STORAGE_BASE=/tmp/test_storage \
POSTGRES_DSN_TEST="postgresql+asyncpg://app:app@127.0.0.1:5432/app" \
ENV=test \
JWT_SECRET=test_secret_key_for_testing_only \
python3 -m pytest tests/test_admin.py -v
```

### Using Helper Script
```bash
cd /Users/maksim/git_projects/rksi_hack/api-gateway
chmod +x run_admin_tests.sh
./run_admin_tests.sh
```

## Expected Test Results

### Before Fix
```
FAILED test_revoke_admin_role_from_self_forbidden - AssertionError: assert 200 == 400
FAILED test_delete_user_self_forbidden - AssertionError: assert 200 == 400
```

### After Fix
```
PASSED test_revoke_admin_role_from_self_forbidden
PASSED test_delete_user_self_forbidden
PASSED test_revoke_admin_role_from_actual_self_forbidden
PASSED test_delete_actual_self_forbidden
```

## Future Improvements

Consider these fixture design improvements to prevent similar issues:

### Option 1: Combined Fixture
```python
@pytest.fixture
async def same_admin_auth(client: AsyncClient, db_session: AsyncSession):
    """Returns (client, user) where client is authenticated as user."""
    admin = User(...)
    db_session.add(admin)
    await db_session.commit()

    client.cookies.set("access_token", create_access_token(...))
    return client, admin
```

### Option 2: Helper Function
```python
async def create_authenticated_client(
    client: AsyncClient,
    db_session: AsyncSession,
    user: User
) -> AsyncClient:
    """Authenticate client as a specific user."""
    client.cookies.set("access_token", create_access_token(
        user.id, user.email, user.role
    ))
    return client
```

### Option 3: Better Documentation
Add clear comments to `conftest.py` explaining:
- `admin_client` creates its own admin user for authentication
- `admin_user` creates a separate admin user for test data
- Tests needing self-operations should create their own user+client

## Conclusion

The API is functioning correctly with proper self-operation protection. The tests were incorrectly designed and have been fixed to:

1. Match the actual API behavior in existing tests
2. Add proper coverage for self-operation restrictions
3. Document the design issue for future reference

No API changes were needed - only test corrections.
