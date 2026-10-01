from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.marketing_action import (
    MarketingActionCreate,
    MarketingActionRead,
    MarketingActionUpdate,
)
from app.services.marketing_action_service import (
    InvalidMarketingActionError,
    MarketingActionContactMismatchError,
    MarketingActionContactNotFoundError,
    MarketingActionLeadNotFoundError,
    MarketingActionNotAllowedError,
    MarketingActionNotFoundError,
    cancel_action,
    create_action,
    get_action,
    list_actions_for_lead,
    update_draft,
)


router = APIRouter(
    tags=["Marketing Actions"],
)


@router.post(
    "/api/leads/{lead_id}/actions",
    response_model=MarketingActionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_action_endpoint(
    lead_id: UUID,
    data: MarketingActionCreate,
    db: Session = Depends(get_db),
):
    try:
        return create_action(
            db,
            lead_id=lead_id,
            data=data,
        )

    except MarketingActionLeadNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except MarketingActionContactNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except MarketingActionContactMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except MarketingActionNotAllowedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except InvalidMarketingActionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get(
    "/api/leads/{lead_id}/actions",
    response_model=list[MarketingActionRead],
)
def list_actions_endpoint(
    lead_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        return list_actions_for_lead(
            db,
            lead_id=lead_id,
        )

    except MarketingActionLeadNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/api/actions/{action_id}",
    response_model=MarketingActionRead,
)
def get_action_endpoint(
    action_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        return get_action(
            db,
            action_id=action_id,
        )

    except MarketingActionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.patch(
    "/api/actions/{action_id}",
    response_model=MarketingActionRead,
)
def update_action_endpoint(
    action_id: UUID,
    data: MarketingActionUpdate,
    db: Session = Depends(get_db),
):
    try:
        return update_draft(
            db,
            action_id=action_id,
            data=data,
        )

    except MarketingActionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except MarketingActionLeadNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except MarketingActionContactNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except MarketingActionContactMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except MarketingActionNotAllowedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except InvalidMarketingActionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.patch(
    "/api/actions/{action_id}/cancel",
    response_model=MarketingActionRead,
)
def cancel_action_endpoint(
    action_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        return cancel_action(
            db,
            action_id=action_id,
        )

    except MarketingActionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except MarketingActionNotAllowedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
