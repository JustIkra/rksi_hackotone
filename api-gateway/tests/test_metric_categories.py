"""
Tests for metric categories API endpoints.

Tests the CRUD operations and reordering functionality.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MetricCategory, User
from tests.conftest import get_auth_cookie


@pytest.fixture
async def sample_categories(db_session: AsyncSession) -> list[MetricCategory]:
    """Create sample categories for testing."""
    categories = [
        MetricCategory(
            id=uuid.uuid4(),
            code=f"cat_{i}",
            name=f"Category {i}",
            description=f"Description {i}",
            sort_order=i * 10,
        )
        for i in range(3)
    ]
    for cat in categories:
        db_session.add(cat)
    await db_session.commit()
    for cat in categories:
        await db_session.refresh(cat)
    return categories


# List Categories Tests


async def test_list_categories(
    client: AsyncClient,
    active_user: User,
    sample_categories: list[MetricCategory],
) -> None:
    """Test listing all categories."""
    response = await client.get(
        "/api/admin/metric-categories",
        cookies=get_auth_cookie(active_user),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3


async def test_list_categories_requires_auth(client: AsyncClient) -> None:
    """Test that listing categories requires authentication."""
    response = await client.get("/api/admin/metric-categories")
    assert response.status_code == 401


# Reorder Tests


async def test_reorder_category_move_down(
    client: AsyncClient,
    admin_user: User,
    sample_categories: list[MetricCategory],
) -> None:
    """Test moving a category down (from position 0 to position 2)."""
    category_to_move = sample_categories[0]

    response = await client.patch(
        "/api/admin/metric-categories/reorder",
        json={
            "category_id": str(category_to_move.id),
            "target_position": 2,
        },
        cookies=get_auth_cookie(admin_user),
    )
    assert response.status_code == 200
    data = response.json()

    # Verify order changed
    codes = [item["code"] for item in data["items"]]
    assert codes == ["cat_1", "cat_2", "cat_0"]


async def test_reorder_category_move_up(
    client: AsyncClient,
    admin_user: User,
    sample_categories: list[MetricCategory],
) -> None:
    """Test moving a category up (from position 2 to position 0)."""
    category_to_move = sample_categories[2]

    response = await client.patch(
        "/api/admin/metric-categories/reorder",
        json={
            "category_id": str(category_to_move.id),
            "target_position": 0,
        },
        cookies=get_auth_cookie(admin_user),
    )
    assert response.status_code == 200
    data = response.json()

    # Verify order changed
    codes = [item["code"] for item in data["items"]]
    assert codes == ["cat_2", "cat_0", "cat_1"]


async def test_reorder_category_same_position(
    client: AsyncClient,
    admin_user: User,
    sample_categories: list[MetricCategory],
) -> None:
    """Test moving a category to its current position (no-op)."""
    category_to_move = sample_categories[1]

    response = await client.patch(
        "/api/admin/metric-categories/reorder",
        json={
            "category_id": str(category_to_move.id),
            "target_position": 1,
        },
        cookies=get_auth_cookie(admin_user),
    )
    assert response.status_code == 200
    data = response.json()

    # Verify order unchanged
    codes = [item["code"] for item in data["items"]]
    assert codes == ["cat_0", "cat_1", "cat_2"]


async def test_reorder_category_auto_correct_negative_position(
    client: AsyncClient,
    admin_user: User,
    sample_categories: list[MetricCategory],
) -> None:
    """Test that negative target_position is rejected by Pydantic (ge=0)."""
    category_to_move = sample_categories[2]

    response = await client.patch(
        "/api/admin/metric-categories/reorder",
        json={
            "category_id": str(category_to_move.id),
            "target_position": -1,
        },
        cookies=get_auth_cookie(admin_user),
    )
    # Pydantic validation should fail
    assert response.status_code == 422


async def test_reorder_category_auto_correct_position_too_high(
    client: AsyncClient,
    admin_user: User,
    sample_categories: list[MetricCategory],
) -> None:
    """Test that position higher than max is auto-corrected to max."""
    category_to_move = sample_categories[0]

    response = await client.patch(
        "/api/admin/metric-categories/reorder",
        json={
            "category_id": str(category_to_move.id),
            "target_position": 100,  # Way beyond max (2)
        },
        cookies=get_auth_cookie(admin_user),
    )
    assert response.status_code == 200
    data = response.json()

    # Should be moved to last position (index 2)
    codes = [item["code"] for item in data["items"]]
    assert codes == ["cat_1", "cat_2", "cat_0"]


async def test_reorder_category_not_found(
    client: AsyncClient,
    admin_user: User,
    sample_categories: list[MetricCategory],
) -> None:
    """Test reordering a non-existent category returns 404."""
    fake_id = uuid.uuid4()

    response = await client.patch(
        "/api/admin/metric-categories/reorder",
        json={
            "category_id": str(fake_id),
            "target_position": 0,
        },
        cookies=get_auth_cookie(admin_user),
    )
    assert response.status_code == 404


async def test_reorder_category_requires_admin(
    client: AsyncClient,
    active_user: User,
    sample_categories: list[MetricCategory],
) -> None:
    """Test that reordering requires admin role."""
    category_to_move = sample_categories[0]

    response = await client.patch(
        "/api/admin/metric-categories/reorder",
        json={
            "category_id": str(category_to_move.id),
            "target_position": 2,
        },
        cookies=get_auth_cookie(active_user),
    )
    assert response.status_code == 403


async def test_reorder_route_not_matched_as_uuid(
    client: AsyncClient,
    admin_user: User,
) -> None:
    """Test that /reorder route is correctly matched (not as /{category_id})."""
    # This test ensures the route order fix works - "reorder" should NOT
    # be parsed as a UUID parameter
    response = await client.patch(
        "/api/admin/metric-categories/reorder",
        json={
            "category_id": str(uuid.uuid4()),
            "target_position": 0,
        },
        cookies=get_auth_cookie(admin_user),
    )
    # Should be 404 (category not found), NOT 422 (invalid UUID)
    assert response.status_code == 404


# CRUD Tests


async def test_create_category(
    client: AsyncClient,
    admin_user: User,
) -> None:
    """Test creating a new category."""
    response = await client.post(
        "/api/admin/metric-categories",
        json={
            "code": "new_cat",
            "name": "New Category",
            "description": "A new test category",
            "sort_order": 0,
        },
        cookies=get_auth_cookie(admin_user),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["code"] == "new_cat"
    assert data["name"] == "New Category"


async def test_create_category_duplicate_code(
    client: AsyncClient,
    admin_user: User,
    sample_categories: list[MetricCategory],
) -> None:
    """Test creating a category with duplicate code fails."""
    response = await client.post(
        "/api/admin/metric-categories",
        json={
            "code": "cat_0",  # Already exists
            "name": "Another Category",
        },
        cookies=get_auth_cookie(admin_user),
    )
    assert response.status_code == 400


async def test_get_category_by_id(
    client: AsyncClient,
    active_user: User,
    sample_categories: list[MetricCategory],
) -> None:
    """Test getting a category by ID."""
    category = sample_categories[0]

    response = await client.get(
        f"/api/admin/metric-categories/{category.id}",
        cookies=get_auth_cookie(active_user),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == category.code


async def test_update_category(
    client: AsyncClient,
    admin_user: User,
    sample_categories: list[MetricCategory],
) -> None:
    """Test updating a category."""
    category = sample_categories[0]

    response = await client.put(
        f"/api/admin/metric-categories/{category.id}",
        json={"name": "Updated Name"},
        cookies=get_auth_cookie(admin_user),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"


async def test_delete_category(
    client: AsyncClient,
    admin_user: User,
    sample_categories: list[MetricCategory],
) -> None:
    """Test deleting a category."""
    category = sample_categories[0]

    response = await client.delete(
        f"/api/admin/metric-categories/{category.id}",
        cookies=get_auth_cookie(admin_user),
    )
    assert response.status_code == 204


async def test_get_category_usage(
    client: AsyncClient,
    active_user: User,
    sample_categories: list[MetricCategory],
) -> None:
    """Test getting category usage statistics."""
    category = sample_categories[0]

    response = await client.get(
        f"/api/admin/metric-categories/{category.id}/usage",
        cookies=get_auth_cookie(active_user),
    )
    assert response.status_code == 200
    data = response.json()
    assert "metrics_count" in data
    assert "extracted_metrics_count" in data
