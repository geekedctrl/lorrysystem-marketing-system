from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.candidate import (
    CandidateAccept,
    CandidateAcceptResult,
    CandidateCreate,
    CandidateCreateResult,
    CandidateDetail,
    CandidateRead,
    CandidateReject,
    CandidateSourceCreate,
    CandidateSourceRead,
    CandidateStatus,
    CandidateUpdate,
)
from app.services.candidate_service import (
    CandidateContactConflictError,
    CandidateNotFoundError,
    CandidateSourceDuplicateError,
    CandidateStateError,
    ExistingActiveLeadError,
    ICPProfileNotFoundError,
    accept_candidate,
    add_candidate_source,
    create_candidate,
    get_candidate,
    list_candidates,
    reject_candidate,
    update_candidate,
)


router = APIRouter(
    prefix="/api/candidates",
    tags=["Lead Candidates"],
)


@router.post(
    "",
    response_model=CandidateCreateResult,
)
def create_candidate_endpoint(
    data: CandidateCreate,
    response: Response,
    db: Session = Depends(get_db),
):
    try:
        result = create_candidate(
            db,
            data,
        )

        if result["outcome"] in {
            "NEW_CANDIDATE",
            "EXISTING_COMPANY",
        }:
            response.status_code = status.HTTP_201_CREATED
        else:
            response.status_code = status.HTTP_200_OK

        return result

    except ICPProfileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "",
    response_model=list[CandidateRead],
)
def list_candidates_endpoint(
    status_filter: CandidateStatus | None = Query(
        default=None,
        alias="status",
    ),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return list_candidates(
        db,
        status=status_filter,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{candidate_id}",
    response_model=CandidateDetail,
)
def get_candidate_endpoint(
    candidate_id: UUID,
    db: Session = Depends(get_db),
):
    candidate = get_candidate(
        db,
        candidate_id,
    )

    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found.",
        )

    return candidate


@router.patch(
    "/{candidate_id}",
    response_model=CandidateRead,
)
def update_candidate_endpoint(
    candidate_id: UUID,
    data: CandidateUpdate,
    db: Session = Depends(get_db),
):
    try:
        return update_candidate(
            db,
            candidate_id=candidate_id,
            data=data,
        )

    except CandidateNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except ICPProfileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except ExistingActiveLeadError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(exc),
                "existing_lead_id": str(
                    exc.lead.id
                ),
                "existing_status": (
                    exc.lead.status
                ),
            },
        ) from exc

    except CandidateStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/{candidate_id}/sources",
    response_model=CandidateSourceRead,
    status_code=status.HTTP_201_CREATED,
)
def add_candidate_source_endpoint(
    candidate_id: UUID,
    data: CandidateSourceCreate,
    db: Session = Depends(get_db),
):
    try:
        return add_candidate_source(
            db,
            candidate_id=candidate_id,
            data=data,
        )

    except CandidateNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except CandidateSourceDuplicateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/{candidate_id}/accept",
    response_model=CandidateAcceptResult,
)
def accept_candidate_endpoint(
    candidate_id: UUID,
    data: CandidateAccept,
    db: Session = Depends(get_db),
):
    try:
        return accept_candidate(
            db,
            candidate_id=candidate_id,
            data=data,
        )

    except CandidateNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except ICPProfileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except CandidateStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except CandidateContactConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/{candidate_id}/reject",
    response_model=CandidateRead,
)
def reject_candidate_endpoint(
    candidate_id: UUID,
    data: CandidateReject,
    db: Session = Depends(get_db),
):
    try:
        return reject_candidate(
            db,
            candidate_id=candidate_id,
            data=data,
        )

    except CandidateNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except CandidateStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
