"""
Service layer for professional activities.

Provides list endpoint orchestration and seed helpers.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.prof_activity import ProfActivityRepository
from app.schemas.prof_activity import (
    ProfActivityCreateRequest,
    ProfActivityResponse,
    ProfActivityUpdateRequest,
)


class ProfActivityService:
    """Business logic for professional activity operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ProfActivityRepository(db)

    async def list_prof_activities(self) -> list[ProfActivityResponse]:
        """
        List all professional activities.

        Returns:
            List of serialized professional activities.
        """
        activities = await self.repo.list_all()
        return [ProfActivityResponse.model_validate(activity) for activity in activities]

    async def create_prof_activity(
        self, request: ProfActivityCreateRequest
    ) -> ProfActivityResponse:
        """
        Create a new professional activity.

        Args:
            request: Creation request with code, name, description

        Returns:
            Created professional activity

        Raises:
            ValueError: If code already exists
        """
        existing = await self.repo.get_by_code(request.code)
        if existing:
            raise ValueError(f"Professional activity with code '{request.code}' already exists")

        prof_activity = await self.repo.create(
            code=request.code, name=request.name, description=request.description
        )
        return ProfActivityResponse.model_validate(prof_activity)

    async def update_prof_activity(
        self, prof_activity_id: UUID, request: ProfActivityUpdateRequest
    ) -> ProfActivityResponse:
        """
        Update a professional activity.

        Args:
            prof_activity_id: UUID of the activity to update
            request: Update request with optional name and description

        Returns:
            Updated professional activity

        Raises:
            ValueError: If activity not found
        """
        prof_activity = await self.repo.update(
            prof_activity_id=prof_activity_id, name=request.name, description=request.description
        )
        if not prof_activity:
            raise ValueError("Professional activity not found")

        return ProfActivityResponse.model_validate(prof_activity)

    async def delete_prof_activity(self, prof_activity_id: UUID) -> None:
        """
        Delete a professional activity.

        Args:
            prof_activity_id: UUID of the activity to delete

        Raises:
            ValueError: If activity not found or has associated weight tables
        """
        success = await self.repo.delete(prof_activity_id)
        if not success:
            raise ValueError("Professional activity not found")

