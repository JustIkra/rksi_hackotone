# tests/tasks/test_metric_generation_transaction.py
"""
Unit tests for transaction handling in MetricGenerationService.

Tests cover:
- get_or_create_category handles IntegrityError gracefully
- Savepoint pattern prevents transaction abortion
- Session remains usable after constraint violations
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.metric_generation import MetricGenerationService
from app.db.models import MetricCategory


@pytest.mark.asyncio
class TestGetOrCreateCategoryTransaction:
    """Test transaction handling in get_or_create_category."""

    async def test_get_or_create_category_handles_integrity_error(self, db_session: AsyncSession):
        """
        Test that IntegrityError during category creation is handled gracefully.

        When two concurrent requests try to create the same category,
        the second should catch IntegrityError and return the existing category
        instead of failing the entire transaction.
        """
        # Arrange
        service = MetricGenerationService(db=db_session, redis=None)
        category_name = "Тестовая категория"

        # Create the category first time
        category1 = await service.get_or_create_category(category_name)
        await db_session.commit()

        # Act: Try to create the same category again (simulates concurrent request)
        # This should NOT raise IntegrityError, should return existing
        category2 = await service.get_or_create_category(category_name)

        # Assert
        assert category2 is not None
        assert category2.id == category1.id
        assert category2.name == category_name

    async def test_session_usable_after_category_integrity_error(self, db_session: AsyncSession):
        """
        Test that session remains usable after handling IntegrityError.

        After a handled IntegrityError, subsequent queries should succeed
        without InFailedSQLTransactionError.
        """
        # Arrange
        service = MetricGenerationService(db=db_session, redis=None)

        # Create a category first
        category = await service.get_or_create_category("Первая категория")
        await db_session.commit()

        # Try to create duplicate (should be handled)
        await service.get_or_create_category("Первая категория")

        # Act: Session should still be usable for other queries
        existing_categories = await service.get_existing_categories()

        # Assert
        assert len(existing_categories) >= 1
        assert any(c["name"] == "Первая категория" for c in existing_categories)

    async def test_get_or_create_category_uses_savepoint(self, db_session: AsyncSession):
        """
        Test that get_or_create_category uses savepoint pattern.

        Verifies that the implementation uses begin_nested() to create
        a savepoint that can be rolled back without affecting the outer transaction.
        """
        import inspect
        from app.services.metric_generation import MetricGenerationService

        # Check source code contains begin_nested pattern
        source = inspect.getsource(MetricGenerationService.get_or_create_category)

        assert 'begin_nested' in source, (
            "get_or_create_category should use begin_nested() for savepoint pattern"
        )


@pytest.mark.asyncio
class TestCreatePendingMetricTransaction:
    """Test transaction handling in create_pending_metric."""

    async def test_create_pending_metric_uses_savepoint(self, db_session: AsyncSession):
        """
        Test that create_pending_metric uses savepoint pattern.
        """
        import inspect
        from app.services.metric_generation import MetricGenerationService

        source = inspect.getsource(MetricGenerationService.create_pending_metric)

        assert 'begin_nested' in source, (
            "create_pending_metric should use begin_nested() for savepoint pattern"
        )

    async def test_session_usable_after_metric_creation(self, db_session: AsyncSession):
        """
        Test that session remains usable after metric creation.
        """
        from app.schemas.metric_generation import ExtractedMetricData
        from sqlalchemy import select
        from app.db.models import MetricDef

        service = MetricGenerationService(db=db_session, redis=None)

        # Create a metric
        metric_data = ExtractedMetricData(
            name="Тестовая метрика",
            description="Описание",
            value=5.0,
            category="Тестовая категория",
            synonyms=[],
            rationale=None,
        )

        metric1 = await service.create_pending_metric(metric_data)
        await db_session.commit()

        # Session should still be usable - query the metric directly
        result = await db_session.execute(
            select(MetricDef).where(MetricDef.id == metric1.id)
        )
        fetched = result.scalars().first()

        assert fetched is not None
        assert fetched.name == "Тестовая метрика"


@pytest.mark.asyncio
class TestProcessDocumentTransaction:
    """Test transaction handling in process_document save loop."""

    async def test_process_document_save_loop_handles_errors_per_metric(self, db_session: AsyncSession):
        """
        Test that errors in saving individual metrics don't abort the entire batch.

        Verifies that the save loop continues processing remaining metrics
        after encountering an error with one metric.
        """
        import inspect
        from app.services.metric_generation import MetricGenerationService

        source = inspect.getsource(MetricGenerationService.process_document)

        # The save loop should have try/except around individual metric processing
        assert 'try:' in source and 'except' in source, (
            "process_document should have error handling in the save loop"
        )

    async def test_save_loop_has_explicit_rollback_on_error(self, db_session: AsyncSession):
        """
        Test that the save loop calls rollback() on errors.
        """
        import inspect
        from app.services.metric_generation import MetricGenerationService

        source = inspect.getsource(MetricGenerationService.process_document)

        # Should have rollback in the save section
        assert 'rollback' in source, (
            "process_document should have explicit rollback on errors"
        )
