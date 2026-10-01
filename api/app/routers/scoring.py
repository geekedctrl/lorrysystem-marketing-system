from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.scoring import (
    ScoreCreate,
    ScoreRead,
)
from app.services.scoring_service import (
    CurrentScoreNotFoundError,
    ScoreNotFoundError,
    ScoringConflictError,
    ScoringLeadNotFoundError,
    ScoringNotAllowedError,
    create_score,
    get_current_score,
    get_score,
    list_scores_for_lead,
)


router = APIRouter(
    tags=["Scoring"],
)


@router.post(
    "/api/leads/{lead_id}/scores",
    response_model=ScoreRead,
    status_code=status.HTTP_201_CREATED,
)
def create_score_endpoint(
    lead_id: UUID,
    data: ScoreCreate,
    db: Session = Depends(get_db),
):
    try:
        return create_score(
            db,
            lead_id=lead_id,
            data=data,
        )

    except ScoringLeadNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except ScoringNotAllowedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except ScoringConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/api/leads/{lead_id}/scores",
    response_model=list[ScoreRead],
)
def list_scores_endpoint(
    lead_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        return list_scores_for_lead(
            db,
            lead_id=lead_id,
        )

    except ScoringLeadNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/api/leads/{lead_id}/scores/current",
    response_model=ScoreRead,
)
def get_current_score_endpoint(
    lead_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        return get_current_score(
            db,
            lead_id=lead_id,
        )

    except ScoringLeadNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except CurrentScoreNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/api/scoring/{score_id}",
    response_model=ScoreRead,
)
def get_score_endpoint(
    score_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        return get_score(
            db,
            score_id=score_id,
        )

    except ScoreNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
