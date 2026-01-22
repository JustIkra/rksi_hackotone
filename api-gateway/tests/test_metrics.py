"""
Comprehensive tests for metrics module.

Tests cover:
- MetricDef CRUD operations (create, list, get, update, delete)
- ExtractedMetric CRUD operations per report
- Metric template generation
- Bulk metric creation
- Value validation against metric_def ranges
- Access control (authentication required)
- Filtering (active_only for metric definitions)

Markers:
- @pytest.mark.integration: Tests requiring database
"""

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FileRef, MetricDef, Participant, Report, User
from tests.conftest import get_auth_header

# Fixtures for test data

@pytest.fixture
async def sample_participant(db_session: AsyncSession) -> Participant:
    """Create a sample participant for testing."""
    participant = Participant(
        id=uuid.uuid4(),
        full_name="Test Participant",
        external_id="TEST-001",
    )
    db_session.add(participant)
    await db_session.commit()
    await db_session.refresh(participant)
    return participant


@pytest.fixture
async def sample_file_ref(db_session: AsyncSession) -> FileRef:
    """Create a sample file reference for testing."""
    file_ref = FileRef(
        id=uuid.uuid4(),
        storage="LOCAL",
        bucket="test",
        key="test/sample.docx",
        filename="sample.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        size_bytes=1024,
    )
    db_session.add(file_ref)
    await db_session.commit()
    await db_session.refresh(file_ref)
    return file_ref


@pytest.fixture
async def sample_report(
    db_session: AsyncSession,
    sample_participant: Participant,
    sample_file_ref: FileRef,
) -> Report:
    """Create a sample report for testing."""
    report = Report(
        id=uuid.uuid4(),
        participant_id=sample_participant.id,
        file_ref_id=sample_file_ref.id,
        status="UPLOADED",
    )
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)
    return report


@pytest.fixture
async def sample_metric_def(db_session: AsyncSession) -> MetricDef:
    """Create a sample metric definition with standard 1-10 range."""
    metric_def = MetricDef(
        id=uuid.uuid4(),
        code="test_metric_001",
        name="Test Metric 001",
        name_ru="Тестовая метрика 001",
        description="Test metric for unit tests",
        unit="points",
        min_value=Decimal("1.0"),
        max_value=Decimal("10.0"),
        active=True,
    )
    db_session.add(metric_def)
    await db_session.commit()
    await db_session.refresh(metric_def)
    return metric_def


@pytest.fixture
async def inactive_metric_def(db_session: AsyncSession) -> MetricDef:
    """Create an inactive metric definition."""
    metric_def = MetricDef(
        id=uuid.uuid4(),
        code="inactive_metric",
        name="Inactive Metric",
        name_ru="Неактивная метрика",
        description="Inactive metric for filtering tests",
        unit="points",
        min_value=Decimal("1.0"),
        max_value=Decimal("10.0"),
        active=False,
    )
    db_session.add(metric_def)
    await db_session.commit()
    await db_session.refresh(metric_def)
    return metric_def


# MetricDef Tests

@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_metric_def_success(client: AsyncClient, admin_user: User):
    """Test creating a metric definition with valid data. Requires ADMIN."""
    headers = get_auth_header(admin_user)
    payload = {
        "code": "new_metric",
        "name": "New Metric",
        "name_ru": "Новая метрика",
        "description": "A new test metric",
        "unit": "score",
        "min_value": 1.0,
        "max_value": 10.0,
        "active": True,
    }

    response = await client.post("/api/metric-defs", json=payload, headers=headers)

    assert response.status_code == 201
    data = response.json()
    assert data["code"] == "new_metric"
    assert data["name"] == "New Metric"
    assert data["name_ru"] == "Новая метрика"
    assert data["unit"] == "score"
    assert float(data["min_value"]) == 1.0
    assert float(data["max_value"]) == 10.0
    assert data["active"] is True
    assert "id" in data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_metric_def_duplicate_code(
    client: AsyncClient,
    admin_user: User,
    sample_metric_def: MetricDef,
):
    """Test creating a metric definition with duplicate code fails. Requires ADMIN."""
    headers = get_auth_header(admin_user)
    payload = {
        "code": sample_metric_def.code,  # Duplicate
        "name": "Duplicate Metric",
        "name_ru": "Дубликат",
    }

    response = await client.post("/api/metric-defs", json=payload, headers=headers)

    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_metric_def_invalid_range(client: AsyncClient, admin_user: User):
    """Test creating a metric definition with min > max fails. Requires ADMIN."""
    headers = get_auth_header(admin_user)
    payload = {
        "code": "invalid_range",
        "name": "Invalid Range",
        "min_value": 10.0,
        "max_value": 1.0,  # max < min
    }

    response = await client.post("/api/metric-defs", json=payload, headers=headers)

    assert response.status_code == 400
    assert "min_value" in response.json()["detail"].lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_metric_def_unauthorized(client: AsyncClient):
    """Test creating a metric definition without authentication fails."""
    payload = {
        "code": "unauthorized_metric",
        "name": "Unauthorized Metric",
    }

    response = await client.post("/api/metric-defs", json=payload)

    assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_metric_defs_all(
    client: AsyncClient,
    active_user: User,
    sample_metric_def: MetricDef,
    inactive_metric_def: MetricDef,
):
    """Test listing all metric definitions (active and inactive)."""
    headers = get_auth_header(active_user)

    response = await client.get("/api/metric-defs", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 2

    # Should include both active and inactive
    codes = [item["code"] for item in data["items"]]
    assert sample_metric_def.code in codes
    assert inactive_metric_def.code in codes


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_metric_defs_active_only(
    client: AsyncClient,
    active_user: User,
    sample_metric_def: MetricDef,
    inactive_metric_def: MetricDef,
):
    """Test listing only active metric definitions with active_only=true."""
    headers = get_auth_header(active_user)

    response = await client.get("/api/metric-defs?active_only=true", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert "items" in data

    # Should include only active metrics
    codes = [item["code"] for item in data["items"]]
    assert sample_metric_def.code in codes
    assert inactive_metric_def.code not in codes

    # All returned items should be active
    for item in data["items"]:
        assert item["active"] is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_metric_def_by_id(
    client: AsyncClient,
    active_user: User,
    sample_metric_def: MetricDef,
):
    """Test getting a metric definition by ID."""
    headers = get_auth_header(active_user)

    response = await client.get(
        f"/api/metric-defs/{sample_metric_def.id}",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(sample_metric_def.id)
    assert data["code"] == sample_metric_def.code
    assert data["name"] == sample_metric_def.name


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_metric_def_not_found(client: AsyncClient, active_user: User):
    """Test getting a non-existent metric definition returns 404."""
    headers = get_auth_header(active_user)
    fake_id = uuid.uuid4()

    response = await client.get(f"/api/metric-defs/{fake_id}", headers=headers)

    assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_metric_def(
    client: AsyncClient,
    admin_user: User,
    sample_metric_def: MetricDef,
):
    """Test updating a metric definition. Requires ADMIN."""
    headers = get_auth_header(admin_user)
    payload = {
        "name": "Updated Metric Name",
        "description": "Updated description",
        "active": False,
    }

    response = await client.put(
        f"/api/metric-defs/{sample_metric_def.id}",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Metric Name"
    assert data["description"] == "Updated description"
    assert data["active"] is False
    assert data["code"] == sample_metric_def.code  # Code unchanged


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_metric_def_not_found(client: AsyncClient, admin_user: User):
    """Test updating a non-existent metric definition returns 404. Requires ADMIN."""
    headers = get_auth_header(admin_user)
    fake_id = uuid.uuid4()
    payload = {"name": "Updated Name"}

    response = await client.put(
        f"/api/metric-defs/{fake_id}",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_metric_def(
    client: AsyncClient,
    admin_user: User,
    db_session: AsyncSession,
):
    """Test deleting a metric definition. Requires ADMIN."""
    # Create a metric def to delete
    metric_def = MetricDef(
        id=uuid.uuid4(),
        code="to_delete",
        name="To Delete",
        active=True,
    )
    db_session.add(metric_def)
    await db_session.commit()
    await db_session.refresh(metric_def)

    headers = get_auth_header(admin_user)

    response = await client.delete(
        f"/api/metric-defs/{metric_def.id}",
        headers=headers,
    )

    assert response.status_code == 200
    assert "deleted successfully" in response.json()["message"]

    # Verify deletion
    response = await client.get(f"/api/metric-defs/{metric_def.id}", headers=headers)
    assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_metric_def_not_found(client: AsyncClient, admin_user: User):
    """Test deleting a non-existent metric definition returns 404. Requires ADMIN."""
    headers = get_auth_header(admin_user)
    fake_id = uuid.uuid4()

    response = await client.delete(f"/api/metric-defs/{fake_id}", headers=headers)

    assert response.status_code == 404


# ExtractedMetric Tests

@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_metric_template(
    client: AsyncClient,
    active_user: User,
    sample_report: Report,
    sample_metric_def: MetricDef,
    inactive_metric_def: MetricDef,
):
    """Test getting metric template for a report."""
    headers = get_auth_header(active_user)

    response = await client.get(
        f"/api/reports/{sample_report.id}/metrics/template",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "filled_count" in data
    assert "missing_count" in data

    # Should only include active metrics
    codes = [item["metric_def"]["code"] for item in data["items"]]
    assert sample_metric_def.code in codes
    assert inactive_metric_def.code not in codes

    # Initially, all metrics should be unfilled
    assert data["filled_count"] == 0
    assert data["missing_count"] == data["total"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_metric_template_report_not_found(
    client: AsyncClient,
    active_user: User,
):
    """Test getting metric template for non-existent report returns 404."""
    headers = get_auth_header(active_user)
    fake_id = uuid.uuid4()

    response = await client.get(
        f"/api/reports/{fake_id}/metrics/template",
        headers=headers,
    )

    assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_extracted_metrics_empty(
    client: AsyncClient,
    active_user: User,
    sample_report: Report,
):
    """Test listing extracted metrics for a report with no metrics."""
    headers = get_auth_header(active_user)

    response = await client.get(
        f"/api/reports/{sample_report.id}/metrics",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_extracted_metric(
    client: AsyncClient,
    active_user: User,
    sample_report: Report,
    sample_metric_def: MetricDef,
):
    """Test creating an extracted metric for a report."""
    headers = get_auth_header(active_user)
    payload = {
        "metric_def_id": str(sample_metric_def.id),
        "value": 7.5,
        "source": "MANUAL",
        "confidence": 0.95,
        "notes": "Manual entry for testing",
    }

    response = await client.post(
        f"/api/reports/{sample_report.id}/metrics",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["report_id"] == str(sample_report.id)
    assert data["metric_def_id"] == str(sample_metric_def.id)
    assert float(data["value"]) == 7.5
    assert data["source"] == "MANUAL"
    assert float(data["confidence"]) == 0.95
    assert data["notes"] == "Manual entry for testing"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_extracted_metric_upsert_behavior(
    client: AsyncClient,
    active_user: User,
    sample_report: Report,
    sample_metric_def: MetricDef,
):
    """Test that creating a metric with same report+metric_def updates existing."""
    headers = get_auth_header(active_user)

    # Create first metric
    payload1 = {
        "metric_def_id": str(sample_metric_def.id),
        "value": 5.0,
        "source": "LLM",
    }
    response1 = await client.post(
        f"/api/reports/{sample_report.id}/metrics",
        json=payload1,
        headers=headers,
    )
    assert response1.status_code == 201
    first_id = response1.json()["id"]

    # Create again with same metric_def - should update
    payload2 = {
        "metric_def_id": str(sample_metric_def.id),
        "value": 8.0,
        "source": "MANUAL",
        "notes": "Updated value",
    }
    response2 = await client.post(
        f"/api/reports/{sample_report.id}/metrics",
        json=payload2,
        headers=headers,
    )
    assert response2.status_code == 201
    second_id = response2.json()["id"]

    # Should have same ID (updated, not created new)
    assert first_id == second_id
    assert float(response2.json()["value"]) == 8.0
    assert response2.json()["source"] == "MANUAL"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_extracted_metric_value_below_min(
    client: AsyncClient,
    active_user: User,
    sample_report: Report,
    sample_metric_def: MetricDef,
):
    """Test creating a metric with value below min_value fails."""
    headers = get_auth_header(active_user)
    payload = {
        "metric_def_id": str(sample_metric_def.id),
        "value": 0.5,  # Below min_value of 1.0
        "source": "MANUAL",
    }

    response = await client.post(
        f"/api/reports/{sample_report.id}/metrics",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 400
    assert "below minimum" in response.json()["detail"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_extracted_metric_value_above_max(
    client: AsyncClient,
    active_user: User,
    sample_report: Report,
    sample_metric_def: MetricDef,
):
    """Test creating a metric with value above max_value fails."""
    headers = get_auth_header(active_user)
    payload = {
        "metric_def_id": str(sample_metric_def.id),
        "value": 15.0,  # Above max_value of 10.0
        "source": "MANUAL",
    }

    response = await client.post(
        f"/api/reports/{sample_report.id}/metrics",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 400
    assert "above maximum" in response.json()["detail"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_extracted_metric_valid_boundary_values(
    client: AsyncClient,
    active_user: User,
    sample_report: Report,
    db_session: AsyncSession,
):
    """Test creating metrics with values at exact min and max boundaries."""
    # Create two metric defs to test both boundaries
    min_metric = MetricDef(
        id=uuid.uuid4(),
        code="min_test",
        name="Min Test",
        min_value=Decimal("1.0"),
        max_value=Decimal("10.0"),
        active=True,
    )
    max_metric = MetricDef(
        id=uuid.uuid4(),
        code="max_test",
        name="Max Test",
        min_value=Decimal("1.0"),
        max_value=Decimal("10.0"),
        active=True,
    )
    db_session.add_all([min_metric, max_metric])
    await db_session.commit()

    headers = get_auth_header(active_user)

    # Test min boundary
    response_min = await client.post(
        f"/api/reports/{sample_report.id}/metrics",
        json={
            "metric_def_id": str(min_metric.id),
            "value": 1.0,  # Exact min
            "source": "MANUAL",
        },
        headers=headers,
    )
    assert response_min.status_code == 201

    # Test max boundary
    response_max = await client.post(
        f"/api/reports/{sample_report.id}/metrics",
        json={
            "metric_def_id": str(max_metric.id),
            "value": 10.0,  # Exact max
            "source": "MANUAL",
        },
        headers=headers,
    )
    assert response_max.status_code == 201


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_extracted_metric_report_not_found(
    client: AsyncClient,
    active_user: User,
    sample_metric_def: MetricDef,
):
    """Test creating a metric for non-existent report returns 404."""
    headers = get_auth_header(active_user)
    fake_report_id = uuid.uuid4()
    payload = {
        "metric_def_id": str(sample_metric_def.id),
        "value": 5.0,
        "source": "MANUAL",
    }

    response = await client.post(
        f"/api/reports/{fake_report_id}/metrics",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 404
    assert "Report not found" in response.json()["detail"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_extracted_metric_metric_def_not_found(
    client: AsyncClient,
    active_user: User,
    sample_report: Report,
):
    """Test creating a metric with non-existent metric_def returns 404."""
    headers = get_auth_header(active_user)
    fake_metric_id = uuid.uuid4()
    payload = {
        "metric_def_id": str(fake_metric_id),
        "value": 5.0,
        "source": "MANUAL",
    }

    response = await client.post(
        f"/api/reports/{sample_report.id}/metrics",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 404
    assert "Metric definition not found" in response.json()["detail"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bulk_create_extracted_metrics(
    client: AsyncClient,
    active_user: User,
    sample_report: Report,
    db_session: AsyncSession,
):
    """Test bulk creating multiple extracted metrics."""
    # Create multiple metric definitions
    metric1 = MetricDef(
        id=uuid.uuid4(),
        code="bulk_1",
        name="Bulk Metric 1",
        min_value=Decimal("1.0"),
        max_value=Decimal("10.0"),
        active=True,
    )
    metric2 = MetricDef(
        id=uuid.uuid4(),
        code="bulk_2",
        name="Bulk Metric 2",
        min_value=Decimal("1.0"),
        max_value=Decimal("10.0"),
        active=True,
    )
    metric3 = MetricDef(
        id=uuid.uuid4(),
        code="bulk_3",
        name="Bulk Metric 3",
        min_value=Decimal("1.0"),
        max_value=Decimal("10.0"),
        active=True,
    )
    db_session.add_all([metric1, metric2, metric3])
    await db_session.commit()

    headers = get_auth_header(active_user)
    payload = {
        "metrics": [
            {
                "metric_def_id": str(metric1.id),
                "value": 7.0,
                "source": "LLM",
                "confidence": 0.9,
            },
            {
                "metric_def_id": str(metric2.id),
                "value": 8.5,
                "source": "LLM",
                "confidence": 0.85,
            },
            {
                "metric_def_id": str(metric3.id),
                "value": 6.0,
                "source": "LLM",
                "confidence": 0.75,
            },
        ]
    }

    response = await client.post(
        f"/api/reports/{sample_report.id}/metrics/bulk",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 200
    assert "3 metrics" in response.json()["message"]

    # Verify all metrics were created
    list_response = await client.get(
        f"/api/reports/{sample_report.id}/metrics",
        headers=headers,
    )
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 3


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bulk_create_with_invalid_value(
    client: AsyncClient,
    active_user: User,
    sample_report: Report,
    sample_metric_def: MetricDef,
    db_session: AsyncSession,
):
    """Test bulk create fails if any metric has invalid value."""
    metric2 = MetricDef(
        id=uuid.uuid4(),
        code="bulk_valid",
        name="Bulk Valid",
        min_value=Decimal("1.0"),
        max_value=Decimal("10.0"),
        active=True,
    )
    db_session.add(metric2)
    await db_session.commit()

    headers = get_auth_header(active_user)
    payload = {
        "metrics": [
            {
                "metric_def_id": str(sample_metric_def.id),
                "value": 5.0,  # Valid
                "source": "LLM",
            },
            {
                "metric_def_id": str(metric2.id),
                "value": 15.0,  # Invalid - above max
                "source": "LLM",
            },
        ]
    }

    response = await client.post(
        f"/api/reports/{sample_report.id}/metrics/bulk",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 400
    assert "above maximum" in response.json()["detail"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_extracted_metric(
    client: AsyncClient,
    active_user: User,
    sample_report: Report,
    sample_metric_def: MetricDef,
):
    """Test updating an extracted metric by report_id and metric_def_id."""
    headers = get_auth_header(active_user)

    # Create metric first
    create_payload = {
        "metric_def_id": str(sample_metric_def.id),
        "value": 5.0,
        "source": "LLM",
        "notes": "Initial value",
    }
    await client.post(
        f"/api/reports/{sample_report.id}/metrics",
        json=create_payload,
        headers=headers,
    )

    # Update the metric
    update_payload = {
        "value": 8.0,
        "notes": "Updated value",
    }
    response = await client.put(
        f"/api/reports/{sample_report.id}/metrics/{sample_metric_def.id}",
        json=update_payload,
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert float(data["value"]) == 8.0
    assert data["notes"] == "Updated value"
    assert data["source"] == "LLM"  # Source unchanged


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_extracted_metric_not_found(
    client: AsyncClient,
    active_user: User,
    sample_report: Report,
    sample_metric_def: MetricDef,
):
    """Test updating non-existent extracted metric returns 404."""
    headers = get_auth_header(active_user)
    payload = {
        "value": 8.0,
        "notes": "Should fail",
    }

    response = await client.put(
        f"/api/reports/{sample_report.id}/metrics/{sample_metric_def.id}",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_extracted_metric_invalid_value(
    client: AsyncClient,
    active_user: User,
    sample_report: Report,
    sample_metric_def: MetricDef,
):
    """Test updating a metric with invalid value fails."""
    headers = get_auth_header(active_user)

    # Create metric first
    await client.post(
        f"/api/reports/{sample_report.id}/metrics",
        json={
            "metric_def_id": str(sample_metric_def.id),
            "value": 5.0,
            "source": "MANUAL",
        },
        headers=headers,
    )

    # Try to update with invalid value
    payload = {
        "value": 20.0,  # Above max of 10.0
    }
    response = await client.put(
        f"/api/reports/{sample_report.id}/metrics/{sample_metric_def.id}",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 400
    assert "above maximum" in response.json()["detail"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_extracted_metric(
    client: AsyncClient,
    active_user: User,
    sample_report: Report,
    sample_metric_def: MetricDef,
):
    """Test deleting an extracted metric by ID."""
    headers = get_auth_header(active_user)

    # Create metric first
    create_response = await client.post(
        f"/api/reports/{sample_report.id}/metrics",
        json={
            "metric_def_id": str(sample_metric_def.id),
            "value": 5.0,
            "source": "MANUAL",
        },
        headers=headers,
    )
    metric_id = create_response.json()["id"]

    # Delete the metric
    delete_response = await client.delete(
        f"/api/extracted-metrics/{metric_id}",
        headers=headers,
    )

    assert delete_response.status_code == 200
    assert "deleted successfully" in delete_response.json()["message"]

    # Verify deletion
    list_response = await client.get(
        f"/api/reports/{sample_report.id}/metrics",
        headers=headers,
    )
    assert list_response.json()["total"] == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_extracted_metric_not_found(
    client: AsyncClient,
    active_user: User,
):
    """Test deleting non-existent extracted metric returns 404."""
    headers = get_auth_header(active_user)
    fake_id = uuid.uuid4()

    response = await client.delete(
        f"/api/extracted-metrics/{fake_id}",
        headers=headers,
    )

    assert response.status_code == 404


# Access Control Tests

@pytest.mark.integration
@pytest.mark.asyncio
async def test_metrics_require_authentication(
    client: AsyncClient,
    sample_report: Report,
):
    """Test that all metric endpoints require authentication."""
    # Test listing metric defs
    response = await client.get("/api/metric-defs")
    assert response.status_code == 401

    # Test getting metric template
    response = await client.get(f"/api/reports/{sample_report.id}/metrics/template")
    assert response.status_code == 401

    # Test listing extracted metrics
    response = await client.get(f"/api/reports/{sample_report.id}/metrics")
    assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pending_user_cannot_access_metrics(
    client: AsyncClient,
    pending_user: User,
    sample_report: Report,
):
    """Test that pending users cannot access metric endpoints."""
    headers = get_auth_header(pending_user)

    # Test listing metric defs
    response = await client.get("/api/metric-defs", headers=headers)
    assert response.status_code == 403

    # Test creating metric
    response = await client.post(
        f"/api/reports/{sample_report.id}/metrics",
        json={
            "metric_def_id": str(uuid.uuid4()),
            "value": 5.0,
            "source": "MANUAL",
        },
        headers=headers,
    )
    assert response.status_code == 403


# Integration Tests

@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_metric_workflow(
    client: AsyncClient,
    admin_user: User,
    sample_report: Report,
    db_session: AsyncSession,
):
    """Test complete workflow: create metric defs, extract metrics, update, delete. Requires ADMIN."""
    headers = get_auth_header(admin_user)

    # Step 1: Create metric definitions
    metric1_payload = {
        "code": "workflow_metric_1",
        "name": "Workflow Metric 1",
        "min_value": 1.0,
        "max_value": 10.0,
        "active": True,
    }
    metric1_response = await client.post(
        "/api/metric-defs",
        json=metric1_payload,
        headers=headers,
    )
    assert metric1_response.status_code == 201
    metric1_id = metric1_response.json()["id"]

    metric2_payload = {
        "code": "workflow_metric_2",
        "name": "Workflow Metric 2",
        "min_value": 1.0,
        "max_value": 10.0,
        "active": True,
    }
    metric2_response = await client.post(
        "/api/metric-defs",
        json=metric2_payload,
        headers=headers,
    )
    assert metric2_response.status_code == 201
    metric2_id = metric2_response.json()["id"]

    # Step 2: Get metric template (should show 2+ metrics)
    template_response = await client.get(
        f"/api/reports/{sample_report.id}/metrics/template",
        headers=headers,
    )
    assert template_response.status_code == 200
    template_data = template_response.json()
    assert template_data["total"] >= 2
    assert template_data["filled_count"] == 0

    # Step 3: Create extracted metrics
    extracted1 = await client.post(
        f"/api/reports/{sample_report.id}/metrics",
        json={
            "metric_def_id": metric1_id,
            "value": 7.5,
            "source": "LLM",
            "confidence": 0.9,
        },
        headers=headers,
    )
    assert extracted1.status_code == 201

    extracted2 = await client.post(
        f"/api/reports/{sample_report.id}/metrics",
        json={
            "metric_def_id": metric2_id,
            "value": 8.0,
            "source": "LLM",
            "confidence": 0.85,
        },
        headers=headers,
    )
    assert extracted2.status_code == 201

    # Step 4: List extracted metrics
    list_response = await client.get(
        f"/api/reports/{sample_report.id}/metrics",
        headers=headers,
    )
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 2

    # Step 5: Update an extracted metric
    update_response = await client.put(
        f"/api/reports/{sample_report.id}/metrics/{metric1_id}",
        json={"value": 9.0, "notes": "Corrected value"},
        headers=headers,
    )
    assert update_response.status_code == 200
    assert float(update_response.json()["value"]) == 9.0

    # Step 6: Get template again (should show filled metrics)
    template_response2 = await client.get(
        f"/api/reports/{sample_report.id}/metrics/template",
        headers=headers,
    )
    assert template_response2.status_code == 200
    template_data2 = template_response2.json()
    assert template_data2["filled_count"] == 2

    # Step 7: Delete one extracted metric
    delete_response = await client.delete(
        f"/api/extracted-metrics/{extracted2.json()['id']}",
        headers=headers,
    )
    assert delete_response.status_code == 200

    # Step 8: Verify only 1 metric remains
    final_list = await client.get(
        f"/api/reports/{sample_report.id}/metrics",
        headers=headers,
    )
    assert final_list.json()["total"] == 1
