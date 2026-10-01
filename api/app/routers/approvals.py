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
from app.schemas.approval import (
    ApprovalDecision,
    ApprovalRead,
    ApprovalReject,
    ApprovalRequestChanges,
    ApprovalStatus,
)
from app.services.approval_service import (
    ApprovalActionNotFoundError,
    ApprovalConflictError,
    ApprovalNotAllowedError,
    ApprovalNotFoundError,
    approve,
    get_approval,
    list_action_approvals,
    list_approvals,
    reject,
    request_changes,
    submit_action_for_approval,
)


router = APIRouter(
    tags=["Approvals"],
)


def raise_approval_http_error(
    exc: Exception,
) -> None:

    if isinstance(
        exc,
        (
            ApprovalNotFoundError,
            ApprovalActionNotFoundError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    if isinstance(
        exc,
        (
            ApprovalNotAllowedError,
            ApprovalConflictError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    raise exc


@router.post(
    "/api/actions/{action_id}/submit",
    response_model=ApprovalRead,
    status_code=status.HTTP_201_CREATED,
)
def submit_action_endpoint(
    action_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        return submit_action_for_approval(
            db,
            action_id=action_id,
        )

    except (
        ApprovalNotFoundError,
        ApprovalActionNotFoundError,
        ApprovalNotAllowedError,
        ApprovalConflictError,
    ) as exc:
        raise_approval_http_error(exc)


@router.get(
    "/api/approvals",
    response_model=list[ApprovalRead],
)
def list_approvals_endpoint(
    approval_status: ApprovalStatus | None = Query(
        default=None,
        alias="status",
    ),
    db: Session = Depends(get_db),
):
    return list_approvals(
        db,
        status_filter=approval_status,
    )


@router.get(
    "/api/approvals/{approval_id}",
    response_model=ApprovalRead,
)
def get_approval_endpoint(
    approval_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        return get_approval(
            db,
            approval_id=approval_id,
        )

    except (
        ApprovalNotFoundError,
        ApprovalActionNotFoundError,
    ) as exc:
        raise_approval_http_error(exc)


@router.get(
    "/api/actions/{action_id}/approvals",
    response_model=list[ApprovalRead],
)
def action_approval_history_endpoint(
    action_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        return list_action_approvals(
            db,
            action_id=action_id,
        )

    except ApprovalActionNotFoundError as exc:
        raise_approval_http_error(exc)


@router.patch(
    "/api/approvals/{approval_id}/approve",
    response_model=ApprovalRead,
)
def approve_endpoint(
    approval_id: UUID,
    data: ApprovalDecision,
    db: Session = Depends(get_db),
):
    try:
        return approve(
            db,
            approval_id=approval_id,
            data=data,
        )

    except (
        ApprovalNotFoundError,
        ApprovalActionNotFoundError,
        ApprovalNotAllowedError,
    ) as exc:
        raise_approval_http_error(exc)


@router.patch(
    "/api/approvals/{approval_id}/reject",
    response_model=ApprovalRead,
)
def reject_endpoint(
    approval_id: UUID,
    data: ApprovalReject,
    db: Session = Depends(get_db),
):
    try:
        return reject(
            db,
            approval_id=approval_id,
            data=data,
        )

    except (
        ApprovalNotFoundError,
        ApprovalActionNotFoundError,
        ApprovalNotAllowedError,
    ) as exc:
        raise_approval_http_error(exc)


@router.patch(
    (
        "/api/approvals/"
        "{approval_id}/request-changes"
    ),
    response_model=ApprovalRead,
)
def request_changes_endpoint(
    approval_id: UUID,
    data: ApprovalRequestChanges,
    db: Session = Depends(get_db),
):
    try:
        return request_changes(
            db,
            approval_id=approval_id,
            data=data,
        )

    except (
        ApprovalNotFoundError,
        ApprovalActionNotFoundError,
        ApprovalNotAllowedError,
    ) as exc:
        raise_approval_http_error(exc)
