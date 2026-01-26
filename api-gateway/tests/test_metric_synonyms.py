"""
Comprehensive tests for metric synonyms module.

Tests cover:
- MetricSynonym CRUD operations (create, list, get, update, delete)
- Global uniqueness constraint validation
- Access control (ADMIN role required)
- Cascade delete with metric_def

Markers:
- @pytest.mark.integration: Tests requiring database
"""

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MetricDef, MetricSynonym, User
from tests.conftest import get_auth_header


# Fixtures for test data

@pytest.fixture
async def test_metric_def(db_session: AsyncSession) -> MetricDef:
    """Create a sample metric definition for synonym testing."""
    metric_def = MetricDef(
        id=uuid.uuid4(),
        code=f"synonym_test_metric_{uuid.uuid4().hex[:8]}",
        name="Synonym Test Metric",
        name_ru="Тестовая метрика для синонимов",
        description="Test metric for synonym tests",
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
async def another_metric_def(db_session: AsyncSession) -> MetricDef:
    """Create another metric definition for testing cross-metric uniqueness."""
    metric_def = MetricDef(
        id=uuid.uuid4(),
        code=f"another_metric_{uuid.uuid4().hex[:8]}",
        name="Another Test Metric",
        name_ru="Другая тестовая метрика",
        description="Another test metric for synonym tests",
        unit="points",
        min_value=Decimal("1.0"),
        max_value=Decimal("10.0"),
        active=True,
    )
    db_session.add(metric_def)
    await db_session.commit()
    await db_session.refresh(metric_def)
    return metric_def


class TestMetricSynonymCRUD:
    """Tests CRUD operations for metric synonyms."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_create_synonym_success(
        self, client: AsyncClient, admin_user: User, test_metric_def: MetricDef
    ):
        """Successful synonym creation."""
        headers = get_auth_header(admin_user)

        response = await client.post(
            f"/api/metric-defs/{test_metric_def.id}/synonyms",
            json={"synonym": "Test Synonym"},
            headers=headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["synonym"] == "Test Synonym"
        assert data["metric_def_id"] == str(test_metric_def.id)
        assert "id" in data
        assert "created_at" in data

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_create_synonym_duplicate_error(
        self, client: AsyncClient, admin_user: User, test_metric_def: MetricDef
    ):
        """Error when creating duplicate synonym."""
        headers = get_auth_header(admin_user)

        # Create first synonym
        response1 = await client.post(
            f"/api/metric-defs/{test_metric_def.id}/synonyms",
            json={"synonym": "Duplicate"},
            headers=headers,
        )
        assert response1.status_code == 201

        # Try to create duplicate
        response2 = await client.post(
            f"/api/metric-defs/{test_metric_def.id}/synonyms",
            json={"synonym": "Duplicate"},
            headers=headers,
        )

        assert response2.status_code == 409
        detail = response2.json()["detail"]
        # detail can be dict {"message": "...", "existing_metric": {...}} or string
        detail_msg = detail["message"] if isinstance(detail, dict) else detail
        assert "already exists" in detail_msg.lower()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_create_synonym_duplicate_case_insensitive(
        self, client: AsyncClient, admin_user: User, test_metric_def: MetricDef
    ):
        """Error when creating duplicate synonym with different case."""
        headers = get_auth_header(admin_user)

        # Create first synonym
        response1 = await client.post(
            f"/api/metric-defs/{test_metric_def.id}/synonyms",
            json={"synonym": "CaseSensitive"},
            headers=headers,
        )
        assert response1.status_code == 201

        # Try to create same synonym with different case
        response2 = await client.post(
            f"/api/metric-defs/{test_metric_def.id}/synonyms",
            json={"synonym": "casesensitive"},
            headers=headers,
        )

        assert response2.status_code == 409

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_create_synonym_duplicate_across_metrics(
        self,
        client: AsyncClient,
        admin_user: User,
        test_metric_def: MetricDef,
        another_metric_def: MetricDef,
    ):
        """Error when creating synonym that exists for another metric (global uniqueness)."""
        headers = get_auth_header(admin_user)

        # Create synonym for first metric
        response1 = await client.post(
            f"/api/metric-defs/{test_metric_def.id}/synonyms",
            json={"synonym": "GlobalUnique"},
            headers=headers,
        )
        assert response1.status_code == 201

        # Try to create same synonym for another metric
        response2 = await client.post(
            f"/api/metric-defs/{another_metric_def.id}/synonyms",
            json={"synonym": "GlobalUnique"},
            headers=headers,
        )

        assert response2.status_code == 409
        detail = response2.json()["detail"]
        # detail can be dict {"message": "...", "existing_metric": {...}} or string
        detail_msg = detail["message"] if isinstance(detail, dict) else detail
        assert "already exists" in detail_msg.lower()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_create_synonym_empty_error(
        self, client: AsyncClient, admin_user: User, test_metric_def: MetricDef
    ):
        """Error when creating empty synonym."""
        headers = get_auth_header(admin_user)

        response = await client.post(
            f"/api/metric-defs/{test_metric_def.id}/synonyms",
            json={"synonym": ""},
            headers=headers,
        )

        assert response.status_code == 422

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_create_synonym_whitespace_only_error(
        self, client: AsyncClient, admin_user: User, test_metric_def: MetricDef
    ):
        """Error when creating whitespace-only synonym (after normalization)."""
        headers = get_auth_header(admin_user)

        response = await client.post(
            f"/api/metric-defs/{test_metric_def.id}/synonyms",
            json={"synonym": "   "},
            headers=headers,
        )

        # After strip(), "   " becomes "", which fails min_length=1
        assert response.status_code == 422

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_create_synonym_normalizes_whitespace(
        self, client: AsyncClient, admin_user: User, test_metric_def: MetricDef
    ):
        """Whitespace is trimmed from synonym during creation."""
        headers = get_auth_header(admin_user)

        response = await client.post(
            f"/api/metric-defs/{test_metric_def.id}/synonyms",
            json={"synonym": "  Trimmed Value  "},
            headers=headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["synonym"] == "Trimmed Value"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_synonyms_for_metric(
        self, client: AsyncClient, admin_user: User, test_metric_def: MetricDef
    ):
        """Get list of synonyms for a metric."""
        headers = get_auth_header(admin_user)

        # Create several synonyms
        await client.post(
            f"/api/metric-defs/{test_metric_def.id}/synonyms",
            json={"synonym": "Syn1"},
            headers=headers,
        )
        await client.post(
            f"/api/metric-defs/{test_metric_def.id}/synonyms",
            json={"synonym": "Syn2"},
            headers=headers,
        )

        response = await client.get(
            f"/api/metric-defs/{test_metric_def.id}/synonyms",
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 2
        synonyms = [item["synonym"] for item in data["items"]]
        assert "Syn1" in synonyms
        assert "Syn2" in synonyms

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_synonyms_empty_list(
        self, client: AsyncClient, admin_user: User, test_metric_def: MetricDef
    ):
        """Get empty list when metric has no synonyms."""
        headers = get_auth_header(admin_user)

        response = await client.get(
            f"/api/metric-defs/{test_metric_def.id}/synonyms",
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_update_synonym_success(
        self, client: AsyncClient, admin_user: User, test_metric_def: MetricDef
    ):
        """Successful synonym update."""
        headers = get_auth_header(admin_user)

        # Create synonym
        create_resp = await client.post(
            f"/api/metric-defs/{test_metric_def.id}/synonyms",
            json={"synonym": "Original"},
            headers=headers,
        )
        assert create_resp.status_code == 201
        synonym_id = create_resp.json()["id"]

        # Update synonym
        response = await client.put(
            f"/api/metric-synonyms/{synonym_id}",
            json={"synonym": "Updated"},
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["synonym"] == "Updated"
        assert data["id"] == synonym_id

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_update_synonym_duplicate_error(
        self, client: AsyncClient, admin_user: User, test_metric_def: MetricDef
    ):
        """Error when updating synonym to existing value."""
        headers = get_auth_header(admin_user)

        # Create two synonyms
        resp1 = await client.post(
            f"/api/metric-defs/{test_metric_def.id}/synonyms",
            json={"synonym": "First"},
            headers=headers,
        )
        resp2 = await client.post(
            f"/api/metric-defs/{test_metric_def.id}/synonyms",
            json={"synonym": "Second"},
            headers=headers,
        )
        synonym_id = resp2.json()["id"]

        # Try to update second to same as first
        response = await client.put(
            f"/api/metric-synonyms/{synonym_id}",
            json={"synonym": "First"},
            headers=headers,
        )

        assert response.status_code == 409
        detail = response.json()["detail"]
        # detail can be dict {"message": "...", "existing_metric": {...}} or string
        detail_msg = detail["message"] if isinstance(detail, dict) else detail
        assert "already exists" in detail_msg.lower()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_update_synonym_not_found(
        self, client: AsyncClient, admin_user: User
    ):
        """404 when updating non-existent synonym."""
        headers = get_auth_header(admin_user)
        fake_id = 999999

        response = await client.put(
            f"/api/metric-synonyms/{fake_id}",
            json={"synonym": "Updated"},
            headers=headers,
        )

        assert response.status_code == 404

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_delete_synonym_success(
        self, client: AsyncClient, admin_user: User, test_metric_def: MetricDef
    ):
        """Successful synonym deletion."""
        headers = get_auth_header(admin_user)

        # Create synonym
        create_resp = await client.post(
            f"/api/metric-defs/{test_metric_def.id}/synonyms",
            json={"synonym": "ToDelete"},
            headers=headers,
        )
        synonym_id = create_resp.json()["id"]

        # Delete synonym
        response = await client.delete(
            f"/api/metric-synonyms/{synonym_id}",
            headers=headers,
        )

        assert response.status_code == 204

        # Verify deletion by listing
        list_resp = await client.get(
            f"/api/metric-defs/{test_metric_def.id}/synonyms",
            headers=headers,
        )
        synonyms = [item["synonym"] for item in list_resp.json()["items"]]
        assert "ToDelete" not in synonyms

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_delete_synonym_not_found(
        self, client: AsyncClient, admin_user: User
    ):
        """404 when deleting non-existent synonym."""
        headers = get_auth_header(admin_user)
        fake_id = 999999

        response = await client.delete(
            f"/api/metric-synonyms/{fake_id}",
            headers=headers,
        )

        assert response.status_code == 404

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_metric_def_not_found(self, client: AsyncClient, admin_user: User):
        """404 when creating synonym for non-existent metric."""
        headers = get_auth_header(admin_user)
        fake_id = str(uuid.uuid4())

        response = await client.post(
            f"/api/metric-defs/{fake_id}/synonyms",
            json={"synonym": "Test"},
            headers=headers,
        )

        assert response.status_code == 404

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_synonyms_metric_def_not_found(
        self, client: AsyncClient, admin_user: User
    ):
        """404 when getting synonyms for non-existent metric."""
        headers = get_auth_header(admin_user)
        fake_id = str(uuid.uuid4())

        response = await client.get(
            f"/api/metric-defs/{fake_id}/synonyms",
            headers=headers,
        )

        assert response.status_code == 404


class TestMetricSynonymAccessControl:
    """Tests for access control on synonym endpoints."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_create_synonym_requires_admin(
        self, client: AsyncClient, active_user: User, test_metric_def: MetricDef
    ):
        """Regular user cannot create synonyms (ADMIN required)."""
        headers = get_auth_header(active_user)

        response = await client.post(
            f"/api/metric-defs/{test_metric_def.id}/synonyms",
            json={"synonym": "Test"},
            headers=headers,
        )

        assert response.status_code == 403

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_synonyms_requires_admin(
        self, client: AsyncClient, active_user: User, test_metric_def: MetricDef
    ):
        """Regular user cannot list synonyms (ADMIN required)."""
        headers = get_auth_header(active_user)

        response = await client.get(
            f"/api/metric-defs/{test_metric_def.id}/synonyms",
            headers=headers,
        )

        assert response.status_code == 403

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_update_synonym_requires_admin(
        self,
        client: AsyncClient,
        admin_user: User,
        active_user: User,
        test_metric_def: MetricDef,
    ):
        """Regular user cannot update synonyms (ADMIN required)."""
        admin_headers = get_auth_header(admin_user)
        user_headers = get_auth_header(active_user)

        # Create synonym as admin
        create_resp = await client.post(
            f"/api/metric-defs/{test_metric_def.id}/synonyms",
            json={"synonym": "AdminCreated"},
            headers=admin_headers,
        )
        synonym_id = create_resp.json()["id"]

        # Try to update as regular user
        response = await client.put(
            f"/api/metric-synonyms/{synonym_id}",
            json={"synonym": "UserUpdated"},
            headers=user_headers,
        )

        assert response.status_code == 403

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_delete_synonym_requires_admin(
        self,
        client: AsyncClient,
        admin_user: User,
        active_user: User,
        test_metric_def: MetricDef,
    ):
        """Regular user cannot delete synonyms (ADMIN required)."""
        admin_headers = get_auth_header(admin_user)
        user_headers = get_auth_header(active_user)

        # Create synonym as admin
        create_resp = await client.post(
            f"/api/metric-defs/{test_metric_def.id}/synonyms",
            json={"synonym": "AdminCreated2"},
            headers=admin_headers,
        )
        synonym_id = create_resp.json()["id"]

        # Try to delete as regular user
        response = await client.delete(
            f"/api/metric-synonyms/{synonym_id}",
            headers=user_headers,
        )

        assert response.status_code == 403

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_synonym_endpoints_require_auth(
        self, client: AsyncClient, test_metric_def: MetricDef
    ):
        """All synonym endpoints require authentication."""
        # Test create
        response = await client.post(
            f"/api/metric-defs/{test_metric_def.id}/synonyms",
            json={"synonym": "Test"},
        )
        assert response.status_code == 401

        # Test list
        response = await client.get(
            f"/api/metric-defs/{test_metric_def.id}/synonyms",
        )
        assert response.status_code == 401

        # Test update
        response = await client.put(
            "/api/metric-synonyms/1",
            json={"synonym": "Updated"},
        )
        assert response.status_code == 401

        # Test delete
        response = await client.delete("/api/metric-synonyms/1")
        assert response.status_code == 401


class TestMetricSynonymCascadeDelete:
    """Tests for cascade delete behavior."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires metric_embedding table (pgvector extension) which may not exist in test DB")
    async def test_cascade_delete_with_metric_def(
        self,
        client: AsyncClient,
        admin_user: User,
        db_session: AsyncSession,
    ):
        """Synonyms are deleted when parent metric_def is deleted.

        Note: Skipped because MetricDef delete triggers cascade to
        metric_embedding table which requires pgvector extension.
        """
        headers = get_auth_header(admin_user)

        # Create a metric def specifically for this test
        metric_def = MetricDef(
            id=uuid.uuid4(),
            code=f"cascade_test_{uuid.uuid4().hex[:8]}",
            name="Cascade Test Metric",
            active=True,
        )
        db_session.add(metric_def)
        await db_session.commit()
        await db_session.refresh(metric_def)

        # Create synonyms for it
        await client.post(
            f"/api/metric-defs/{metric_def.id}/synonyms",
            json={"synonym": "CascadeSyn1"},
            headers=headers,
        )
        await client.post(
            f"/api/metric-defs/{metric_def.id}/synonyms",
            json={"synonym": "CascadeSyn2"},
            headers=headers,
        )

        # Verify synonyms exist
        list_resp = await client.get(
            f"/api/metric-defs/{metric_def.id}/synonyms",
            headers=headers,
        )
        assert list_resp.json()["total"] == 2

        # Delete the metric_def
        delete_resp = await client.delete(
            f"/api/metric-defs/{metric_def.id}",
            headers=headers,
        )
        assert delete_resp.status_code == 200

        # Verify metric_def no longer exists
        get_resp = await client.get(
            f"/api/metric-defs/{metric_def.id}",
            headers=headers,
        )
        assert get_resp.status_code == 404

        # The synonyms should also be deleted (cascade)
        # We cannot query them directly as the metric_def is gone
        # but we can verify the synonym values are now available for reuse
        new_metric_def = MetricDef(
            id=uuid.uuid4(),
            code=f"cascade_test_new_{uuid.uuid4().hex[:8]}",
            name="New Cascade Test Metric",
            active=True,
        )
        db_session.add(new_metric_def)
        await db_session.commit()
        await db_session.refresh(new_metric_def)

        # Should be able to create the same synonym again
        reuse_resp = await client.post(
            f"/api/metric-defs/{new_metric_def.id}/synonyms",
            json={"synonym": "CascadeSyn1"},
            headers=headers,
        )
        assert reuse_resp.status_code == 201


class TestMetricSynonymConflicts:
    """Tests for synonym conflicts with metric names."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_synonym_conflicts_with_metric_name(
        self,
        client: AsyncClient,
        admin_user: User,
        test_metric_def: MetricDef,
        another_metric_def: MetricDef,
    ):
        """Cannot create synonym that matches existing metric name."""
        headers = get_auth_header(admin_user)

        # Try to create synonym matching another metric's name
        response = await client.post(
            f"/api/metric-defs/{test_metric_def.id}/synonyms",
            json={"synonym": another_metric_def.name},
            headers=headers,
        )

        # Should be rejected as it conflicts with metric name
        assert response.status_code == 409
        detail = response.json()["detail"]
        # detail can be dict or string
        detail_msg = detail["message"] if isinstance(detail, dict) else detail
        assert "conflicts" in detail_msg.lower()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_synonym_conflicts_with_metric_name_ru(
        self,
        client: AsyncClient,
        admin_user: User,
        test_metric_def: MetricDef,
        another_metric_def: MetricDef,
    ):
        """Cannot create synonym that matches existing metric name_ru."""
        headers = get_auth_header(admin_user)

        # Try to create synonym matching another metric's name_ru
        response = await client.post(
            f"/api/metric-defs/{test_metric_def.id}/synonyms",
            json={"synonym": another_metric_def.name_ru},
            headers=headers,
        )

        # Should be rejected as it conflicts with metric name_ru
        assert response.status_code == 409
        detail = response.json()["detail"]
        # detail can be dict or string
        detail_msg = detail["message"] if isinstance(detail, dict) else detail
        assert "conflicts" in detail_msg.lower()
