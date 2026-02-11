"""
Repository layer for Organization and Department data access.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.db.models import Department, Organization, Participant, WeightTable, ProfActivity


class OrganizationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, name: str, description: str | None = None) -> Organization:
        org = Organization(name=name, description=description)
        self.db.add(org)
        await self.db.commit()
        await self.db.refresh(org)
        return org

    async def get_by_id(self, org_id: UUID) -> Organization | None:
        result = await self.db.execute(select(Organization).where(Organization.id == org_id))
        return result.scalar_one_or_none()

    async def get_by_id_with_departments(self, org_id: UUID) -> Organization | None:
        result = await self.db.execute(
            select(Organization)
            .options(
                selectinload(Organization.departments)
                .selectinload(Department.weight_table)
                .selectinload(WeightTable.prof_activity)
            )
            .where(Organization.id == org_id)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Organization | None:
        result = await self.db.execute(select(Organization).where(Organization.name == name))
        return result.scalar_one_or_none()

    async def search(
        self, query: str | None = None, page: int = 1, size: int = 20
    ) -> tuple[list[Organization], int]:
        stmt = select(Organization)
        if query:
            stmt = stmt.where(Organization.name.ilike(f"%{query}%"))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar_one()

        stmt = stmt.order_by(Organization.name, Organization.id)
        offset = (page - 1) * size
        stmt = stmt.offset(offset).limit(size)

        result = await self.db.execute(stmt)
        return list(result.scalars().all()), total

    async def update(self, org: Organization, name: str | None = None, description: str | None = None) -> Organization:
        if name is not None:
            org.name = name
        if description is not None:
            org.description = description
        await self.db.commit()
        await self.db.refresh(org)
        return org

    async def delete(self, org: Organization) -> None:
        await self.db.delete(org)
        await self.db.commit()

    async def get_departments_count(self, org_id: UUID) -> int:
        result = await self.db.execute(
            select(func.count()).where(Department.organization_id == org_id)
        )
        return result.scalar_one()

    async def get_participants_count(self, org_id: UUID) -> int:
        """Count all participants across all departments in an organization."""
        result = await self.db.execute(
            select(func.count())
            .select_from(Participant)
            .join(Department, Participant.department_id == Department.id)
            .where(Department.organization_id == org_id)
        )
        return result.scalar_one()


class DepartmentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, organization_id: UUID, name: str, description: str | None = None) -> Department:
        dept = Department(organization_id=organization_id, name=name, description=description)
        self.db.add(dept)
        await self.db.commit()
        await self.db.refresh(dept)
        return dept

    async def get_by_id(self, dept_id: UUID) -> Department | None:
        result = await self.db.execute(
            select(Department)
            .options(
                selectinload(Department.weight_table).selectinload(WeightTable.prof_activity)
            )
            .where(Department.id == dept_id)
        )
        return result.scalar_one_or_none()

    async def list_by_organization(self, org_id: UUID) -> list[Department]:
        result = await self.db.execute(
            select(Department)
            .options(
                selectinload(Department.weight_table).selectinload(WeightTable.prof_activity)
            )
            .where(Department.organization_id == org_id)
            .order_by(Department.name)
        )
        return list(result.scalars().all())

    async def get_by_org_and_name(self, org_id: UUID, name: str) -> Department | None:
        result = await self.db.execute(
            select(Department).where(
                Department.organization_id == org_id,
                Department.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def update(self, dept: Department, name: str | None = None, description: str | None = None) -> Department:
        if name is not None:
            dept.name = name
        if description is not None:
            dept.description = description
        await self.db.commit()
        await self.db.refresh(dept)
        return dept

    async def delete(self, dept: Department) -> None:
        await self.db.delete(dept)
        await self.db.commit()

    async def get_participants_count(self, dept_id: UUID) -> int:
        result = await self.db.execute(
            select(func.count()).where(Participant.department_id == dept_id)
        )
        return result.scalar_one()

    async def list_participants(self, dept_id: UUID) -> list[Participant]:
        result = await self.db.execute(
            select(Participant)
            .options(selectinload(Participant.department).selectinload(Department.organization))
            .where(Participant.department_id == dept_id)
            .order_by(Participant.full_name)
        )
        return list(result.scalars().all())

    async def attach_participants(self, dept_id: UUID, participant_ids: list[UUID]) -> int:
        """Attach participants to department. Returns count of updated rows."""
        count = 0
        for pid in participant_ids:
            result = await self.db.execute(
                select(Participant).where(Participant.id == pid)
            )
            participant = result.scalar_one_or_none()
            if participant:
                participant.department_id = dept_id
                count += 1
        await self.db.commit()
        return count

    async def set_weight_table(self, dept: Department, weight_table_id: UUID | None) -> Department:
        dept.weight_table_id = weight_table_id
        await self.db.commit()
        await self.db.refresh(dept, attribute_names=["weight_table"])
        return dept

    async def detach_participant(self, participant_id: UUID) -> bool:
        result = await self.db.execute(
            select(Participant).where(Participant.id == participant_id)
        )
        participant = result.scalar_one_or_none()
        if not participant or participant.department_id is None:
            return False
        participant.department_id = None
        await self.db.commit()
        return True
