from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.research import (
    ResearchComplete,
    ResearchContext,
    ResearchDetail,
    ResearchFail,
    ResearchPartial,
    ResearchRead,
    ResearchStatus,
    ResearchSourceCreate,
    ResearchSourceRead,
)
from app.services.lead_service import (
    LeadNotFoundError,
)
from app.services.research_service import (
    InvalidLeadResearchStateError,
    InvalidResearchTransitionError,
    ResearchContextIntegrityError,
    ResearchNotFoundError,
    add_research_source,
    claim_next_research,
    complete_research,
    create_research_run,
    fail_research,
    get_research_context,
    get_research_detail,
    list_research_for_lead,
    list_research_runs,
    mark_research_partial,
    start_research,
)


router = APIRouter(
    tags=["Research"],
)


@router.get(
    "/api/research",
    response_model=list[ResearchRead],
)
def list_research_runs_endpoint(
    status_filter: ResearchStatus | None = Query(
        default=None,
        alias="status",
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=100,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    db: Session = Depends(get_db),
):
    return list_research_runs(
        db,
        research_status=status_filter,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/api/leads/{lead_id}/research",
    response_model=ResearchRead,
    status_code=status.HTTP_201_CREATED,
)
def create_research_endpoint(
    lead_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        return create_research_run(
            db,
            lead_id=lead_id,
        )

    except LeadNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except InvalidLeadResearchStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/api/leads/{lead_id}/research",
    response_model=list[ResearchRead],
)
def list_research_endpoint(
    lead_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        return list_research_for_lead(
            db,
            lead_id=lead_id,
        )

    except LeadNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/api/research/claim",
    response_model=ResearchRead | None,
)
def claim_research_endpoint(
    db: Session = Depends(get_db),
):
    try:
        return claim_next_research(
            db,
        )

    except LeadNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except InvalidLeadResearchStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/api/research/{research_id}/context",
    response_model=ResearchContext,
)
def get_research_context_endpoint(
    research_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        return get_research_context(
            db,
            research_id=research_id,
        )

    except ResearchNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except ResearchContextIntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/api/research/{research_id}",
    response_model=ResearchDetail,
)
def get_research_endpoint(
    research_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        research, sources = get_research_detail(
            db,
            research_id=research_id,
        )

        research_data = (
            ResearchRead
            .model_validate(research)
            .model_dump()
        )

        source_data = [
            ResearchSourceRead.model_validate(
                source
            )
            for source in sources
        ]

        return ResearchDetail(
            **research_data,
            sources=source_data,
        )

    except ResearchNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.patch(
    "/api/research/{research_id}/start",
    response_model=ResearchRead,
)
def start_research_endpoint(
    research_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        return start_research(
            db,
            research_id=research_id,
        )

    except ResearchNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except InvalidResearchTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/api/research/{research_id}/sources",
    response_model=ResearchSourceRead,
    status_code=status.HTTP_201_CREATED,
)
def add_research_source_endpoint(
    research_id: UUID,
    data: ResearchSourceCreate,
    db: Session = Depends(get_db),
):
    try:
        return add_research_source(
            db,
            research_id=research_id,
            data=data,
        )

    except ResearchNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.patch(
    "/api/research/{research_id}/complete",
    response_model=ResearchRead,
)
def complete_research_endpoint(
    research_id: UUID,
    data: ResearchComplete,
    db: Session = Depends(get_db),
):
    try:
        return complete_research(
            db,
            research_id=research_id,
            data=data,
        )

    except ResearchNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except InvalidResearchTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.patch(
    "/api/research/{research_id}/partial",
    response_model=ResearchRead,
)
def partial_research_endpoint(
    research_id: UUID,
    data: ResearchPartial,
    db: Session = Depends(get_db),
):
    try:
        return mark_research_partial(
            db,
            research_id=research_id,
            data=data,
        )

    except ResearchNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except InvalidResearchTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.patch(
    "/api/research/{research_id}/fail",
    response_model=ResearchRead,
)
def fail_research_endpoint(
    research_id: UUID,
    data: ResearchFail,
    db: Session = Depends(get_db),
):
    try:
        return fail_research(
            db,
            research_id=research_id,
            data=data,
        )

    except ResearchNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except InvalidResearchTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
