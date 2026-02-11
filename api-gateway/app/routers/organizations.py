"""
REST API endpoints for Organization and Department management.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.organization import (
    AttachParticipantsRequest,
    AttachWeightTableRequest,
    DepartmentCreateRequest,
    DepartmentListResponse,
    DepartmentResponse,
    DepartmentUpdateRequest,
    DetachParticipantRequest,
    OrganizationCreateRequest,
    OrganizationDetailResponse,
    OrganizationListResponse,
    OrganizationResponse,
    OrganizationUpdateRequest,
    ParticipantWithSuitabilityResponse,
)
from app.schemas.participant import MessageResponse, ParticipantResponse
from app.services.organization import OrganizationService

router = APIRouter(prefix="/organizations", tags=["organizations"])


# --- Organization CRUD ---

@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    request: OrganizationCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = OrganizationService(db)
    return await service.create_organization(request)


@router.get("", response_model=OrganizationListResponse)
async def search_organizations(
    query: str | None = Query(None, description="Search by name"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = OrganizationService(db)
    return await service.search_organizations(query=query, page=page, size=size)


@router.get("/{org_id}", response_model=OrganizationDetailResponse)
async def get_organization(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = OrganizationService(db)
    return await service.get_organization(org_id)


@router.put("/{org_id}", response_model=OrganizationResponse)
async def update_organization(
    org_id: UUID,
    request: OrganizationUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = OrganizationService(db)
    return await service.update_organization(org_id, request)


@router.delete("/{org_id}", response_model=MessageResponse)
async def delete_organization(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = OrganizationService(db)
    await service.delete_organization(org_id)
    return MessageResponse(message="Организация удалена")


# --- Department CRUD ---

@router.post("/{org_id}/departments", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
async def create_department(
    org_id: UUID,
    request: DepartmentCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = OrganizationService(db)
    return await service.create_department(org_id, request)


@router.get("/{org_id}/departments", response_model=DepartmentListResponse)
async def list_departments(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = OrganizationService(db)
    return await service.list_departments(org_id)


@router.put("/{org_id}/departments/{dept_id}", response_model=DepartmentResponse)
async def update_department(
    org_id: UUID,
    dept_id: UUID,
    request: DepartmentUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = OrganizationService(db)
    return await service.update_department(org_id, dept_id, request)


@router.delete("/{org_id}/departments/{dept_id}", response_model=MessageResponse)
async def delete_department(
    org_id: UUID,
    dept_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = OrganizationService(db)
    await service.delete_department(org_id, dept_id)
    return MessageResponse(message="Отдел удалён")


# --- Participants in department ---

@router.get("/{org_id}/departments/{dept_id}/participants", response_model=list[ParticipantResponse])
async def list_department_participants(
    org_id: UUID,
    dept_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    from app.services.participant import ParticipantService

    service = OrganizationService(db)
    participants = await service.list_department_participants(org_id, dept_id)
    return [ParticipantService._to_response(p) for p in participants]


@router.post("/{org_id}/departments/{dept_id}/participants", response_model=MessageResponse)
async def attach_participants(
    org_id: UUID,
    dept_id: UUID,
    request: AttachParticipantsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = OrganizationService(db)
    count = await service.attach_participants(org_id, dept_id, request)
    return MessageResponse(message=f"Привязано участников: {count}")


@router.delete("/{org_id}/departments/{dept_id}/participants", response_model=MessageResponse)
async def detach_participant(
    org_id: UUID,
    dept_id: UUID,
    request: DetachParticipantRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = OrganizationService(db)
    await service.detach_participant(org_id, dept_id, request.participant_id)
    return MessageResponse(message="Участник отвязан от отдела")


# --- Weight table attachment ---

@router.put("/{org_id}/departments/{dept_id}/weight-table", response_model=DepartmentResponse)
async def attach_weight_table(
    org_id: UUID,
    dept_id: UUID,
    request: AttachWeightTableRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = OrganizationService(db)
    return await service.attach_weight_table(org_id, dept_id, request)


@router.get(
    "/{org_id}/departments/{dept_id}/participants/scores",
    response_model=list[ParticipantWithSuitabilityResponse],
)
async def list_department_participants_with_scores(
    org_id: UUID,
    dept_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = OrganizationService(db)
    return await service.list_department_participants_with_scores(org_id, dept_id)


@router.post("/{org_id}/departments/{dept_id}/calculate-scores")
async def calculate_department_scores(
    org_id: UUID,
    dept_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = OrganizationService(db)
    return await service.calculate_department_scores(org_id, dept_id)
