"""
Scoring API router.

Provides endpoints for:
- Calculating professional fitness scores
- Generating strengths and development areas
- Fetching scoring history for participants
"""

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.models import User
from app.db.session import get_db
from app.repositories.participant import ParticipantRepository
from app.repositories.scoring_result import ScoringResultRepository
from app.services.scoring import ScoringService

router = APIRouter(prefix="/scoring", tags=["scoring"])


# Schemas

class MetricContribution(BaseModel):
    """Individual metric contribution to the score."""

    metric_code: str
    value: str  # Decimal as string
    weight: str  # Decimal as string
    contribution: str  # Decimal as string


class MetricItem(BaseModel):
    """Metric item for strengths/dev_areas."""

    metric_code: str
    metric_name: str
    value: str  # Decimal as string
    weight: str  # Decimal as string


class TopCompetencyItem(BaseModel):
    """Top competency item sorted by contribution (value × weight)."""

    metric_code: str
    metric_name: str
    metric_name_ru: str
    value: str  # Decimal as string
    weight: str  # Decimal as string
    contribution: str  # Decimal as string


class ScoringResponse(BaseModel):
    """Response schema for scoring calculation."""

    scoring_result_id: str
    participant_id: str
    prof_activity_id: str
    prof_activity_name: str
    prof_activity_code: str
    score_pct: Decimal = Field(..., description="Score as percentage (0-100), quantized to 0.01")
    weight_table_id: str = Field(..., description="ID of the weight table used for scoring")
    details: list[MetricContribution]
    missing_metrics: list[str] = Field(default_factory=list)
    strengths: list[MetricItem] = Field(
        default_factory=list, description="Top 5 high-value metrics"
    )
    dev_areas: list[MetricItem] = Field(
        default_factory=list, description="Top 5 low-value metrics"
    )
    top_competencies: list[TopCompetencyItem] = Field(
        default_factory=list, description="Top 5 competencies by contribution (value × weight)"
    )


class ScoringHistoryItem(BaseModel):
    """Single item in scoring history."""

    id: str
    participant_id: str
    prof_activity_code: str
    prof_activity_name: str
    score_pct: Decimal = Field(..., description="Score as percentage (0-100)")
    strengths: list[dict] = Field(default_factory=list)
    dev_areas: list[dict] = Field(default_factory=list)
    created_at: str  # ISO 8601 datetime string


class ScoringHistoryResponse(BaseModel):
    """Response schema for scoring history."""

    items: list[ScoringHistoryItem]


# Endpoints

@router.post("/participants/{participant_id}/calculate", response_model=ScoringResponse)
async def calculate_participant_score(
    participant_id: UUID,
    activity_code: str = Query(..., description="Professional activity code"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Calculate professional fitness score for a participant.

    Requires:
    - Active weight table for the specified professional activity
    - Extracted metrics for all required metrics in the weight table

    Returns:
    - Score as percentage (0-100)
    - Breakdown of metric contributions
    - Weight table version used
    - Strengths: Top 5 high-value metrics
    - Dev areas: Top 5 low-value metrics

    Raises:
    - 404: Participant or activity not found
    - 400: Missing metrics or invalid data
    """
    scoring_service = ScoringService(db)

    try:
        result = await scoring_service.calculate_score(
            participant_id=participant_id,
            prof_activity_code=activity_code,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return ScoringResponse(
        scoring_result_id=result["scoring_result_id"],
        participant_id=str(participant_id),
        prof_activity_id=result["prof_activity_id"],
        prof_activity_name=result["prof_activity_name"],
        prof_activity_code=activity_code,
        score_pct=result["score_pct"],
        weight_table_id=result["weight_table_id"],
        details=[MetricContribution(**d) for d in result["details"]],
        missing_metrics=result["missing_metrics"],
        strengths=[MetricItem(**item) for item in result.get("strengths", [])],
        dev_areas=[MetricItem(**item) for item in result.get("dev_areas", [])],
        top_competencies=[TopCompetencyItem(**item) for item in result.get("top_competencies", [])],
    )


@router.get("/participants/{participant_id}/scores", response_model=ScoringHistoryResponse)
async def get_participant_scoring_history(
    participant_id: UUID,
    limit: int = Query(10, ge=1, le=100, description="Maximum number of results to return"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get scoring history for a participant.

    Returns list of all scoring results ordered by computed_at DESC.

    Returns:
    - List of scoring results with:
        - id: Scoring result UUID
        - participant_id: Participant UUID
        - prof_activity_code: Professional activity code
        - prof_activity_name: Professional activity name
        - score_pct: Score as percentage (0-100)
        - strengths: JSONB array of strengths
        - dev_areas: JSONB array of development areas
        - created_at: Timestamp when score was computed

    Raises:
    - 404: Participant not found
    - 401: Unauthorized
    """
    participant_repo = ParticipantRepository(db)
    participant = await participant_repo.get_by_id(participant_id)
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")

    scoring_repo = ScoringResultRepository(db)
    results = await scoring_repo.list_by_participant(participant_id, limit=limit)

    items = []
    for result in results:
        items.append(
            ScoringHistoryItem(
                id=str(result.id),
                participant_id=str(result.participant_id),
                prof_activity_code=result.weight_table.prof_activity.code,
                prof_activity_name=result.weight_table.prof_activity.name,
                score_pct=result.score_pct,
                strengths=result.strengths or [],
                dev_areas=result.dev_areas or [],
                created_at=result.computed_at.isoformat(),
            )
        )

    return ScoringHistoryResponse(items=items)
