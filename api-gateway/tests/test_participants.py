"""
Comprehensive tests for participant management endpoints.

Tests CRUD operations, pagination, filtering, metrics management,
scoring history, and final report generation.
"""

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    MetricDef,
    Participant,
    ParticipantMetric,
    ProfActivity,
    ScoringResult,
    WeightTable,
)
from tests.conftest import get_auth_header

# Fixtures


@pytest.fixture
async def sample_participant(db_session: AsyncSession) -> Participant:
    """Create a sample participant for testing."""
    participant = Participant(
        id=uuid.uuid4(),
        full_name="John Doe",
        birth_date=date(1990, 1, 15),
        external_id="EXT001",
        created_at=datetime.utcnow(),
    )
    db_session.add(participant)
    await db_session.commit()
    await db_session.refresh(participant)
    return participant


@pytest.fixture
async def sample_participants(db_session: AsyncSession) -> list[Participant]:
    """Create multiple participants for pagination/filtering tests."""
    participants = [
        Participant(
            id=uuid.uuid4(),
            full_name="Alice Smith",
            birth_date=date(1985, 3, 10),
            external_id="EXT100",
        ),
        Participant(
            id=uuid.uuid4(),
            full_name="Bob Johnson",
            birth_date=date(1992, 7, 22),
            external_id="EXT101",
        ),
        Participant(
            id=uuid.uuid4(),
            full_name="Charlie Brown",
            birth_date=date(1988, 11, 5),
            external_id="EXT102",
        ),
        Participant(
            id=uuid.uuid4(),
            full_name="Diana Prince",
            birth_date=date(1995, 2, 14),
            external_id=None,  # No external_id
        ),
        Participant(
            id=uuid.uuid4(),
            full_name="Eve Anderson",
            birth_date=None,  # No birth_date
            external_id="EXT103",
        ),
    ]
    for p in participants:
        db_session.add(p)
    await db_session.commit()
    for p in participants:
        await db_session.refresh(p)
    return participants


@pytest.fixture
async def metric_def(db_session: AsyncSession) -> MetricDef:
    """Create a sample metric definition."""
    metric = MetricDef(
        id=uuid.uuid4(),
        code="communication",
        name="Communication Skills",
        name_ru="Коммуникативные навыки",
        description="Ability to communicate effectively",
        unit="балл",
        min_value=Decimal("1"),
        max_value=Decimal("10"),
        active=True,
    )
    db_session.add(metric)
    await db_session.commit()
    await db_session.refresh(metric)
    return metric


@pytest.fixture
async def participant_with_metrics(
    db_session: AsyncSession, sample_participant: Participant, metric_def: MetricDef
) -> Participant:
    """Create a participant with associated metrics."""
    participant_metric = ParticipantMetric(
        id=uuid.uuid4(),
        participant_id=sample_participant.id,
        metric_code=metric_def.code,
        value=Decimal("8.5"),
        confidence=Decimal("0.95"),
        last_source_report_id=None,
        updated_at=datetime.utcnow(),
    )
    db_session.add(participant_metric)
    await db_session.commit()
    return sample_participant


@pytest.fixture
async def prof_activity_with_weights(db_session: AsyncSession) -> tuple[ProfActivity, WeightTable]:
    """Create a professional activity with weight table."""
    unique_code = f"developer_{uuid.uuid4().hex[:8]}"
    prof_activity = ProfActivity(
        id=uuid.uuid4(),
        code=unique_code,
        name="Software Developer",
        description="Software development professional",
    )
    db_session.add(prof_activity)
    await db_session.flush()

    weight_table = WeightTable(
        id=uuid.uuid4(),
        prof_activity_id=prof_activity.id,
        weights=[
            {"metric_code": "communication", "weight": 0.3},
            {"metric_code": "teamwork", "weight": 0.3},
            {"metric_code": "problem_solving", "weight": 0.4},
        ],
        metadata_json={"version": "1.0"},
        created_at=datetime.utcnow(),
    )
    db_session.add(weight_table)
    await db_session.commit()
    await db_session.refresh(prof_activity)
    await db_session.refresh(weight_table)
    return prof_activity, weight_table


@pytest.fixture
async def participant_with_scoring(
    db_session: AsyncSession,
    sample_participant: Participant,
    prof_activity_with_weights: tuple[ProfActivity, WeightTable],
) -> tuple[Participant, ScoringResult, ProfActivity]:
    """Create a participant with a scoring result."""
    prof_activity, weight_table = prof_activity_with_weights

    scoring_result = ScoringResult(
        id=uuid.uuid4(),
        participant_id=sample_participant.id,
        weight_table_id=weight_table.id,
        score_pct=Decimal("85.50"),
        strengths=[
            {
                "metric_code": "communication",
                "metric_name": "Communication",
                "value": "9.0",
                "weight": "0.3",
            }
        ],
        dev_areas=[
            {
                "metric_code": "teamwork",
                "metric_name": "Teamwork",
                "value": "6.0",
                "weight": "0.3",
            }
        ],
        computed_at=datetime.utcnow(),
        compute_notes="Test scoring",
    )
    db_session.add(scoring_result)
    await db_session.commit()
    await db_session.refresh(scoring_result)
    return sample_participant, scoring_result, prof_activity


# CREATE Tests


@pytest.mark.integration
async def test_create_participant_success(user_client: AsyncClient):
    """Test creating a new participant with valid data."""
    response = await user_client.post(
        "/api/participants",
        json={
            "full_name": "Test User",
            "birth_date": "1990-05-15",
            "external_id": "TEST001",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["full_name"] == "Test User"
    assert data["birth_date"] == "1990-05-15"
    assert data["external_id"] == "TEST001"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.integration
async def test_create_participant_minimal(user_client: AsyncClient):
    """Test creating a participant with only required fields."""
    response = await user_client.post(
        "/api/participants",
        json={"full_name": "Minimal User"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["full_name"] == "Minimal User"
    assert data["birth_date"] is None
    assert data["external_id"] is None


@pytest.mark.integration
async def test_create_participant_invalid_name(user_client: AsyncClient):
    """Test creating a participant with empty name fails validation."""
    response = await user_client.post(
        "/api/participants",
        json={"full_name": ""},
    )

    assert response.status_code == 422  # Validation error


@pytest.mark.integration
async def test_create_participant_name_too_long(user_client: AsyncClient):
    """Test creating a participant with name exceeding max length."""
    response = await user_client.post(
        "/api/participants",
        json={"full_name": "A" * 256},  # Max is 255
    )

    assert response.status_code == 422


@pytest.mark.integration
async def test_create_participant_unauthorized(client: AsyncClient):
    """Test creating a participant without authentication fails."""
    response = await client.post(
        "/api/participants",
        json={"full_name": "Test User"},
    )

    assert response.status_code == 401


@pytest.mark.integration
async def test_create_participant_pending_user(client: AsyncClient, pending_user):
    """Test creating a participant with pending user fails."""
    headers = get_auth_header(pending_user)
    response = await client.post(
        "/api/participants",
        json={"full_name": "Test User"},
        headers=headers,
    )

    assert response.status_code == 403  # Pending users are not ACTIVE


# READ Tests - List/Search


@pytest.mark.integration
async def test_list_participants_empty(user_client: AsyncClient):
    """Test listing participants when none exist."""
    response = await user_client.get("/api/participants")

    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["size"] == 20
    assert data["pages"] == 0


@pytest.mark.integration
async def test_list_participants(user_client: AsyncClient, sample_participants):
    """Test listing all participants with default pagination."""
    response = await user_client.get("/api/participants")

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 5
    assert data["total"] == 5
    assert data["page"] == 1
    assert data["size"] == 20
    assert data["pages"] == 1

    # Check sorting by full_name
    names = [item["full_name"] for item in data["items"]]
    assert names == sorted(names)


@pytest.mark.integration
async def test_list_participants_pagination(user_client: AsyncClient, sample_participants):
    """Test pagination with custom page size."""
    # Page 1, size 2
    response = await user_client.get("/api/participants?page=1&size=2")

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5
    assert data["page"] == 1
    assert data["size"] == 2
    assert data["pages"] == 3

    # Page 2
    response = await user_client.get("/api/participants?page=2&size=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["page"] == 2

    # Last page
    response = await user_client.get("/api/participants?page=3&size=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["page"] == 3


@pytest.mark.integration
async def test_search_participants_by_name(user_client: AsyncClient, sample_participants):
    """Test searching participants by full_name substring."""
    response = await user_client.get("/api/participants?query=alice")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["full_name"] == "Alice Smith"

    # Case insensitive
    response = await user_client.get("/api/participants?query=ALICE")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1


@pytest.mark.integration
async def test_search_participants_by_partial_name(user_client: AsyncClient, sample_participants):
    """Test searching with partial name match."""
    response = await user_client.get("/api/participants?query=son")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2  # Johnson, Anderson
    names = [item["full_name"] for item in data["items"]]
    assert "Bob Johnson" in names
    assert "Eve Anderson" in names


@pytest.mark.integration
async def test_filter_participants_by_external_id(user_client: AsyncClient, sample_participants):
    """Test filtering participants by exact external_id."""
    response = await user_client.get("/api/participants?external_id=EXT100")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["external_id"] == "EXT100"
    assert data["items"][0]["full_name"] == "Alice Smith"


@pytest.mark.integration
async def test_search_no_results(user_client: AsyncClient, sample_participants):
    """Test search with no matching results."""
    response = await user_client.get("/api/participants?query=nonexistent")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.integration
async def test_list_participants_invalid_page(user_client: AsyncClient):
    """Test invalid page number."""
    response = await user_client.get("/api/participants?page=0")

    assert response.status_code == 422  # Validation error


@pytest.mark.integration
async def test_list_participants_size_exceeds_max(user_client: AsyncClient):
    """Test page size exceeding maximum."""
    response = await user_client.get("/api/participants?size=101")

    assert response.status_code == 422  # Max is 100


# READ Tests - Get Single


@pytest.mark.integration
async def test_get_participant_success(user_client: AsyncClient, sample_participant: Participant):
    """Test retrieving a single participant by ID."""
    response = await user_client.get(f"/api/participants/{sample_participant.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(sample_participant.id)
    assert data["full_name"] == sample_participant.full_name
    assert data["external_id"] == sample_participant.external_id


@pytest.mark.integration
async def test_get_participant_not_found(user_client: AsyncClient):
    """Test retrieving non-existent participant returns 404."""
    non_existent_id = uuid.uuid4()
    response = await user_client.get(f"/api/participants/{non_existent_id}")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.integration
async def test_get_participant_invalid_uuid(user_client: AsyncClient):
    """Test retrieving participant with invalid UUID format."""
    response = await user_client.get("/api/participants/invalid-uuid")

    assert response.status_code == 422  # Validation error


@pytest.mark.integration
async def test_get_participant_unauthorized(client: AsyncClient, sample_participant: Participant):
    """Test retrieving participant without authentication."""
    response = await client.get(f"/api/participants/{sample_participant.id}")

    assert response.status_code == 401


# UPDATE Tests


@pytest.mark.integration
async def test_update_participant_full(user_client: AsyncClient, sample_participant: Participant):
    """Test updating all participant fields."""
    response = await user_client.put(
        f"/api/participants/{sample_participant.id}",
        json={
            "full_name": "Jane Doe Updated",
            "birth_date": "1991-06-20",
            "external_id": "EXT999",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(sample_participant.id)
    assert data["full_name"] == "Jane Doe Updated"
    assert data["birth_date"] == "1991-06-20"
    assert data["external_id"] == "EXT999"


@pytest.mark.integration
async def test_update_participant_partial(user_client: AsyncClient, sample_participant: Participant):
    """Test updating only some fields."""
    original_external_id = sample_participant.external_id

    response = await user_client.put(
        f"/api/participants/{sample_participant.id}",
        json={"full_name": "Updated Name Only"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Updated Name Only"
    assert data["external_id"] == original_external_id  # Unchanged


@pytest.mark.integration
async def test_update_participant_partial_update(
    user_client: AsyncClient, sample_participant: Participant
):
    """Test partial update keeps existing values when fields are not provided or null.

    Note: The current API design treats None as "not provided" rather than "clear value".
    This is intentional - to clear optional fields, a different endpoint or mechanism would be needed.
    """
    original_birth_date = sample_participant.birth_date
    original_external_id = sample_participant.external_id

    response = await user_client.put(
        f"/api/participants/{sample_participant.id}",
        json={
            "full_name": "Name Only",
            "birth_date": None,
            "external_id": None,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Name Only"
    # None values are treated as "not provided", so original values are preserved
    assert data["birth_date"] == str(original_birth_date) if original_birth_date else original_birth_date
    assert data["external_id"] == original_external_id


@pytest.mark.integration
async def test_update_participant_not_found(user_client: AsyncClient):
    """Test updating non-existent participant returns 404."""
    non_existent_id = uuid.uuid4()
    response = await user_client.put(
        f"/api/participants/{non_existent_id}",
        json={"full_name": "Test"},
    )

    assert response.status_code == 404


@pytest.mark.integration
async def test_update_participant_invalid_data(user_client: AsyncClient, sample_participant: Participant):
    """Test updating with invalid data fails validation."""
    response = await user_client.put(
        f"/api/participants/{sample_participant.id}",
        json={"full_name": ""},  # Empty name
    )

    assert response.status_code == 422


@pytest.mark.integration
async def test_update_participant_unauthorized(client: AsyncClient, sample_participant: Participant):
    """Test updating participant without authentication."""
    response = await client.put(
        f"/api/participants/{sample_participant.id}",
        json={"full_name": "Test"},
    )

    assert response.status_code == 401


# DELETE Tests


@pytest.mark.integration
async def test_delete_participant_success(
    user_client: AsyncClient, sample_participant: Participant
):
    """Test deleting a participant."""
    response = await user_client.delete(f"/api/participants/{sample_participant.id}")

    assert response.status_code == 200
    data = response.json()
    assert "deleted successfully" in data["message"].lower()

    # Verify deletion
    get_response = await user_client.get(f"/api/participants/{sample_participant.id}")
    assert get_response.status_code == 404


@pytest.mark.integration
async def test_delete_participant_not_found(user_client: AsyncClient):
    """Test deleting non-existent participant returns 404."""
    non_existent_id = uuid.uuid4()
    response = await user_client.delete(f"/api/participants/{non_existent_id}")

    assert response.status_code == 404


@pytest.mark.integration
async def test_delete_participant_unauthorized(client: AsyncClient, sample_participant: Participant):
    """Test deleting participant without authentication."""
    response = await client.delete(f"/api/participants/{sample_participant.id}")

    assert response.status_code == 401


# Participant Metrics Tests


@pytest.mark.integration
async def test_get_participant_metrics_empty(
    user_client: AsyncClient,
    sample_participant: Participant,
    metric_def: MetricDef,
):
    """Test getting metrics for participant with no metrics returns synthetic zeros."""
    response = await user_client.get(f"/api/participants/{sample_participant.id}/metrics")

    assert response.status_code == 200
    data = response.json()
    assert data["participant_id"] == str(sample_participant.id)
    assert len(data["metrics"]) >= 1  # At least the metric_def we created

    # Find the synthetic metric
    metric = next((m for m in data["metrics"] if m["metric_code"] == metric_def.code), None)
    assert metric is not None
    assert metric["value"] == 0.0
    assert metric["confidence"] is None
    assert metric["last_source_report_id"] is None


@pytest.mark.integration
async def test_get_participant_metrics_with_data(
    user_client: AsyncClient, participant_with_metrics: Participant, metric_def: MetricDef
):
    """Test getting metrics for participant with actual metrics."""
    response = await user_client.get(f"/api/participants/{participant_with_metrics.id}/metrics")

    assert response.status_code == 200
    data = response.json()
    assert data["participant_id"] == str(participant_with_metrics.id)
    assert data["total"] >= 1

    # Find the actual metric
    metric = next((m for m in data["metrics"] if m["metric_code"] == metric_def.code), None)
    assert metric is not None
    assert metric["value"] == 8.5
    assert metric["confidence"] == 0.95


@pytest.mark.integration
async def test_get_participant_metrics_not_found(user_client: AsyncClient):
    """Test getting metrics for non-existent participant."""
    non_existent_id = uuid.uuid4()
    response = await user_client.get(f"/api/participants/{non_existent_id}/metrics")

    assert response.status_code == 404


@pytest.mark.integration
async def test_update_participant_metric_success(
    user_client: AsyncClient,
    participant_with_metrics: Participant,
    metric_def: MetricDef,
):
    """Test manually updating a participant metric value."""
    response = await user_client.put(
        f"/api/participants/{participant_with_metrics.id}/metrics/{metric_def.code}",
        json={"value": 9.5, "confidence": 1.0},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["metric_code"] == metric_def.code
    assert data["value"] == 9.5
    assert data["confidence"] == 1.0


@pytest.mark.integration
async def test_update_participant_metric_without_confidence(
    user_client: AsyncClient,
    participant_with_metrics: Participant,
    metric_def: MetricDef,
):
    """Test updating metric value without confidence."""
    response = await user_client.put(
        f"/api/participants/{participant_with_metrics.id}/metrics/{metric_def.code}",
        json={"value": 7.0},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["value"] == 7.0


@pytest.mark.integration
async def test_update_participant_metric_invalid_value(
    user_client: AsyncClient,
    participant_with_metrics: Participant,
    metric_def: MetricDef,
):
    """Test updating metric with out-of-range value fails."""
    # Value < 1
    response = await user_client.put(
        f"/api/participants/{participant_with_metrics.id}/metrics/{metric_def.code}",
        json={"value": 0.5},
    )
    assert response.status_code == 422

    # Value > 10
    response = await user_client.put(
        f"/api/participants/{participant_with_metrics.id}/metrics/{metric_def.code}",
        json={"value": 10.5},
    )
    assert response.status_code == 422


@pytest.mark.integration
async def test_update_participant_metric_invalid_confidence(
    user_client: AsyncClient,
    participant_with_metrics: Participant,
    metric_def: MetricDef,
):
    """Test updating metric with invalid confidence fails."""
    response = await user_client.put(
        f"/api/participants/{participant_with_metrics.id}/metrics/{metric_def.code}",
        json={"value": 8.0, "confidence": 1.5},  # > 1
    )
    assert response.status_code == 422


@pytest.mark.integration
async def test_update_participant_metric_not_found(
    user_client: AsyncClient,
    sample_participant: Participant,
):
    """Test updating non-existent metric returns 404."""
    response = await user_client.put(
        f"/api/participants/{sample_participant.id}/metrics/nonexistent_metric",
        json={"value": 8.0},
    )

    assert response.status_code == 404


# Scoring History Tests


@pytest.mark.integration
async def test_get_scoring_history_empty(user_client: AsyncClient, sample_participant: Participant):
    """Test getting scoring history for participant with no scores."""
    response = await user_client.get(f"/api/participants/{sample_participant.id}/scores")

    assert response.status_code == 200
    data = response.json()
    assert data["results"] == []
    assert data["total"] == 0


@pytest.mark.integration
async def test_get_scoring_history_with_data(
    user_client: AsyncClient,
    participant_with_scoring: tuple[Participant, ScoringResult, ProfActivity],
):
    """Test getting scoring history with scoring results."""
    participant, scoring_result, prof_activity = participant_with_scoring

    response = await user_client.get(f"/api/participants/{participant.id}/scores")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["results"]) == 1

    result = data["results"][0]
    assert result["id"] == str(scoring_result.id)
    assert result["prof_activity_code"] == prof_activity.code
    assert result["score_pct"] == 85.5
    assert len(result["strengths"]) == 1
    assert len(result["dev_areas"]) == 1


@pytest.mark.integration
async def test_get_scoring_history_with_limit(
    user_client: AsyncClient,
    participant_with_scoring: tuple[Participant, ScoringResult, ProfActivity],
    db_session: AsyncSession,
):
    """Test scoring history with custom limit."""
    participant, first_result, _ = participant_with_scoring

    # Create second scoring result
    second_result = ScoringResult(
        id=uuid.uuid4(),
        participant_id=participant.id,
        weight_table_id=first_result.weight_table_id,
        score_pct=Decimal("90.00"),
        computed_at=datetime.utcnow() + timedelta(days=1),  # More recent
    )
    db_session.add(second_result)
    await db_session.commit()

    response = await user_client.get(f"/api/participants/{participant.id}/scores?limit=1")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    # Should return the most recent one
    assert data["results"][0]["score_pct"] == 90.0


@pytest.mark.integration
async def test_get_scoring_history_participant_not_found(user_client: AsyncClient):
    """Test getting scoring history for non-existent participant."""
    non_existent_id = uuid.uuid4()
    response = await user_client.get(f"/api/participants/{non_existent_id}/scores")

    assert response.status_code == 404


@pytest.mark.integration
async def test_get_scoring_history_invalid_limit(
    user_client: AsyncClient,
    sample_participant: Participant,
):
    """Test scoring history with invalid limit."""
    response = await user_client.get(f"/api/participants/{sample_participant.id}/scores?limit=0")
    assert response.status_code == 422

    response = await user_client.get(f"/api/participants/{sample_participant.id}/scores?limit=101")
    assert response.status_code == 422


# Final Report Tests


@pytest.mark.integration
async def test_get_final_report_json(
    user_client: AsyncClient,
    participant_with_scoring: tuple[Participant, ScoringResult, ProfActivity],
    db_session: AsyncSession,
    metric_def: MetricDef,
):
    """Test getting final report in JSON format."""
    participant, scoring_result, prof_activity = participant_with_scoring

    # Add participant metric to generate full report
    participant_metric = ParticipantMetric(
        id=uuid.uuid4(),
        participant_id=participant.id,
        metric_code="communication",
        value=Decimal("9.0"),
        confidence=Decimal("0.95"),
        updated_at=datetime.utcnow(),
    )
    db_session.add(participant_metric)
    await db_session.commit()

    response = await user_client.get(
        f"/api/participants/{participant.id}/final-report?activity_code={prof_activity.code}&format=json"
    )

    assert response.status_code == 200
    data = response.json()

    # Verify structure
    assert data["participant_id"] == str(participant.id)
    assert data["participant_name"] == participant.full_name
    assert data["prof_activity_code"] == prof_activity.code
    assert "score_pct" in data
    assert "strengths" in data
    assert "dev_areas" in data
    # recommendations field removed in cleanup
    assert "metrics" in data


@pytest.mark.integration
async def test_get_final_report_html(
    user_client: AsyncClient,
    participant_with_scoring: tuple[Participant, ScoringResult, ProfActivity],
    db_session: AsyncSession,
):
    """Test getting final report in HTML format."""
    participant, _, prof_activity = participant_with_scoring

    # Add participant metric
    participant_metric = ParticipantMetric(
        id=uuid.uuid4(),
        participant_id=participant.id,
        metric_code="communication",
        value=Decimal("9.0"),
        updated_at=datetime.utcnow(),
    )
    db_session.add(participant_metric)
    await db_session.commit()

    response = await user_client.get(
        f"/api/participants/{participant.id}/final-report?activity_code={prof_activity.code}&format=html"
    )

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert b"<!DOCTYPE html>" in response.content or b"<html" in response.content


@pytest.mark.integration
async def test_get_final_report_participant_not_found(user_client: AsyncClient):
    """Test final report for non-existent participant."""
    non_existent_id = uuid.uuid4()
    response = await user_client.get(
        f"/api/participants/{non_existent_id}/final-report?activity_code=developer"
    )

    # Should return 400 or 404 depending on the error
    assert response.status_code in [400, 404]


@pytest.mark.integration
async def test_get_final_report_no_weight_table(
    user_client: AsyncClient,
    sample_participant: Participant,
):
    """Test final report when no weight table exists for the activity.

    Note: The API validates weight table existence before checking for scoring results.
    """
    response = await user_client.get(
        f"/api/participants/{sample_participant.id}/final-report?activity_code=developer"
    )

    assert response.status_code == 400
    assert "weight table" in response.json()["detail"].lower()


@pytest.mark.integration
async def test_get_final_report_invalid_activity(
    user_client: AsyncClient,
    participant_with_scoring: tuple[Participant, ScoringResult, ProfActivity],
):
    """Test final report with non-existent activity code."""
    participant, _, _ = participant_with_scoring

    response = await user_client.get(
        f"/api/participants/{participant.id}/final-report?activity_code=nonexistent"
    )

    assert response.status_code == 400


@pytest.mark.integration
async def test_get_final_report_missing_activity_code(
    user_client: AsyncClient,
    sample_participant: Participant,
):
    """Test final report without activity_code parameter."""
    response = await user_client.get(f"/api/participants/{sample_participant.id}/final-report")

    assert response.status_code == 422  # Missing required parameter


# Authorization Tests


@pytest.mark.integration
async def test_participants_admin_access(admin_client: AsyncClient, sample_participant: Participant):
    """Test that admin users can access all participant endpoints."""
    # List
    response = await admin_client.get("/api/participants")
    assert response.status_code == 200

    # Get
    response = await admin_client.get(f"/api/participants/{sample_participant.id}")
    assert response.status_code == 200

    # Create
    response = await admin_client.post(
        "/api/participants",
        json={"full_name": "Admin Created"},
    )
    assert response.status_code == 201

    # Update
    response = await admin_client.put(
        f"/api/participants/{sample_participant.id}",
        json={"full_name": "Admin Updated"},
    )
    assert response.status_code == 200

    # Delete
    response = await admin_client.delete(f"/api/participants/{sample_participant.id}")
    assert response.status_code == 200


@pytest.mark.integration
async def test_participants_regular_user_access(
    user_client: AsyncClient, sample_participant: Participant
):
    """Test that regular users can access all participant endpoints."""
    # List
    response = await user_client.get("/api/participants")
    assert response.status_code == 200

    # Get
    response = await user_client.get(f"/api/participants/{sample_participant.id}")
    assert response.status_code == 200

    # Create
    response = await user_client.post(
        "/api/participants",
        json={"full_name": "User Created"},
    )
    assert response.status_code == 201

    # Update
    response = await user_client.put(
        f"/api/participants/{sample_participant.id}",
        json={"full_name": "User Updated"},
    )
    assert response.status_code == 200


# Edge Cases and Stress Tests


@pytest.mark.integration
async def test_create_many_participants(user_client: AsyncClient):
    """Test creating multiple participants in sequence."""
    created_ids = []
    for i in range(10):
        response = await user_client.post(
            "/api/participants",
            json={"full_name": f"Participant {i:03d}"},
        )
        assert response.status_code == 201
        created_ids.append(response.json()["id"])

    # Verify all created
    response = await user_client.get("/api/participants?size=20")
    assert response.status_code == 200
    assert response.json()["total"] == 10


@pytest.mark.integration
async def test_participant_with_unicode_name(user_client: AsyncClient):
    """Test creating participant with Unicode characters."""
    response = await user_client.post(
        "/api/participants",
        json={"full_name": "Иван Петрович Сидоров"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["full_name"] == "Иван Петрович Сидоров"


@pytest.mark.integration
async def test_search_participants_unicode(user_client: AsyncClient, db_session: AsyncSession):
    """Test searching participants with Cyrillic characters."""
    # Create participant with Cyrillic name
    participant = Participant(
        full_name="Александр Иванов",
        created_at=datetime.utcnow(),
    )
    db_session.add(participant)
    await db_session.commit()

    # Search case-insensitive
    response = await user_client.get("/api/participants?query=александр")
    assert response.status_code == 200
    assert response.json()["total"] == 1

    # Partial match
    response = await user_client.get("/api/participants?query=иван")
    assert response.status_code == 200
    assert response.json()["total"] == 1


@pytest.mark.integration
async def test_concurrent_metric_updates(
    user_client: AsyncClient,
    participant_with_metrics: Participant,
    metric_def: MetricDef,
):
    """Test updating the same metric multiple times (last write wins)."""
    # First update
    response = await user_client.put(
        f"/api/participants/{participant_with_metrics.id}/metrics/{metric_def.code}",
        json={"value": 5.0},
    )
    assert response.status_code == 200

    # Second update
    response = await user_client.put(
        f"/api/participants/{participant_with_metrics.id}/metrics/{metric_def.code}",
        json={"value": 7.0},
    )
    assert response.status_code == 200
    assert response.json()["value"] == 7.0

    # Verify final value
    response = await user_client.get(f"/api/participants/{participant_with_metrics.id}/metrics")
    metrics = response.json()["metrics"]
    metric = next(m for m in metrics if m["metric_code"] == metric_def.code)
    assert metric["value"] == 7.0
