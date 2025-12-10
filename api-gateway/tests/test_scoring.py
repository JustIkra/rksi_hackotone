"""
Comprehensive tests for scoring module.

Tests cover:
- Score calculation formula: score_pct = Σ(value × weight) × 10
- Missing metrics error handling
- Missing weight table error handling
- Strengths and development areas generation
- Scoring history retrieval
- Access control
- Edge cases and validation

Markers:
- unit: Pure service-level tests
- integration: Tests requiring database and API
"""

import uuid
from decimal import Decimal
from datetime import datetime, UTC
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    User,
    Participant,
    ProfActivity,
    WeightTable,
    MetricDef,
    ParticipantMetric,
    ScoringResult,
)
from app.repositories.participant_metric import ParticipantMetricRepository
from app.repositories.prof_activity import ProfActivityRepository
from app.repositories.scoring_result import ScoringResultRepository
from app.services.scoring import ScoringService
from tests.conftest import get_auth_header


# Fixtures

@pytest_asyncio.fixture
async def mock_gemini_client():
    """Create a mock Gemini client for testing."""
    mock_client = MagicMock()
    # Mock generate_text method for recommendations
    mock_client.generate_text = AsyncMock(return_value="Mock AI response")
    return mock_client


@pytest_asyncio.fixture
async def developer_activity(db_session: AsyncSession) -> ProfActivity:
    """Create a professional activity for testing."""
    unique_code = f"developer_{uuid.uuid4().hex[:8]}"
    activity = ProfActivity(
        id=uuid.uuid4(),
        code=unique_code,
        name="Разработчик",
        description="Test activity for scoring",
    )
    db_session.add(activity)
    await db_session.commit()
    await db_session.refresh(activity)
    return activity


@pytest_asyncio.fixture
async def weight_table(db_session: AsyncSession, developer_activity: ProfActivity) -> WeightTable:
    """
    Create a weight table with 3 metrics.

    Weights sum to 1.0:
    - competency_1: 0.50
    - competency_2: 0.30
    - competency_3: 0.20
    """
    weights = [
        {"metric_code": "competency_1", "weight": "0.50"},
        {"metric_code": "competency_2", "weight": "0.30"},
        {"metric_code": "competency_3", "weight": "0.20"},
    ]

    weight_table = WeightTable(
        prof_activity_id=developer_activity.id,
        weights=weights,
        metadata_json={"version": "1.0", "notes": "Test weight table"},
    )
    db_session.add(weight_table)
    await db_session.commit()
    await db_session.refresh(weight_table)
    return weight_table


@pytest_asyncio.fixture
async def metric_defs(db_session: AsyncSession) -> list[MetricDef]:
    """Create metric definitions for testing."""
    metrics = [
        MetricDef(
            code="competency_1",
            name="Competency 1",
            name_ru="Компетенция 1",
            unit="балл",
            min_value=Decimal("1"),
            max_value=Decimal("10"),
            active=True,
        ),
        MetricDef(
            code="competency_2",
            name="Competency 2",
            name_ru="Компетенция 2",
            unit="балл",
            min_value=Decimal("1"),
            max_value=Decimal("10"),
            active=True,
        ),
        MetricDef(
            code="competency_3",
            name="Competency 3",
            name_ru="Компетенция 3",
            unit="балл",
            min_value=Decimal("1"),
            max_value=Decimal("10"),
            active=True,
        ),
    ]

    for metric in metrics:
        db_session.add(metric)

    await db_session.commit()

    for metric in metrics:
        await db_session.refresh(metric)

    return metrics


@pytest_asyncio.fixture
async def test_participant(db_session: AsyncSession) -> Participant:
    """Create a test participant."""
    participant = Participant(
        full_name="Test Participant",
        external_id="TEST001",
    )
    db_session.add(participant)
    await db_session.commit()
    await db_session.refresh(participant)
    return participant


@pytest_asyncio.fixture
async def participant_metrics(
    db_session: AsyncSession,
    test_participant: Participant,
    metric_defs: list[MetricDef],
) -> list[ParticipantMetric]:
    """
    Create participant metrics with specific values for predictable scoring.

    Values:
    - competency_1: 8.00 (weight 0.50)
    - competency_2: 6.00 (weight 0.30)
    - competency_3: 4.00 (weight 0.20)

    Expected score: (8 * 0.50 + 6 * 0.30 + 4 * 0.20) * 10 = (4 + 1.8 + 0.8) * 10 = 66.00
    """
    metrics = [
        ParticipantMetric(
            participant_id=test_participant.id,
            metric_code="competency_1",
            value=Decimal("8.00"),
            confidence=Decimal("0.95"),
        ),
        ParticipantMetric(
            participant_id=test_participant.id,
            metric_code="competency_2",
            value=Decimal("6.00"),
            confidence=Decimal("0.90"),
        ),
        ParticipantMetric(
            participant_id=test_participant.id,
            metric_code="competency_3",
            value=Decimal("4.00"),
            confidence=Decimal("0.85"),
        ),
    ]

    for metric in metrics:
        db_session.add(metric)

    await db_session.commit()

    for metric in metrics:
        await db_session.refresh(metric)

    return metrics


# Unit Tests for ScoringService

@pytest.mark.unit
@pytest.mark.asyncio
async def test_calculate_score_success(
    db_session: AsyncSession,
    test_participant: Participant,
    developer_activity: ProfActivity,
    weight_table: WeightTable,
    metric_defs: list[MetricDef],
    participant_metrics: list[ParticipantMetric],
    mock_gemini_client,
):
    """
    Test successful score calculation with correct formula.

    Formula: score_pct = Σ(value × weight) × 10
    Expected: (8 * 0.50 + 6 * 0.30 + 4 * 0.20) * 10 = (4 + 1.8 + 0.8) * 10 = 66.00
    """
    # Disable AI recommendations for this test to avoid Celery/network calls
    with patch("app.core.config.settings.ai_recommendations_enabled", False):
        service = ScoringService(db_session, gemini_client=None)

        result = await service.calculate_score(
            participant_id=test_participant.id,
            prof_activity_code=developer_activity.code,
        )

    # Verify score calculation
    assert result["score_pct"] == Decimal("66.00")

    # Verify result structure
    assert "scoring_result_id" in result
    assert result["prof_activity_id"] == str(developer_activity.id)
    assert result["prof_activity_name"] == "Разработчик"
    assert result["weight_table_id"] == str(weight_table.id)
    assert result["missing_metrics"] == []

    # Verify details breakdown
    assert len(result["details"]) == 3

    # Check individual contributions
    details_by_code = {d["metric_code"]: d for d in result["details"]}

    # competency_1: 8.00 * 0.50 = 4.00
    assert details_by_code["competency_1"]["value"] == "8.00"
    assert details_by_code["competency_1"]["weight"] == "0.50"
    assert details_by_code["competency_1"]["contribution"] == "4.00"

    # competency_2: 6.00 * 0.30 = 1.80
    assert details_by_code["competency_2"]["value"] == "6.00"
    assert details_by_code["competency_2"]["weight"] == "0.30"
    assert details_by_code["competency_2"]["contribution"] == "1.80"

    # competency_3: 4.00 * 0.20 = 0.80
    assert details_by_code["competency_3"]["value"] == "4.00"
    assert details_by_code["competency_3"]["weight"] == "0.20"
    assert details_by_code["competency_3"]["contribution"] == "0.80"

    # Verify strengths and dev_areas are generated
    assert "strengths" in result
    assert "dev_areas" in result
    assert len(result["strengths"]) > 0
    assert len(result["dev_areas"]) > 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_calculate_score_strengths_and_dev_areas(
    db_session: AsyncSession,
    test_participant: Participant,
    developer_activity: ProfActivity,
    weight_table: WeightTable,
    metric_defs: list[MetricDef],
    participant_metrics: list[ParticipantMetric],
    mock_gemini_client,
):
    """
    Test that strengths and development areas are correctly identified.

    Given metrics:
    - competency_1: 8.00 (highest - should be in strengths)
    - competency_2: 6.00 (middle)
    - competency_3: 4.00 (lowest - should be in dev_areas)
    """
    # Disable AI recommendations for this test
    with patch("app.core.config.settings.ai_recommendations_enabled", False):
        service = ScoringService(db_session, gemini_client=None)

        result = await service.calculate_score(
            participant_id=test_participant.id,
            prof_activity_code=developer_activity.code,
        )

    # Check strengths (should have highest value first)
    strengths = result["strengths"]
    assert len(strengths) >= 1
    assert strengths[0]["metric_code"] == "competency_1"
    assert strengths[0]["value"] == "8.00"
    assert strengths[0]["metric_name"] == "Компетенция 1"

    # Check dev_areas (should have lowest value first)
    dev_areas = result["dev_areas"]
    assert len(dev_areas) >= 1
    assert dev_areas[0]["metric_code"] == "competency_3"
    assert dev_areas[0]["value"] == "4.00"
    assert dev_areas[0]["metric_name"] == "Компетенция 3"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_calculate_score_missing_metrics(
    db_session: AsyncSession,
    test_participant: Participant,
    developer_activity: ProfActivity,
    weight_table: WeightTable,
    metric_defs: list[MetricDef],
):
    """
    Test error when required metrics are missing.

    Should raise ValueError with clear message about missing metrics.
    """
    service = ScoringService(db_session)

    # No participant_metrics created, so all metrics are missing
    with pytest.raises(ValueError) as exc_info:
        await service.calculate_score(
            participant_id=test_participant.id,
            prof_activity_code=developer_activity.code,
        )

    error_message = str(exc_info.value)
    assert "Missing extracted metrics for" in error_message
    assert "competency_1" in error_message or "competency_2" in error_message


@pytest.mark.unit
@pytest.mark.asyncio
async def test_calculate_score_partially_missing_metrics(
    db_session: AsyncSession,
    test_participant: Participant,
    developer_activity: ProfActivity,
    weight_table: WeightTable,
    metric_defs: list[MetricDef],
):
    """
    Test error when only some metrics are present.

    Should fail if ANY required metric is missing.
    """
    # Add only 2 out of 3 required metrics
    metrics = [
        ParticipantMetric(
            participant_id=test_participant.id,
            metric_code="competency_1",
            value=Decimal("8.00"),
            confidence=Decimal("0.95"),
        ),
        ParticipantMetric(
            participant_id=test_participant.id,
            metric_code="competency_2",
            value=Decimal("6.00"),
            confidence=Decimal("0.90"),
        ),
        # competency_3 is missing
    ]

    for metric in metrics:
        db_session.add(metric)
    await db_session.commit()

    service = ScoringService(db_session)

    with pytest.raises(ValueError) as exc_info:
        await service.calculate_score(
            participant_id=test_participant.id,
            prof_activity_code=developer_activity.code,
        )

    error_message = str(exc_info.value)
    assert "Missing extracted metrics for" in error_message
    assert "competency_3" in error_message


@pytest.mark.unit
@pytest.mark.asyncio
async def test_calculate_score_no_weight_table(
    db_session: AsyncSession,
    test_participant: Participant,
    developer_activity: ProfActivity,
    metric_defs: list[MetricDef],
    participant_metrics: list[ParticipantMetric],
):
    """
    Test error when no weight table exists for activity.

    Should raise ValueError with clear message.
    """
    # No weight_table fixture used, so none exists
    service = ScoringService(db_session)

    with pytest.raises(ValueError) as exc_info:
        await service.calculate_score(
            participant_id=test_participant.id,
            prof_activity_code=developer_activity.code,
        )

    error_message = str(exc_info.value)
    assert "No active weight table" in error_message
    assert developer_activity.code in error_message


@pytest.mark.unit
@pytest.mark.asyncio
async def test_calculate_score_invalid_activity(
    db_session: AsyncSession,
    test_participant: Participant,
):
    """
    Test error when professional activity doesn't exist.
    """
    service = ScoringService(db_session)

    with pytest.raises(ValueError) as exc_info:
        await service.calculate_score(
            participant_id=test_participant.id,
            prof_activity_code="nonexistent_activity",
        )

    error_message = str(exc_info.value)
    assert "Professional activity" in error_message
    assert "not found" in error_message


@pytest.mark.unit
@pytest.mark.asyncio
async def test_calculate_score_invalid_weight_sum(
    db_session: AsyncSession,
    test_participant: Participant,
    developer_activity: ProfActivity,
    metric_defs: list[MetricDef],
    participant_metrics: list[ParticipantMetric],
):
    """
    Test error when weight sum is not 1.0.

    Weights must sum to exactly 1.0 for valid scoring.
    """
    # Create weight table with invalid sum (0.90 instead of 1.0)
    invalid_weights = [
        {"metric_code": "competency_1", "weight": "0.40"},
        {"metric_code": "competency_2", "weight": "0.30"},
        {"metric_code": "competency_3", "weight": "0.20"},  # Sum = 0.90
    ]

    weight_table = WeightTable(
        prof_activity_id=developer_activity.id,
        weights=invalid_weights,
    )
    db_session.add(weight_table)
    await db_session.commit()

    service = ScoringService(db_session)

    with pytest.raises(ValueError) as exc_info:
        await service.calculate_score(
            participant_id=test_participant.id,
            prof_activity_code=developer_activity.code,
        )

    error_message = str(exc_info.value)
    assert "Sum of weights must equal 1.0" in error_message


@pytest.mark.unit
@pytest.mark.asyncio
async def test_database_rejects_metric_value_out_of_range(
    db_session: AsyncSession,
    test_participant: Participant,
):
    """
    Test that database CHECK constraint prevents metric values outside [1..10].

    The participant_metric table has a CHECK constraint 'participant_metric_value_range_check'
    that ensures values are between 1 and 10. This test verifies that constraint works.
    """
    from sqlalchemy.exc import IntegrityError

    # Try to create metric with invalid value (11 > 10)
    invalid_metric = ParticipantMetric(
        participant_id=test_participant.id,
        metric_code="test_metric",
        value=Decimal("11.00"),  # Invalid: > 10
        confidence=Decimal("0.95"),
    )
    db_session.add(invalid_metric)

    # Database should reject this with a CHECK constraint violation
    with pytest.raises(IntegrityError) as exc_info:
        await db_session.commit()

    # Verify it's the value range check that failed
    assert "participant_metric_value_range_check" in str(exc_info.value)

    # Rollback to clean up
    await db_session.rollback()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_calculate_score_edge_case_all_max_values(
    db_session: AsyncSession,
    test_participant: Participant,
    developer_activity: ProfActivity,
    weight_table: WeightTable,
    metric_defs: list[MetricDef],
    mock_gemini_client,
):
    """
    Test score calculation with all maximum values (10.00).

    Expected score: (10 * 0.50 + 10 * 0.30 + 10 * 0.20) * 10 = 100.00
    """
    # Create metrics with all max values
    metrics = [
        ParticipantMetric(
            participant_id=test_participant.id,
            metric_code="competency_1",
            value=Decimal("10.00"),
            confidence=Decimal("1.00"),
        ),
        ParticipantMetric(
            participant_id=test_participant.id,
            metric_code="competency_2",
            value=Decimal("10.00"),
            confidence=Decimal("1.00"),
        ),
        ParticipantMetric(
            participant_id=test_participant.id,
            metric_code="competency_3",
            value=Decimal("10.00"),
            confidence=Decimal("1.00"),
        ),
    ]

    for metric in metrics:
        db_session.add(metric)
    await db_session.commit()

    # Disable AI recommendations for this test
    with patch("app.core.config.settings.ai_recommendations_enabled", False):
        service = ScoringService(db_session, gemini_client=None)

        result = await service.calculate_score(
            participant_id=test_participant.id,
            prof_activity_code=developer_activity.code,
        )

    assert result["score_pct"] == Decimal("100.00")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_calculate_score_edge_case_all_min_values(
    db_session: AsyncSession,
    test_participant: Participant,
    developer_activity: ProfActivity,
    weight_table: WeightTable,
    metric_defs: list[MetricDef],
    mock_gemini_client,
):
    """
    Test score calculation with all minimum values (1.00).

    Expected score: (1 * 0.50 + 1 * 0.30 + 1 * 0.20) * 10 = 10.00
    """
    # Create metrics with all min values
    metrics = [
        ParticipantMetric(
            participant_id=test_participant.id,
            metric_code="competency_1",
            value=Decimal("1.00"),
            confidence=Decimal("1.00"),
        ),
        ParticipantMetric(
            participant_id=test_participant.id,
            metric_code="competency_2",
            value=Decimal("1.00"),
            confidence=Decimal("1.00"),
        ),
        ParticipantMetric(
            participant_id=test_participant.id,
            metric_code="competency_3",
            value=Decimal("1.00"),
            confidence=Decimal("1.00"),
        ),
    ]

    for metric in metrics:
        db_session.add(metric)
    await db_session.commit()

    # Disable AI recommendations for this test
    with patch("app.core.config.settings.ai_recommendations_enabled", False):
        service = ScoringService(db_session, gemini_client=None)

        result = await service.calculate_score(
            participant_id=test_participant.id,
            prof_activity_code=developer_activity.code,
        )

    assert result["score_pct"] == Decimal("10.00")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_calculate_score_persists_to_database(
    db_session: AsyncSession,
    test_participant: Participant,
    developer_activity: ProfActivity,
    weight_table: WeightTable,
    metric_defs: list[MetricDef],
    participant_metrics: list[ParticipantMetric],
    mock_gemini_client,
):
    """
    Test that scoring result is saved to database.
    """
    # Disable AI recommendations for this test
    with patch("app.core.config.settings.ai_recommendations_enabled", False):
        service = ScoringService(db_session, gemini_client=None)

        result = await service.calculate_score(
            participant_id=test_participant.id,
            prof_activity_code=developer_activity.code,
        )

    # Verify result was saved to database
    scoring_result_id = uuid.UUID(result["scoring_result_id"])

    scoring_repo = ScoringResultRepository(db_session)
    saved_result = await scoring_repo.get_by_id(scoring_result_id)

    assert saved_result is not None
    assert saved_result.participant_id == test_participant.id
    assert saved_result.weight_table_id == weight_table.id
    assert saved_result.score_pct == Decimal("66.00")
    assert saved_result.strengths is not None
    assert saved_result.dev_areas is not None


# Integration Tests for API Endpoints

@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_calculate_score_success(
    client: AsyncClient,
    active_user: User,
    test_participant: Participant,
    developer_activity: ProfActivity,
    weight_table: WeightTable,
    metric_defs: list[MetricDef],
    participant_metrics: list[ParticipantMetric],
    mock_gemini_client,
):
    """
    Test POST /api/scoring/participants/{id}/calculate endpoint success.
    """
    headers = get_auth_header(active_user)

    # Mock the gemini client dependency and disable AI recommendations
    with patch("app.core.config.settings.ai_recommendations_enabled", False):
        with patch("app.core.gemini_factory.get_gemini_client", return_value=None):
            response = await client.post(
                f"/api/scoring/participants/{test_participant.id}/calculate",
                params={"activity_code": developer_activity.code},
                headers=headers,
            )

    assert response.status_code == 200

    data = response.json()

    # Verify response structure
    assert "scoring_result_id" in data
    assert data["participant_id"] == str(test_participant.id)
    assert data["prof_activity_code"] == developer_activity.code
    assert data["prof_activity_name"] == "Разработчик"
    assert data["score_pct"] == "66.00"
    assert data["weight_table_id"] == str(weight_table.id)
    assert data["missing_metrics"] == []

    # Verify details
    assert len(data["details"]) == 3

    # Verify strengths and dev_areas
    assert len(data["strengths"]) > 0
    assert len(data["dev_areas"]) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_calculate_score_missing_metrics(
    client: AsyncClient,
    active_user: User,
    test_participant: Participant,
    developer_activity: ProfActivity,
    weight_table: WeightTable,
    metric_defs: list[MetricDef],
):
    """
    Test API error response when metrics are missing.
    """
    headers = get_auth_header(active_user)

    # No participant_metrics, so all are missing
    response = await client.post(
        f"/api/scoring/participants/{test_participant.id}/calculate",
        params={"activity_code": developer_activity.code},
        headers=headers,
    )

    assert response.status_code == 400

    data = response.json()
    assert "detail" in data
    assert "Missing extracted metrics" in data["detail"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_calculate_score_no_weight_table(
    client: AsyncClient,
    active_user: User,
    test_participant: Participant,
    developer_activity: ProfActivity,
    metric_defs: list[MetricDef],
    participant_metrics: list[ParticipantMetric],
):
    """
    Test API error response when weight table is missing.
    """
    headers = get_auth_header(active_user)

    # No weight_table fixture, so none exists
    response = await client.post(
        f"/api/scoring/participants/{test_participant.id}/calculate",
        params={"activity_code": developer_activity.code},
        headers=headers,
    )

    assert response.status_code == 400

    data = response.json()
    assert "detail" in data
    assert "No active weight table" in data["detail"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_calculate_score_invalid_participant(
    client: AsyncClient,
    active_user: User,
    developer_activity: ProfActivity,
    weight_table: WeightTable,
):
    """
    Test API error with non-existent participant.

    Note: The service doesn't validate participant existence before calculating,
    it will fail with missing metrics instead. This test documents current behavior.
    """
    headers = get_auth_header(active_user)

    fake_participant_id = uuid.uuid4()

    response = await client.post(
        f"/api/scoring/participants/{fake_participant_id}/calculate",
        params={"activity_code": developer_activity.code},
        headers=headers,
    )

    # Will fail with 400 due to missing metrics
    assert response.status_code == 400


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_calculate_score_unauthorized(
    client: AsyncClient,
    test_participant: Participant,
    developer_activity: ProfActivity,
    weight_table: WeightTable,
    participant_metrics: list[ParticipantMetric],
):
    """
    Test that unauthorized users cannot calculate scores.
    """
    # No auth headers
    response = await client.post(
        f"/api/scoring/participants/{test_participant.id}/calculate",
        params={"activity_code": developer_activity.code},
    )

    assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_get_scoring_history_success(
    client: AsyncClient,
    active_user: User,
    db_session: AsyncSession,
    test_participant: Participant,
    developer_activity: ProfActivity,
    weight_table: WeightTable,
):
    """
    Test GET /api/scoring/participants/{id}/scores endpoint.
    """
    # Create some scoring results
    scoring_repo = ScoringResultRepository(db_session)

    result1 = await scoring_repo.create(
        participant_id=test_participant.id,
        weight_table_id=weight_table.id,
        score_pct=Decimal("75.50"),
        strengths=[{"metric_code": "competency_1", "value": "9.00", "weight": "0.50", "metric_name": "Компетенция 1"}],
        dev_areas=[{"metric_code": "competency_3", "value": "5.00", "weight": "0.20", "metric_name": "Компетенция 3"}],
        recommendations=[],
    )

    result2 = await scoring_repo.create(
        participant_id=test_participant.id,
        weight_table_id=weight_table.id,
        score_pct=Decimal("82.00"),
        strengths=[{"metric_code": "competency_1", "value": "10.00", "weight": "0.50", "metric_name": "Компетенция 1"}],
        dev_areas=[{"metric_code": "competency_2", "value": "6.00", "weight": "0.30", "metric_name": "Компетенция 2"}],
        recommendations=[],
    )

    headers = get_auth_header(active_user)

    response = await client.get(
        f"/api/scoring/participants/{test_participant.id}/scores",
        headers=headers,
    )

    assert response.status_code == 200

    data = response.json()

    # Verify response structure
    assert "items" in data
    items = data["items"]

    # Should have 2 results
    assert len(items) == 2

    # Collect result IDs and scores for verification (order may vary due to timing)
    result_ids = {item["id"] for item in items}
    result_scores = {item["score_pct"] for item in items}

    # Verify both results are present
    assert str(result1.id) in result_ids
    assert str(result2.id) in result_ids
    assert "75.50" in result_scores
    assert "82.00" in result_scores

    # Verify common fields on any item
    assert items[0]["participant_id"] == str(test_participant.id)
    assert items[0]["prof_activity_code"] == developer_activity.code


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_get_scoring_history_with_limit(
    client: AsyncClient,
    active_user: User,
    db_session: AsyncSession,
    test_participant: Participant,
    developer_activity: ProfActivity,
    weight_table: WeightTable,
):
    """
    Test that limit parameter works correctly.
    """
    # Create 5 scoring results
    scoring_repo = ScoringResultRepository(db_session)

    for i in range(5):
        await scoring_repo.create(
            participant_id=test_participant.id,
            weight_table_id=weight_table.id,
            score_pct=Decimal(f"{60 + i}.00"),
            strengths=[],
            dev_areas=[],
            recommendations=[],
        )

    headers = get_auth_header(active_user)

    # Request only 3 results
    response = await client.get(
        f"/api/scoring/participants/{test_participant.id}/scores",
        params={"limit": 3},
        headers=headers,
    )

    assert response.status_code == 200

    data = response.json()
    items = data["items"]

    # Should have exactly 3 results
    assert len(items) == 3


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_get_scoring_history_empty(
    client: AsyncClient,
    active_user: User,
    test_participant: Participant,
):
    """
    Test scoring history for participant with no results.
    """
    headers = get_auth_header(active_user)

    response = await client.get(
        f"/api/scoring/participants/{test_participant.id}/scores",
        headers=headers,
    )

    assert response.status_code == 200

    data = response.json()
    assert data["items"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_get_scoring_history_nonexistent_participant(
    client: AsyncClient,
    active_user: User,
):
    """
    Test error response for non-existent participant.
    """
    headers = get_auth_header(active_user)

    fake_participant_id = uuid.uuid4()

    response = await client.get(
        f"/api/scoring/participants/{fake_participant_id}/scores",
        headers=headers,
    )

    assert response.status_code == 404

    data = response.json()
    assert "detail" in data
    assert "Participant not found" in data["detail"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_get_scoring_history_unauthorized(
    client: AsyncClient,
    test_participant: Participant,
):
    """
    Test that unauthorized users cannot access scoring history.
    """
    # No auth headers
    response = await client.get(
        f"/api/scoring/participants/{test_participant.id}/scores",
    )

    assert response.status_code == 401


# Edge Cases and Boundary Tests

@pytest.mark.unit
@pytest.mark.asyncio
async def test_strengths_and_dev_areas_max_five_items(
    db_session: AsyncSession,
    test_participant: Participant,
    developer_activity: ProfActivity,
    mock_gemini_client,
):
    """
    Test that strengths and dev_areas are limited to 5 items each.
    """
    # Create weight table with 10 metrics
    weights = [
        {"metric_code": f"metric_{i}", "weight": "0.10"}
        for i in range(10)
    ]

    weight_table = WeightTable(
        prof_activity_id=developer_activity.id,
        weights=weights,
    )
    db_session.add(weight_table)
    await db_session.commit()

    # Create 10 metric definitions
    for i in range(10):
        metric_def = MetricDef(
            code=f"metric_{i}",
            name=f"Metric {i}",
            name_ru=f"Метрика {i}",
            unit="балл",
            min_value=Decimal("1"),
            max_value=Decimal("10"),
            active=True,
        )
        db_session.add(metric_def)

    await db_session.commit()

    # Create participant metrics with different values
    for i in range(10):
        metric = ParticipantMetric(
            participant_id=test_participant.id,
            metric_code=f"metric_{i}",
            value=Decimal(f"{i + 1}.00"),  # Values from 1.00 to 10.00
            confidence=Decimal("0.90"),
        )
        db_session.add(metric)

    await db_session.commit()

    # Disable AI recommendations for this test
    with patch("app.core.config.settings.ai_recommendations_enabled", False):
        service = ScoringService(db_session, gemini_client=None)

        result = await service.calculate_score(
            participant_id=test_participant.id,
            prof_activity_code=developer_activity.code,
        )

    # Verify max 5 items in each list
    assert len(result["strengths"]) == 5
    assert len(result["dev_areas"]) == 5

    # Verify correct ordering (highest first for strengths, lowest first for dev_areas)
    strength_values = [Decimal(s["value"]) for s in result["strengths"]]
    assert strength_values == sorted(strength_values, reverse=True)

    dev_area_values = [Decimal(d["value"]) for d in result["dev_areas"]]
    assert dev_area_values == sorted(dev_area_values)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_score_decimal_precision(
    db_session: AsyncSession,
    test_participant: Participant,
    developer_activity: ProfActivity,
    metric_defs: list[MetricDef],
    mock_gemini_client,
):
    """
    Test that score is properly quantized to 0.01 precision.
    """
    # Create weights that produce repeating decimal
    weights = [
        {"metric_code": "competency_1", "weight": "0.333333"},
        {"metric_code": "competency_2", "weight": "0.333333"},
        {"metric_code": "competency_3", "weight": "0.333334"},  # Sum = 1.0
    ]

    weight_table = WeightTable(
        prof_activity_id=developer_activity.id,
        weights=weights,
    )
    db_session.add(weight_table)
    await db_session.commit()

    # Create metrics
    metrics = [
        ParticipantMetric(
            participant_id=test_participant.id,
            metric_code="competency_1",
            value=Decimal("7.77"),
            confidence=Decimal("0.95"),
        ),
        ParticipantMetric(
            participant_id=test_participant.id,
            metric_code="competency_2",
            value=Decimal("8.88"),
            confidence=Decimal("0.90"),
        ),
        ParticipantMetric(
            participant_id=test_participant.id,
            metric_code="competency_3",
            value=Decimal("9.99"),
            confidence=Decimal("0.85"),
        ),
    ]

    for metric in metrics:
        db_session.add(metric)
    await db_session.commit()

    # Disable AI recommendations for this test
    with patch("app.core.config.settings.ai_recommendations_enabled", False):
        service = ScoringService(db_session, gemini_client=None)

        result = await service.calculate_score(
            participant_id=test_participant.id,
            prof_activity_code=developer_activity.code,
        )

    # Verify score has exactly 2 decimal places
    score = result["score_pct"]
    assert isinstance(score, Decimal)
    assert score.as_tuple().exponent == -2  # 2 decimal places


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multiple_scoring_calculations_create_history(
    client: AsyncClient,
    active_user: User,
    db_session: AsyncSession,
    test_participant: Participant,
    developer_activity: ProfActivity,
    weight_table: WeightTable,
    metric_defs: list[MetricDef],
    participant_metrics: list[ParticipantMetric],
    mock_gemini_client,
):
    """
    Test that multiple score calculations create separate history entries.
    """
    headers = get_auth_header(active_user)

    # Mock the gemini client dependency and disable AI recommendations
    with patch("app.core.config.settings.ai_recommendations_enabled", False):
        with patch("app.core.gemini_factory.get_gemini_client", return_value=None):
            # Calculate score multiple times
            for _ in range(3):
                response = await client.post(
                    f"/api/scoring/participants/{test_participant.id}/calculate",
                    params={"activity_code": developer_activity.code},
                    headers=headers,
                )
                assert response.status_code == 200

    # Get scoring history
    response = await client.get(
        f"/api/scoring/participants/{test_participant.id}/scores",
        headers=headers,
    )

    assert response.status_code == 200

    data = response.json()
    items = data["items"]

    # Should have 3 separate scoring results
    assert len(items) == 3

    # All should have the same score (since metrics didn't change)
    for item in items:
        assert item["score_pct"] == "66.00"
