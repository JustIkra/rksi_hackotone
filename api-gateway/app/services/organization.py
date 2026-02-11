"""
Service layer for Organization and Department business logic.
"""

import logging
from math import ceil
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Department
from app.repositories.organization import DepartmentRepository, OrganizationRepository
from app.repositories.scoring_result import ScoringResultRepository
from app.repositories.weight_table import WeightTableRepository
from app.schemas.organization import (
    AttachParticipantsRequest,
    AttachWeightTableRequest,
    DepartmentCreateRequest,
    DepartmentListResponse,
    DepartmentResponse,
    DepartmentUpdateRequest,
    OrganizationCreateRequest,
    OrganizationDetailResponse,
    OrganizationListResponse,
    OrganizationResponse,
    OrganizationUpdateRequest,
    ParticipantWithSuitabilityResponse,
)

logger = logging.getLogger(__name__)


class OrganizationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.org_repo = OrganizationRepository(db)
        self.dept_repo = DepartmentRepository(db)

    # --- Organization CRUD ---

    async def create_organization(self, request: OrganizationCreateRequest) -> OrganizationResponse:
        existing = await self.org_repo.get_by_name(request.name)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Организация с именем '{request.name}' уже существует",
            )
        org = await self.org_repo.create(name=request.name, description=request.description)
        return OrganizationResponse(
            id=org.id,
            name=org.name,
            description=org.description,
            created_at=org.created_at,
            departments_count=0,
            participants_count=0,
        )

    async def get_organization(self, org_id: UUID) -> OrganizationDetailResponse:
        org = await self.org_repo.get_by_id_with_departments(org_id)
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Организация не найдена")

        dept_responses = []
        for dept in org.departments:
            count = await self.dept_repo.get_participants_count(dept.id)
            dept_responses.append(self._build_dept_response(dept, count))
        dept_responses.sort(key=lambda d: d.name)

        return OrganizationDetailResponse(
            id=org.id,
            name=org.name,
            description=org.description,
            created_at=org.created_at,
            departments=dept_responses,
        )

    async def search_organizations(
        self, query: str | None = None, page: int = 1, size: int = 20
    ) -> OrganizationListResponse:
        orgs, total = await self.org_repo.search(query=query, page=page, size=size)
        items = []
        for org in orgs:
            dept_count = await self.org_repo.get_departments_count(org.id)
            part_count = await self.org_repo.get_participants_count(org.id)
            items.append(
                OrganizationResponse(
                    id=org.id,
                    name=org.name,
                    description=org.description,
                    created_at=org.created_at,
                    departments_count=dept_count,
                    participants_count=part_count,
                )
            )
        pages = ceil(total / size) if total > 0 else 0
        return OrganizationListResponse(items=items, total=total, page=page, size=size, pages=pages)

    async def update_organization(self, org_id: UUID, request: OrganizationUpdateRequest) -> OrganizationResponse:
        org = await self.org_repo.get_by_id(org_id)
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Организация не найдена")

        if request.name is not None and request.name != org.name:
            existing = await self.org_repo.get_by_name(request.name)
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Организация с именем '{request.name}' уже существует",
                )

        org = await self.org_repo.update(org, name=request.name, description=request.description)
        dept_count = await self.org_repo.get_departments_count(org.id)
        part_count = await self.org_repo.get_participants_count(org.id)
        return OrganizationResponse(
            id=org.id,
            name=org.name,
            description=org.description,
            created_at=org.created_at,
            departments_count=dept_count,
            participants_count=part_count,
        )

    async def delete_organization(self, org_id: UUID) -> None:
        org = await self.org_repo.get_by_id(org_id)
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Организация не найдена")
        await self.org_repo.delete(org)

    # --- Department CRUD ---

    async def create_department(self, org_id: UUID, request: DepartmentCreateRequest) -> DepartmentResponse:
        org = await self.org_repo.get_by_id(org_id)
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Организация не найдена")

        existing = await self.dept_repo.get_by_org_and_name(org_id, request.name)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Отдел '{request.name}' уже существует в этой организации",
            )

        dept = await self.dept_repo.create(
            organization_id=org_id, name=request.name, description=request.description
        )
        return self._build_dept_response(dept, 0)

    async def list_departments(self, org_id: UUID) -> DepartmentListResponse:
        org = await self.org_repo.get_by_id(org_id)
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Организация не найдена")

        depts = await self.dept_repo.list_by_organization(org_id)
        items = []
        for dept in depts:
            count = await self.dept_repo.get_participants_count(dept.id)
            items.append(self._build_dept_response(dept, count))
        return DepartmentListResponse(items=items, total=len(items))

    async def update_department(
        self, org_id: UUID, dept_id: UUID, request: DepartmentUpdateRequest
    ) -> DepartmentResponse:
        dept = await self._get_department_in_org(org_id, dept_id)

        if request.name is not None and request.name != dept.name:
            existing = await self.dept_repo.get_by_org_and_name(org_id, request.name)
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Отдел '{request.name}' уже существует в этой организации",
                )

        dept = await self.dept_repo.update(dept, name=request.name, description=request.description)
        count = await self.dept_repo.get_participants_count(dept.id)
        return self._build_dept_response(dept, count)

    async def delete_department(self, org_id: UUID, dept_id: UUID) -> None:
        dept = await self._get_department_in_org(org_id, dept_id)
        await self.dept_repo.delete(dept)

    # --- Participants in department ---

    async def list_department_participants(self, org_id: UUID, dept_id: UUID):
        await self._get_department_in_org(org_id, dept_id)
        return await self.dept_repo.list_participants(dept_id)

    async def attach_participants(
        self, org_id: UUID, dept_id: UUID, request: AttachParticipantsRequest
    ) -> int:
        await self._get_department_in_org(org_id, dept_id)
        return await self.dept_repo.attach_participants(dept_id, request.participant_ids)

    async def detach_participant(self, org_id: UUID, dept_id: UUID, participant_id: UUID) -> None:
        await self._get_department_in_org(org_id, dept_id)
        detached = await self.dept_repo.detach_participant(participant_id)
        if not detached:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Участник не найден или не привязан к этому отделу",
            )

    # --- Weight table ---

    async def attach_weight_table(
        self, org_id: UUID, dept_id: UUID, request: AttachWeightTableRequest
    ) -> DepartmentResponse:
        dept = await self._get_department_in_org(org_id, dept_id)

        if request.weight_table_id is not None:
            wt_repo = WeightTableRepository(self.db)
            wt = await wt_repo.get_by_id(request.weight_table_id)
            if not wt:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Весовая таблица не найдена",
                )

        dept = await self.dept_repo.set_weight_table(dept, request.weight_table_id)
        count = await self.dept_repo.get_participants_count(dept.id)
        return self._build_dept_response(dept, count)

    async def list_department_participants_with_scores(
        self, org_id: UUID, dept_id: UUID
    ) -> list[ParticipantWithSuitabilityResponse]:
        dept = await self._get_department_in_org(org_id, dept_id)
        participants = await self.dept_repo.list_participants(dept_id)

        if not dept.weight_table_id or not participants:
            return [
                ParticipantWithSuitabilityResponse(
                    id=p.id,
                    full_name=p.full_name,
                    birth_date=p.birth_date,
                    external_id=p.external_id,
                    department_id=p.department_id,
                    created_at=p.created_at,
                )
                for p in participants
            ]

        # Batch fetch scoring results
        sr_repo = ScoringResultRepository(self.db)
        pids = [p.id for p in participants]
        scores_map = await sr_repo.list_by_participants_and_weight_table(pids, dept.weight_table_id)

        # Get weight table to compute coverage
        wt_repo = WeightTableRepository(self.db)
        wt = await wt_repo.get_by_id(dept.weight_table_id)
        wt_metric_codes = {w["metric_code"] for w in wt.weights} if wt else set()
        total_wt_metrics = len(wt_metric_codes)

        # Batch fetch participant metrics for coverage
        from app.repositories.participant_metric import ParticipantMetricRepository
        pm_repo = ParticipantMetricRepository(self.db)

        results = []
        for p in participants:
            sr = scores_map.get(p.id)
            p_metrics = await pm_repo.get_metrics_dict(p.id)
            has_metrics = len(p_metrics) > 0

            metrics_coverage = None
            if total_wt_metrics > 0 and has_metrics:
                covered = sum(1 for mc in wt_metric_codes if mc in p_metrics)
                metrics_coverage = round(covered / total_wt_metrics * 100, 1)

            suitability_pct = None
            final_score = None
            if sr:
                final_score = float(sr.final_score)
                suitability_pct = round(final_score / 10 * 100, 1)

            results.append(ParticipantWithSuitabilityResponse(
                id=p.id,
                full_name=p.full_name,
                birth_date=p.birth_date,
                external_id=p.external_id,
                department_id=p.department_id,
                created_at=p.created_at,
                suitability_pct=suitability_pct,
                final_score=final_score,
                has_metrics=has_metrics,
                metrics_coverage=metrics_coverage,
            ))
        return results

    async def calculate_department_scores(
        self, org_id: UUID, dept_id: UUID
    ) -> dict:
        dept = await self._get_department_in_org(org_id, dept_id)
        if not dept.weight_table_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="К отделу не привязана весовая таблица",
            )

        participants = await self.dept_repo.list_participants(dept_id)
        from app.services.scoring import ScoringService
        scoring_svc = ScoringService(self.db)

        calculated = 0
        errors = []
        for p in participants:
            try:
                await scoring_svc.calculate_score(p.id, dept.weight_table_id)
                calculated += 1
            except Exception as e:
                logger.error(f"Score calc error for participant {p.id}: {e}")
                errors.append({"participant_id": str(p.id), "error": str(e)})

        return {"calculated": calculated, "errors": errors}

    # --- helpers ---

    def _build_dept_response(self, dept: Department, participants_count: int) -> DepartmentResponse:
        wt_name = None
        if dept.weight_table_id:
            wt = getattr(dept, "weight_table", None)
            if wt and getattr(wt, "prof_activity", None):
                wt_name = wt.prof_activity.name
        return DepartmentResponse(
            id=dept.id,
            organization_id=dept.organization_id,
            name=dept.name,
            description=dept.description,
            created_at=dept.created_at,
            participants_count=participants_count,
            weight_table_id=dept.weight_table_id,
            weight_table_name=wt_name,
        )

    async def _get_department_in_org(self, org_id: UUID, dept_id: UUID):
        dept = await self.dept_repo.get_by_id(dept_id)
        if not dept or dept.organization_id != org_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Отдел не найден")
        return dept
