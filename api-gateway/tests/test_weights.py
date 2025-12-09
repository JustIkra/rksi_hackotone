"""
Comprehensive tests for the weights management module.

Tests cover:
- Admin-only access control
- Weight table creation and validation
- Weight sum validation (must equal 1.0)
- Weight table updates
- Listing and filtering weight tables
- Edge cases and error scenarios
"""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ProfActivity, User, WeightTable
from app.repositories.prof_activity import ProfActivityRepository
from app.repositories.weight_table import WeightTableRepository

pytestmark = pytest.mark.asyncio


# Fixtures


@pytest_asyncio.fixture
async def prof_activity_developer(db_session: AsyncSession) -> ProfActivity:
    """Create a professional activity for testing."""
    repo = ProfActivityRepository(db_session)
    # Use unique code to avoid conflicts between tests
    unique_code = f"developer_{uuid.uuid4().hex[:8]}"
    activity = await repo.create(
        code=unique_code,
        name="Software Developer",
        description="Professional activity for software development",
    )
    return activity


@pytest_asyncio.fixture
async def prof_activity_analyst(db_session: AsyncSession) -> ProfActivity:
    """Create another professional activity for filtering tests."""
    repo = ProfActivityRepository(db_session)
    # Use unique code to avoid conflicts between tests
    unique_code = f"analyst_{uuid.uuid4().hex[:8]}"
    activity = await repo.create(
        code=unique_code,
        name="Business Analyst",
        description="Professional activity for business analysis",
    )
    return activity


@pytest_asyncio.fixture
async def weight_table_developer(
    db_session: AsyncSession,
    prof_activity_developer: ProfActivity,
) -> WeightTable:
    """Create a weight table for the developer activity."""
    repo = WeightTableRepository(db_session)
    weights = [
        {"metric_code": "m1", "weight": "0.4"},
        {"metric_code": "m2", "weight": "0.35"},
        {"metric_code": "m3", "weight": "0.25"},
    ]
    table = await repo.create(
        prof_activity_id=prof_activity_developer.id,
        weights=weights,
        metadata={"version": "1.0", "author": "test"},
    )
    return table


# Test: Admin-only access control


async def test_upload_weight_table_requires_admin(
    client: AsyncClient,
    active_user: User,
    prof_activity_developer: ProfActivity,
) -> None:
    """Regular users should not be able to upload weight tables."""
    from tests.conftest import get_auth_header

    payload = {
        "prof_activity_code": prof_activity_developer.code,
        "weights": [
            {"metric_code": "m1", "weight": "0.5"},
            {"metric_code": "m2", "weight": "0.5"},
        ],
        "metadata": {"version": "1.0"},
    }

    response = await client.post(
        "/api/admin/weights/upload",
        json=payload,
        headers=get_auth_header(active_user),
    )

    assert response.status_code == 403
    assert "detail" in response.json()


async def test_list_weight_tables_requires_admin(
    client: AsyncClient,
    active_user: User,
) -> None:
    """Regular users should not be able to list weight tables."""
    from tests.conftest import get_auth_header

    response = await client.get(
        "/api/admin/weights",
        headers=get_auth_header(active_user),
    )

    assert response.status_code == 403


async def test_update_weight_table_requires_admin(
    client: AsyncClient,
    active_user: User,
    weight_table_developer: WeightTable,
    prof_activity_developer: ProfActivity,
) -> None:
    """Regular users should not be able to update weight tables."""
    from tests.conftest import get_auth_header

    payload = {
        "prof_activity_code": prof_activity_developer.code,
        "weights": [
            {"metric_code": "m1", "weight": "0.6"},
            {"metric_code": "m2", "weight": "0.4"},
        ],
    }

    response = await client.put(
        f"/api/admin/weights/{weight_table_developer.id}",
        json=payload,
        headers=get_auth_header(active_user),
    )

    assert response.status_code == 403


# Test: Create weight table with valid weights


async def test_upload_weight_table_success(
    admin_client: AsyncClient,
    prof_activity_developer: ProfActivity,
) -> None:
    """Admin can successfully create a weight table with valid weights."""
    payload = {
        "prof_activity_code": prof_activity_developer.code,
        "weights": [
            {"metric_code": "m1", "weight": "0.5"},
            {"metric_code": "m2", "weight": "0.3"},
            {"metric_code": "m3", "weight": "0.2"},
        ],
        "metadata": {"version": "1.0", "author": "admin"},
    }

    response = await admin_client.post("/api/admin/weights/upload", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["prof_activity_code"] == prof_activity_developer.code
    assert data["prof_activity_name"] == prof_activity_developer.name
    assert len(data["weights"]) == 3
    assert data["metadata"]["version"] == "1.0"

    # Verify weights are returned correctly
    weights_by_code = {w["metric_code"]: Decimal(str(w["weight"])) for w in data["weights"]}
    assert weights_by_code["m1"] == Decimal("0.5")
    assert weights_by_code["m2"] == Decimal("0.3")
    assert weights_by_code["m3"] == Decimal("0.2")


async def test_upload_weight_table_with_exact_decimal_sum(
    admin_client: AsyncClient,
    prof_activity_developer: ProfActivity,
) -> None:
    """Weight table with weights that sum to exactly 1.0 is accepted."""
    payload = {
        "prof_activity_code": prof_activity_developer.code,
        "weights": [
            {"metric_code": "m1", "weight": "0.333"},
            {"metric_code": "m2", "weight": "0.333"},
            {"metric_code": "m3", "weight": "0.334"},
        ],
    }

    response = await admin_client.post("/api/admin/weights/upload", json=payload)

    assert response.status_code == 201
    data = response.json()
    weights_sum = sum(Decimal(str(w["weight"])) for w in data["weights"])
    assert weights_sum == Decimal("1.0")


async def test_upload_weight_table_updates_existing(
    admin_client: AsyncClient,
    prof_activity_developer: ProfActivity,
    weight_table_developer: WeightTable,
) -> None:
    """Uploading to an existing activity updates the weight table."""
    # First, verify the existing table
    assert weight_table_developer.prof_activity_id == prof_activity_developer.id

    # Upload new weights for the same activity
    payload = {
        "prof_activity_code": prof_activity_developer.code,
        "weights": [
            {"metric_code": "new_m1", "weight": "0.7"},
            {"metric_code": "new_m2", "weight": "0.3"},
        ],
        "metadata": {"version": "2.0", "updated_by": "admin"},
    }

    response = await admin_client.post("/api/admin/weights/upload", json=payload)

    assert response.status_code == 201
    data = response.json()

    # Should be the same weight table ID (updated)
    assert data["id"] == str(weight_table_developer.id)
    assert len(data["weights"]) == 2
    assert data["metadata"]["version"] == "2.0"


# Test: Weight sum validation


async def test_upload_weight_table_sum_not_one_rejected(
    admin_client: AsyncClient,
    prof_activity_developer: ProfActivity,
) -> None:
    """Weight table with sum != 1.0 is rejected."""
    payload = {
        "prof_activity_code": prof_activity_developer.code,
        "weights": [
            {"metric_code": "m1", "weight": "0.5"},
            {"metric_code": "m2", "weight": "0.3"},
            # Sum = 0.8, not 1.0
        ],
    }

    response = await admin_client.post("/api/admin/weights/upload", json=payload)

    assert response.status_code == 422  # Pydantic validation error
    error_data = response.json()
    assert "detail" in error_data


async def test_upload_weight_table_sum_exceeds_one_rejected(
    admin_client: AsyncClient,
    prof_activity_developer: ProfActivity,
) -> None:
    """Weight table with sum > 1.0 is rejected."""
    payload = {
        "prof_activity_code": prof_activity_developer.code,
        "weights": [
            {"metric_code": "m1", "weight": "0.6"},
            {"metric_code": "m2", "weight": "0.5"},
            # Sum = 1.1, exceeds 1.0
        ],
    }

    response = await admin_client.post("/api/admin/weights/upload", json=payload)

    assert response.status_code == 422
    error_data = response.json()
    assert "detail" in error_data


async def test_upload_weight_table_empty_weights_rejected(
    admin_client: AsyncClient,
    prof_activity_developer: ProfActivity,
) -> None:
    """Weight table with empty weights list is rejected."""
    payload = {
        "prof_activity_code": prof_activity_developer.code,
        "weights": [],
    }

    response = await admin_client.post("/api/admin/weights/upload", json=payload)

    assert response.status_code == 422


async def test_upload_weight_table_zero_weight_rejected(
    admin_client: AsyncClient,
    prof_activity_developer: ProfActivity,
) -> None:
    """Weights must be > 0."""
    payload = {
        "prof_activity_code": prof_activity_developer.code,
        "weights": [
            {"metric_code": "m1", "weight": "0"},
            {"metric_code": "m2", "weight": "1"},
        ],
    }

    response = await admin_client.post("/api/admin/weights/upload", json=payload)

    assert response.status_code == 422


async def test_upload_weight_table_negative_weight_rejected(
    admin_client: AsyncClient,
    prof_activity_developer: ProfActivity,
) -> None:
    """Negative weights are rejected."""
    payload = {
        "prof_activity_code": prof_activity_developer.code,
        "weights": [
            {"metric_code": "m1", "weight": "-0.5"},
            {"metric_code": "m2", "weight": "1.5"},
        ],
    }

    response = await admin_client.post("/api/admin/weights/upload", json=payload)

    assert response.status_code == 422


async def test_upload_weight_table_weight_exceeds_one_rejected(
    admin_client: AsyncClient,
    prof_activity_developer: ProfActivity,
) -> None:
    """Individual weights cannot exceed 1.0."""
    payload = {
        "prof_activity_code": prof_activity_developer.code,
        "weights": [
            {"metric_code": "m1", "weight": "1.1"},
        ],
    }

    response = await admin_client.post("/api/admin/weights/upload", json=payload)

    assert response.status_code == 422


# Test: Invalid professional activity


async def test_upload_weight_table_invalid_prof_activity(
    admin_client: AsyncClient,
) -> None:
    """Cannot create weight table for non-existent professional activity."""
    payload = {
        "prof_activity_code": "nonexistent_activity",
        "weights": [
            {"metric_code": "m1", "weight": "1.0"},
        ],
    }

    response = await admin_client.post("/api/admin/weights/upload", json=payload)

    assert response.status_code == 400
    error_data = response.json()
    assert "not found" in error_data["detail"].lower()


# Test: List weight tables


async def test_list_weight_tables_empty(
    admin_client: AsyncClient,
) -> None:
    """Listing weight tables when none exist returns empty list."""
    response = await admin_client.get("/api/admin/weights")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


async def test_list_weight_tables_success(
    admin_client: AsyncClient,
    weight_table_developer: WeightTable,
) -> None:
    """Admin can list all weight tables."""
    response = await admin_client.get("/api/admin/weights")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == str(weight_table_developer.id)
    assert len(data[0]["weights"]) == 3


async def test_list_weight_tables_multiple(
    admin_client: AsyncClient,
    prof_activity_developer: ProfActivity,
    prof_activity_analyst: ProfActivity,
    db_session: AsyncSession,
) -> None:
    """Listing returns all weight tables from multiple activities."""
    # Create weight tables for both activities
    repo = WeightTableRepository(db_session)

    await repo.create(
        prof_activity_id=prof_activity_developer.id,
        weights=[
            {"metric_code": "m1", "weight": "0.5"},
            {"metric_code": "m2", "weight": "0.5"},
        ],
        metadata=None,
    )

    await repo.create(
        prof_activity_id=prof_activity_analyst.id,
        weights=[
            {"metric_code": "m1", "weight": "0.3"},
            {"metric_code": "m2", "weight": "0.7"},
        ],
        metadata=None,
    )

    response = await admin_client.get("/api/admin/weights")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    # Verify both activities are present
    codes = {item["prof_activity_code"] for item in data}
    assert prof_activity_developer.code in codes
    assert prof_activity_analyst.code in codes


async def test_list_weight_tables_filter_by_prof_activity(
    admin_client: AsyncClient,
    prof_activity_developer: ProfActivity,
    prof_activity_analyst: ProfActivity,
    db_session: AsyncSession,
) -> None:
    """Can filter weight tables by professional activity code."""
    # Create weight tables for both activities
    repo = WeightTableRepository(db_session)

    await repo.create(
        prof_activity_id=prof_activity_developer.id,
        weights=[
            {"metric_code": "m1", "weight": "0.5"},
            {"metric_code": "m2", "weight": "0.5"},
        ],
        metadata=None,
    )

    await repo.create(
        prof_activity_id=prof_activity_analyst.id,
        weights=[
            {"metric_code": "m1", "weight": "0.3"},
            {"metric_code": "m2", "weight": "0.7"},
        ],
        metadata=None,
    )

    # Filter by developer
    response = await admin_client.get(
        "/api/admin/weights",
        params={"prof_activity_code": prof_activity_developer.code},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["prof_activity_code"] == prof_activity_developer.code


async def test_list_weight_tables_filter_invalid_activity(
    admin_client: AsyncClient,
) -> None:
    """Filtering by non-existent activity returns error."""
    response = await admin_client.get(
        "/api/admin/weights",
        params={"prof_activity_code": "nonexistent"},
    )

    assert response.status_code == 400
    error_data = response.json()
    assert "not found" in error_data["detail"].lower()


# Test: Update weight table


async def test_update_weight_table_success(
    admin_client: AsyncClient,
    weight_table_developer: WeightTable,
    prof_activity_developer: ProfActivity,
) -> None:
    """Admin can update an existing weight table."""
    payload = {
        "prof_activity_code": prof_activity_developer.code,
        "weights": [
            {"metric_code": "updated_m1", "weight": "0.6"},
            {"metric_code": "updated_m2", "weight": "0.4"},
        ],
        "metadata": {"version": "2.0", "updated": True},
    }

    response = await admin_client.put(
        f"/api/admin/weights/{weight_table_developer.id}",
        json=payload,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(weight_table_developer.id)
    assert len(data["weights"]) == 2
    assert data["metadata"]["version"] == "2.0"

    # Verify new weights
    weights_by_code = {w["metric_code"]: w["weight"] for w in data["weights"]}
    assert "updated_m1" in weights_by_code
    assert "updated_m2" in weights_by_code


async def test_update_weight_table_invalid_sum(
    admin_client: AsyncClient,
    weight_table_developer: WeightTable,
    prof_activity_developer: ProfActivity,
) -> None:
    """Update is rejected if weights don't sum to 1.0."""
    payload = {
        "prof_activity_code": prof_activity_developer.code,
        "weights": [
            {"metric_code": "m1", "weight": "0.5"},
            {"metric_code": "m2", "weight": "0.4"},
            # Sum = 0.9
        ],
    }

    response = await admin_client.put(
        f"/api/admin/weights/{weight_table_developer.id}",
        json=payload,
    )

    assert response.status_code == 422


async def test_update_weight_table_not_found(
    admin_client: AsyncClient,
    prof_activity_developer: ProfActivity,
) -> None:
    """Cannot update non-existent weight table."""
    non_existent_id = uuid.uuid4()

    payload = {
        "prof_activity_code": prof_activity_developer.code,
        "weights": [
            {"metric_code": "m1", "weight": "1.0"},
        ],
    }

    response = await admin_client.put(
        f"/api/admin/weights/{non_existent_id}",
        json=payload,
    )

    assert response.status_code == 400
    error_data = response.json()
    assert "not found" in error_data["detail"].lower()


async def test_update_weight_table_cannot_change_activity(
    admin_client: AsyncClient,
    weight_table_developer: WeightTable,
    prof_activity_analyst: ProfActivity,
) -> None:
    """Cannot change professional activity of existing weight table."""
    payload = {
        "prof_activity_code": prof_activity_analyst.code,  # Different activity
        "weights": [
            {"metric_code": "m1", "weight": "1.0"},
        ],
    }

    response = await admin_client.put(
        f"/api/admin/weights/{weight_table_developer.id}",
        json=payload,
    )

    assert response.status_code == 400
    error_data = response.json()
    assert "cannot change" in error_data["detail"].lower()


# Test: Edge cases


async def test_upload_weight_table_single_metric(
    admin_client: AsyncClient,
    prof_activity_developer: ProfActivity,
) -> None:
    """Weight table with single metric at weight 1.0 is valid."""
    payload = {
        "prof_activity_code": prof_activity_developer.code,
        "weights": [
            {"metric_code": "only_metric", "weight": "1.0"},
        ],
    }

    response = await admin_client.post("/api/admin/weights/upload", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert len(data["weights"]) == 1
    assert data["weights"][0]["weight"] == "1.0"


async def test_upload_weight_table_many_metrics(
    admin_client: AsyncClient,
    prof_activity_developer: ProfActivity,
) -> None:
    """Weight table with many metrics is valid if sum is 1.0."""
    # Create 10 metrics with equal weights
    weight_per_metric = Decimal("0.1")
    weights = [
        {"metric_code": f"m{i}", "weight": str(weight_per_metric)}
        for i in range(10)
    ]

    payload = {
        "prof_activity_code": prof_activity_developer.code,
        "weights": weights,
    }

    response = await admin_client.post("/api/admin/weights/upload", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert len(data["weights"]) == 10

    # Verify sum
    total = sum(Decimal(str(w["weight"])) for w in data["weights"])
    assert total == Decimal("1.0")


async def test_upload_weight_table_without_metadata(
    admin_client: AsyncClient,
    prof_activity_developer: ProfActivity,
) -> None:
    """Metadata is optional."""
    payload = {
        "prof_activity_code": prof_activity_developer.code,
        "weights": [
            {"metric_code": "m1", "weight": "0.5"},
            {"metric_code": "m2", "weight": "0.5"},
        ],
        # No metadata field
    }

    response = await admin_client.post("/api/admin/weights/upload", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["metadata"] is None


async def test_upload_weight_table_with_high_precision_decimals(
    admin_client: AsyncClient,
    prof_activity_developer: ProfActivity,
) -> None:
    """Weights with high decimal precision that sum to 1.0 are accepted."""
    payload = {
        "prof_activity_code": prof_activity_developer.code,
        "weights": [
            {"metric_code": "m1", "weight": "0.333333"},
            {"metric_code": "m2", "weight": "0.333333"},
            {"metric_code": "m3", "weight": "0.333334"},
        ],
    }

    response = await admin_client.post("/api/admin/weights/upload", json=payload)

    assert response.status_code == 201
    data = response.json()
    weights_sum = sum(Decimal(str(w["weight"])) for w in data["weights"])
    assert weights_sum == Decimal("1.0")


async def test_upload_weight_table_duplicate_metric_codes_allowed(
    admin_client: AsyncClient,
    prof_activity_developer: ProfActivity,
) -> None:
    """
    Duplicate metric codes in weights are allowed at API level.
    This may be a business rule to enforce separately.
    """
    payload = {
        "prof_activity_code": prof_activity_developer.code,
        "weights": [
            {"metric_code": "m1", "weight": "0.5"},
            {"metric_code": "m1", "weight": "0.5"},  # Duplicate
        ],
    }

    response = await admin_client.post("/api/admin/weights/upload", json=payload)

    # Currently accepted - adjust if business rules change
    assert response.status_code == 201
    data = response.json()
    assert len(data["weights"]) == 2


# Test: Unauthenticated access


async def test_upload_weight_table_unauthenticated(
    client: AsyncClient,
    prof_activity_developer: ProfActivity,
) -> None:
    """Unauthenticated requests are rejected."""
    payload = {
        "prof_activity_code": prof_activity_developer.code,
        "weights": [
            {"metric_code": "m1", "weight": "1.0"},
        ],
    }

    response = await client.post("/api/admin/weights/upload", json=payload)

    assert response.status_code == 401


async def test_list_weight_tables_unauthenticated(
    client: AsyncClient,
) -> None:
    """Unauthenticated requests are rejected."""
    response = await client.get("/api/admin/weights")

    assert response.status_code == 401


async def test_update_weight_table_unauthenticated(
    client: AsyncClient,
    weight_table_developer: WeightTable,
    prof_activity_developer: ProfActivity,
) -> None:
    """Unauthenticated requests are rejected."""
    payload = {
        "prof_activity_code": prof_activity_developer.code,
        "weights": [
            {"metric_code": "m1", "weight": "1.0"},
        ],
    }

    response = await client.put(
        f"/api/admin/weights/{weight_table_developer.id}",
        json=payload,
    )

    assert response.status_code == 401
