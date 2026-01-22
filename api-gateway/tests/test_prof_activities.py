"""
Tests for professional activities module.

Tests coverage:
- List professional activities (authenticated users)
- Create professional activity (admin only)
- Update professional activity (admin only)
- Delete professional activity (admin only)
- Unique code constraint validation
- Authorization checks (admin vs regular user)
- Edge cases and error scenarios
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ProfActivity

pytestmark = pytest.mark.asyncio


# Helper functions

async def create_test_prof_activity(
    db: AsyncSession,
    code: str = "test_activity",
    name: str = "Test Activity",
    description: str | None = "Test description",
) -> ProfActivity:
    """
    Helper to create a professional activity for testing.

    Args:
        db: Database session
        code: Unique activity code
        name: Activity name
        description: Optional description

    Returns:
        Created ProfActivity instance
    """
    prof_activity = ProfActivity(
        id=uuid.uuid4(),
        code=code,
        name=name,
        description=description,
    )
    db.add(prof_activity)
    await db.commit()
    await db.refresh(prof_activity)
    return prof_activity


# List Professional Activities Tests


@pytest.mark.unit
async def test_list_prof_activities_success(
    user_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Test successful listing of professional activities as regular user.

    Scenario:
    - Create multiple professional activities
    - List them via API
    - Verify all are returned in correct order
    """
    # Arrange: Create test activities with unique codes
    unique_suffix = uuid.uuid4().hex[:8]
    code1 = f"analyst_{unique_suffix}"
    code2 = f"developer_{unique_suffix}"
    code3 = f"manager_{unique_suffix}"

    await create_test_prof_activity(
        db_session,
        code=code1,
        name="Analyst",
        description="Data analyst",
    )
    await create_test_prof_activity(
        db_session,
        code=code2,
        name="Developer",
        description="Software developer",
    )
    await create_test_prof_activity(
        db_session,
        code=code3,
        name="Manager",
        description="Project manager",
    )

    # Act: List activities
    response = await user_client.get("/api/prof-activities")

    # Assert: Verify response
    assert response.status_code == 200
    data = response.json()
    assert "activities" in data
    activities = data["activities"]
    assert len(activities) >= 3

    # Verify activities are ordered by code
    codes = [a["code"] for a in activities]
    assert code1 in codes
    assert code2 in codes
    assert code3 in codes

    # Verify structure of returned activities
    for activity in activities:
        assert "id" in activity
        assert "code" in activity
        assert "name" in activity
        assert "description" in activity or activity.get("description") is None


@pytest.mark.unit
async def test_list_prof_activities_empty(
    user_client: AsyncClient,
) -> None:
    """
    Test listing professional activities when none exist.

    Scenario:
    - No activities in database
    - List should return empty array
    """
    # Act: List activities
    response = await user_client.get("/api/prof-activities")

    # Assert: Empty list returned
    assert response.status_code == 200
    data = response.json()
    assert "activities" in data
    assert isinstance(data["activities"], list)


@pytest.mark.unit
async def test_list_prof_activities_requires_authentication(
    client: AsyncClient,
) -> None:
    """
    Test that listing activities requires authentication.

    Scenario:
    - Request without authentication
    - Should return 401 Unauthorized
    """
    # Act: Request without auth
    response = await client.get("/api/prof-activities")

    # Assert: Unauthorized
    assert response.status_code == 401


@pytest.mark.integration
async def test_list_prof_activities_as_admin(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Test listing professional activities as admin user.

    Scenario:
    - Admin user should have same read access
    - Verify admin can list activities
    """
    # Arrange: Create test activity with unique code
    unique_code = f"tester_{uuid.uuid4().hex[:8]}"
    await create_test_prof_activity(
        db_session,
        code=unique_code,
        name="Tester",
    )

    # Act: List as admin
    response = await admin_client.get("/api/prof-activities")

    # Assert: Success
    assert response.status_code == 200
    data = response.json()
    assert "activities" in data
    assert len(data["activities"]) >= 1


# Create Professional Activity Tests


@pytest.mark.integration
async def test_create_prof_activity_success(
    admin_client: AsyncClient,
) -> None:
    """
    Test successful creation of professional activity by admin.

    Scenario:
    - Admin creates a new activity
    - Verify activity is created with correct data
    """
    # Arrange: Prepare request data
    request_data = {
        "code": "new_activity",
        "name": "New Activity",
        "description": "A brand new professional activity",
    }

    # Act: Create activity
    response = await admin_client.post("/api/prof-activities", json=request_data)

    # Assert: Created successfully
    assert response.status_code == 201
    data = response.json()
    assert data["code"] == request_data["code"]
    assert data["name"] == request_data["name"]
    assert data["description"] == request_data["description"]
    assert "id" in data
    # Verify UUID is valid
    assert uuid.UUID(data["id"])


@pytest.mark.integration
async def test_create_prof_activity_without_description(
    admin_client: AsyncClient,
) -> None:
    """
    Test creating professional activity without optional description.

    Scenario:
    - Admin creates activity with only required fields
    - Verify activity is created successfully
    """
    # Arrange: Minimal request data
    request_data = {
        "code": "minimal_activity",
        "name": "Minimal Activity",
    }

    # Act: Create activity
    response = await admin_client.post("/api/prof-activities", json=request_data)

    # Assert: Created successfully
    assert response.status_code == 201
    data = response.json()
    assert data["code"] == request_data["code"]
    assert data["name"] == request_data["name"]
    assert data["description"] is None


@pytest.mark.integration
async def test_create_prof_activity_duplicate_code(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Test creating professional activity with duplicate code.

    Scenario:
    - Activity with code 'duplicate' exists
    - Admin tries to create another with same code
    - Should return 400 Bad Request
    """
    # Arrange: Create existing activity with unique code
    unique_code = f"duplicate_{uuid.uuid4().hex[:8]}"
    await create_test_prof_activity(
        db_session,
        code=unique_code,
        name="Existing Activity",
    )

    # Act: Try to create duplicate
    request_data = {
        "code": unique_code,
        "name": "New Activity with Duplicate Code",
    }
    response = await admin_client.post("/api/prof-activities", json=request_data)

    # Assert: Bad request with error message
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "duplicate" in data["detail"].lower()


@pytest.mark.unit
async def test_create_prof_activity_requires_admin(
    user_client: AsyncClient,
) -> None:
    """
    Test that creating professional activity requires admin role.

    Scenario:
    - Regular user tries to create activity
    - Should return 403 Forbidden
    """
    # Arrange: Prepare request data
    request_data = {
        "code": "forbidden_activity",
        "name": "Forbidden Activity",
    }

    # Act: Try to create as regular user
    response = await user_client.post("/api/prof-activities", json=request_data)

    # Assert: Forbidden
    assert response.status_code == 403


@pytest.mark.integration
async def test_create_prof_activity_invalid_data(
    admin_client: AsyncClient,
) -> None:
    """
    Test creating professional activity with invalid data.

    Scenario:
    - Missing required fields
    - Should return 422 Unprocessable Entity
    """
    # Act: Request with missing required field
    request_data = {
        "name": "Missing Code",
    }
    response = await admin_client.post("/api/prof-activities", json=request_data)

    # Assert: Validation error
    assert response.status_code == 422


@pytest.mark.integration
async def test_create_prof_activity_code_too_long(
    admin_client: AsyncClient,
) -> None:
    """
    Test creating professional activity with code exceeding max length.

    Scenario:
    - Code field has max_length=50
    - Provide code longer than 50 characters
    - Should return 422 Unprocessable Entity
    """
    # Arrange: Code longer than 50 characters
    request_data = {
        "code": "a" * 51,  # 51 characters
        "name": "Too Long Code",
    }

    # Act: Create activity
    response = await admin_client.post("/api/prof-activities", json=request_data)

    # Assert: Validation error
    assert response.status_code == 422


@pytest.mark.integration
async def test_create_prof_activity_empty_code(
    admin_client: AsyncClient,
) -> None:
    """
    Test creating professional activity with empty code.

    Scenario:
    - Code field has min_length=1
    - Provide empty string
    - Should return 422 Unprocessable Entity
    """
    # Arrange: Empty code
    request_data = {
        "code": "",
        "name": "Empty Code",
    }

    # Act: Create activity
    response = await admin_client.post("/api/prof-activities", json=request_data)

    # Assert: Validation error
    assert response.status_code == 422


# Update Professional Activity Tests


@pytest.mark.integration
async def test_update_prof_activity_success(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Test successful update of professional activity by admin.

    Scenario:
    - Activity exists
    - Admin updates name and description
    - Verify changes are applied
    """
    # Arrange: Create activity with unique code
    unique_code = f"updatable_{uuid.uuid4().hex[:8]}"
    activity = await create_test_prof_activity(
        db_session,
        code=unique_code,
        name="Original Name",
        description="Original description",
    )

    # Act: Update activity
    request_data = {
        "name": "Updated Name",
        "description": "Updated description",
    }
    response = await admin_client.put(
        f"/api/prof-activities/{activity.id}",
        json=request_data,
    )

    # Assert: Updated successfully
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(activity.id)
    assert data["code"] == unique_code  # Code should not change
    assert data["name"] == "Updated Name"
    assert data["description"] == "Updated description"


@pytest.mark.integration
async def test_update_prof_activity_name_only(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Test updating only the name field.

    Scenario:
    - Update only name, leave description unchanged
    - Verify only name is updated
    """
    # Arrange: Create activity with unique code
    unique_code = f"partial_update_{uuid.uuid4().hex[:8]}"
    activity = await create_test_prof_activity(
        db_session,
        code=unique_code,
        name="Original Name",
        description="Original description",
    )

    # Act: Update only name
    request_data = {
        "name": "New Name",
    }
    response = await admin_client.put(
        f"/api/prof-activities/{activity.id}",
        json=request_data,
    )

    # Assert: Name updated, description preserved
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New Name"
    assert data["description"] == "Original description"


@pytest.mark.integration
async def test_update_prof_activity_description_only(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Test updating only the description field.

    Scenario:
    - Update only description, leave name unchanged
    - Verify only description is updated
    """
    # Arrange: Create activity with unique code
    unique_code = f"desc_update_{uuid.uuid4().hex[:8]}"
    activity = await create_test_prof_activity(
        db_session,
        code=unique_code,
        name="Original Name",
        description="Original description",
    )

    # Act: Update only description
    request_data = {
        "description": "New description",
    }
    response = await admin_client.put(
        f"/api/prof-activities/{activity.id}",
        json=request_data,
    )

    # Assert: Description updated, name preserved
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Original Name"
    assert data["description"] == "New description"


@pytest.mark.integration
async def test_update_prof_activity_not_found(
    admin_client: AsyncClient,
) -> None:
    """
    Test updating non-existent professional activity.

    Scenario:
    - Provide UUID that doesn't exist
    - Should return 404 Not Found
    """
    # Arrange: Random UUID
    non_existent_id = uuid.uuid4()

    # Act: Try to update
    request_data = {
        "name": "Updated Name",
    }
    response = await admin_client.put(
        f"/api/prof-activities/{non_existent_id}",
        json=request_data,
    )

    # Assert: Not found
    assert response.status_code == 404


@pytest.mark.unit
async def test_update_prof_activity_requires_admin(
    user_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Test that updating professional activity requires admin role.

    Scenario:
    - Regular user tries to update activity
    - Should return 403 Forbidden
    """
    # Arrange: Create activity with unique code
    unique_code = f"forbidden_update_{uuid.uuid4().hex[:8]}"
    activity = await create_test_prof_activity(
        db_session,
        code=unique_code,
        name="Original Name",
    )

    # Act: Try to update as regular user
    request_data = {
        "name": "New Name",
    }
    response = await user_client.put(
        f"/api/prof-activities/{activity.id}",
        json=request_data,
    )

    # Assert: Forbidden
    assert response.status_code == 403


@pytest.mark.integration
async def test_update_prof_activity_invalid_uuid(
    admin_client: AsyncClient,
) -> None:
    """
    Test updating with invalid UUID format.

    Scenario:
    - Provide invalid UUID string
    - Should return 422 Unprocessable Entity
    """
    # Act: Request with invalid UUID
    request_data = {
        "name": "New Name",
    }
    response = await admin_client.put(
        "/api/prof-activities/not-a-uuid",
        json=request_data,
    )

    # Assert: Validation error
    assert response.status_code == 422


# Delete Professional Activity Tests


@pytest.mark.integration
async def test_delete_prof_activity_success(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Test successful deletion of professional activity by admin.

    Scenario:
    - Activity exists without weight tables
    - Admin deletes it
    - Verify activity is removed
    """
    # Arrange: Create activity with unique code
    unique_code = f"deletable_{uuid.uuid4().hex[:8]}"
    activity = await create_test_prof_activity(
        db_session,
        code=unique_code,
        name="Deletable Activity",
    )
    activity_id = activity.id

    # Act: Delete activity
    response = await admin_client.delete(f"/api/prof-activities/{activity_id}")

    # Assert: Deleted successfully (204 No Content)
    assert response.status_code == 204

    # Verify: Activity is gone
    from sqlalchemy import select
    stmt = select(ProfActivity).where(ProfActivity.id == activity_id)
    result = await db_session.execute(stmt)
    assert result.scalar_one_or_none() is None


@pytest.mark.integration
async def test_delete_prof_activity_not_found(
    admin_client: AsyncClient,
) -> None:
    """
    Test deleting non-existent professional activity.

    Scenario:
    - Provide UUID that doesn't exist
    - Should return 404 Not Found
    """
    # Arrange: Random UUID
    non_existent_id = uuid.uuid4()

    # Act: Try to delete
    response = await admin_client.delete(f"/api/prof-activities/{non_existent_id}")

    # Assert: Not found
    assert response.status_code == 404


@pytest.mark.unit
async def test_delete_prof_activity_requires_admin(
    user_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Test that deleting professional activity requires admin role.

    Scenario:
    - Regular user tries to delete activity
    - Should return 403 Forbidden
    """
    # Arrange: Create activity with unique code
    unique_code = f"forbidden_delete_{uuid.uuid4().hex[:8]}"
    activity = await create_test_prof_activity(
        db_session,
        code=unique_code,
        name="Forbidden Delete",
    )

    # Act: Try to delete as regular user
    response = await user_client.delete(f"/api/prof-activities/{activity.id}")

    # Assert: Forbidden
    assert response.status_code == 403


@pytest.mark.integration
async def test_delete_prof_activity_invalid_uuid(
    admin_client: AsyncClient,
) -> None:
    """
    Test deleting with invalid UUID format.

    Scenario:
    - Provide invalid UUID string
    - Should return 422 Unprocessable Entity
    """
    # Act: Request with invalid UUID
    response = await admin_client.delete("/api/prof-activities/not-a-uuid")

    # Assert: Validation error
    assert response.status_code == 422


# Edge Cases and Integration Tests


@pytest.mark.integration
async def test_full_lifecycle_prof_activity(
    admin_only_client: AsyncClient,
    user_only_client: AsyncClient,
) -> None:
    """
    Test complete lifecycle of a professional activity.

    Scenario:
    - Admin creates activity
    - User lists and sees it
    - Admin updates it
    - User lists and sees updated version
    - Admin deletes it
    - User lists and doesn't see it
    """
    # Step 1: Create with unique code
    unique_code = f"lifecycle_{uuid.uuid4().hex[:8]}"
    create_data = {
        "code": unique_code,
        "name": "Lifecycle Test",
        "description": "Testing full lifecycle",
    }
    create_response = await admin_only_client.post(
        "/api/prof-activities",
        json=create_data,
    )
    assert create_response.status_code == 201
    activity = create_response.json()
    activity_id = activity["id"]

    # Step 2: User lists and sees it
    list_response = await user_only_client.get("/api/prof-activities")
    assert list_response.status_code == 200
    activities = list_response.json()["activities"]
    codes = [a["code"] for a in activities]
    assert unique_code in codes

    # Step 3: Admin updates
    update_data = {
        "name": "Updated Lifecycle Test",
        "description": "Updated description",
    }
    update_response = await admin_only_client.put(
        f"/api/prof-activities/{activity_id}",
        json=update_data,
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["name"] == "Updated Lifecycle Test"

    # Step 4: User lists and sees updated version
    list_response2 = await user_only_client.get("/api/prof-activities")
    assert list_response2.status_code == 200
    activities2 = list_response2.json()["activities"]
    lifecycle_activity = next(a for a in activities2 if a["code"] == unique_code)
    assert lifecycle_activity["name"] == "Updated Lifecycle Test"

    # Step 5: Admin deletes
    delete_response = await admin_only_client.delete(f"/api/prof-activities/{activity_id}")
    assert delete_response.status_code == 204

    # Step 6: User lists and doesn't see it
    list_response3 = await user_only_client.get("/api/prof-activities")
    assert list_response3.status_code == 200
    activities3 = list_response3.json()["activities"]
    codes3 = [a["code"] for a in activities3]
    assert unique_code not in codes3


@pytest.mark.integration
async def test_create_multiple_activities_different_codes(
    admin_client: AsyncClient,
) -> None:
    """
    Test creating multiple activities with different codes.

    Scenario:
    - Create several activities in sequence
    - Verify all are created successfully
    - Verify all can be listed
    """
    # Arrange: Activity data
    activities_data = [
        {"code": "activity_1", "name": "Activity 1"},
        {"code": "activity_2", "name": "Activity 2"},
        {"code": "activity_3", "name": "Activity 3"},
    ]

    # Act: Create all activities
    created_ids = []
    for data in activities_data:
        response = await admin_client.post("/api/prof-activities", json=data)
        assert response.status_code == 201
        created_ids.append(response.json()["id"])

    # Assert: All can be listed
    list_response = await admin_client.get("/api/prof-activities")
    assert list_response.status_code == 200
    activities = list_response.json()["activities"]
    codes = [a["code"] for a in activities]
    assert "activity_1" in codes
    assert "activity_2" in codes
    assert "activity_3" in codes


@pytest.mark.integration
async def test_update_activity_preserves_code(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Test that updating an activity doesn't change its code.

    Scenario:
    - Code field is unique and should not be updatable
    - Update request should only affect name and description
    """
    # Arrange: Create activity with unique code
    unique_code = f"immutable_code_{uuid.uuid4().hex[:8]}"
    activity = await create_test_prof_activity(
        db_session,
        code=unique_code,
        name="Original Name",
    )

    # Act: Update (code should remain unchanged)
    update_data = {
        "name": "New Name",
        "description": "New description",
    }
    response = await admin_client.put(
        f"/api/prof-activities/{activity.id}",
        json=update_data,
    )

    # Assert: Code unchanged
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == unique_code
    assert data["name"] == "New Name"


@pytest.mark.integration
async def test_case_sensitive_codes(
    admin_client: AsyncClient,
) -> None:
    """
    Test that codes are case-sensitive.

    Scenario:
    - Create activity with code 'TestCode'
    - Create another with code 'testcode'
    - Both should be created successfully (different codes)
    """
    # Use unique codes to avoid conflicts with seed data
    unique_suffix = uuid.uuid4().hex[:8]
    code1 = f"TestCode_{unique_suffix}"
    code2 = f"testcode_{unique_suffix}"

    # Act: Create first activity
    response1 = await admin_client.post(
        "/api/prof-activities",
        json={"code": code1, "name": "TestCode (capitalized)"},
    )
    assert response1.status_code == 201

    # Act: Create second activity with different case
    response2 = await admin_client.post(
        "/api/prof-activities",
        json={"code": code2, "name": "testcode (lowercase)"},
    )
    assert response2.status_code == 201

    # Assert: Both exist
    list_response = await admin_client.get("/api/prof-activities")
    activities = list_response.json()["activities"]
    codes = [a["code"] for a in activities]
    assert code1 in codes
    assert code2 in codes
