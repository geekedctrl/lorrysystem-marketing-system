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
from app.schemas.lead import (
    LeadCreate,
    LeadPriority,
    LeadRead,
    LeadStatus,
    LeadStatusUpdate,
)
from app.services.lead_service import (
    CompanyNotFoundError,
    ContactCompanyMismatchError,
    ContactNotFoundError,
    DuplicateLeadError,
    ICPProfileNotFoundError,
    InvalidLeadTransitionError,
    LeadNotFoundError,
    create_lead,
    get_lead,
    list_leads,
    transition_lead,
)


router = APIRouter(
    prefix="/api/leads",
    tags=["Leads"],
)


@router.post(
    "",
    response_model=LeadRead,
    status_code=status.HTTP_201_CREATED,
)
def create_lead_endpoint(
    data: LeadCreate,
    db: Session = Depends(get_db),
):
    try:
        return create_lead(
            db,
            data,
        )

    except CompanyNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except ContactNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except ICPProfileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except ContactCompanyMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except DuplicateLeadError as exc:
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

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "",
    response_model=list[LeadRead],
)
def list_leads_endpoint(
    company_id: UUID | None = None,
    status_filter: LeadStatus | None = Query(
        default=None,
        alias="status",
    ),
    priority: LeadPriority | None = None,
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
    return list_leads(
        db,
        company_id=company_id,
        status=status_filter,
        priority=priority,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{lead_id}",
    response_model=LeadRead,
)
def get_lead_endpoint(
    lead_id: UUID,
    db: Session = Depends(get_db),
):
    lead = get_lead(
        db,
        lead_id,
    )

    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found.",
        )

    return lead


@router.patch(
    "/{lead_id}/status",
    response_model=LeadRead,
)
def update_lead_status_endpoint(
    lead_id: UUID,
    data: LeadStatusUpdate,
    db: Session = Depends(get_db),
):
    try:
        return transition_lead(
            db,
            lead_id=lead_id,
            new_status=data.status,
            reason=data.reason,
            note=data.note,
            closed_by=data.closed_by,
        )

    except LeadNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except InvalidLeadTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
