from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.marketing import (
    ApprovalRequest,
    Event,
    MarketingAction,
)
from app.schemas.approval import (
    ApprovalDecision,
    ApprovalReject,
    ApprovalRequestChanges,
)
from app.services.marketing_action_service import (
    InvalidMarketingActionError,
    MarketingActionContactMismatchError,
    MarketingActionContactNotFoundError,
    MarketingActionLeadNotFoundError,
    MarketingActionNotAllowedError,
    validate_channel_action_pair,
    validate_contact,
    validate_lead_eligibility,
    validate_subject,
)


class ApprovalNotFoundError(Exception):
    pass


class ApprovalActionNotFoundError(Exception):
    pass


class ApprovalNotAllowedError(Exception):
    pass


class ApprovalConflictError(Exception):
    pass


def serialize_approval(
    approval: ApprovalRequest,
    action: MarketingAction,
) -> dict:
    return {
        "id": approval.id,
        "marketing_action_id": (
            approval.marketing_action_id
        ),
        "status": approval.status,
        "requested_at": (
            approval.requested_at
        ),
        "decided_by": approval.decided_by,
        "decided_at": approval.decided_at,
        "reviewer_notes": (
            approval.reviewer_notes
        ),
        "content_snapshot": (
            approval.content_snapshot
        ),
        "created_at": approval.created_at,
        "updated_at": approval.updated_at,
        "marketing_action_status": (
            action.status
        ),
    }


def build_content_snapshot(
    action: MarketingAction,
    db: Session | None = None,
) -> dict:
    from app.models.companies import Contact
    contact = db.get(Contact, action.contact_id) if db and action.contact_id else None
    return {
        "recipient_email": contact.email.strip().lower() if contact and contact.email and action.channel == "EMAIL" else None,
        "marketing_action_id": str(
            action.id
        ),
        "lead_id": (
            str(action.lead_id)
            if action.lead_id
            else None
        ),
        "contact_id": (
            str(action.contact_id)
            if action.contact_id
            else None
        ),
        "channel": action.channel,
        "action_type": action.action_type,
        "subject": action.subject,
        "content": action.content,
        "scheduled_at": (
            action.scheduled_at.isoformat()
            if action.scheduled_at
            else None
        ),
        "created_by": action.created_by,
    }


def validate_action_for_submission(
    db: Session,
    *,
    action: MarketingAction,
) -> None:

    if action.status != "DRAFT":
        raise ApprovalNotAllowedError(
            "Only DRAFT Marketing Actions "
            "can be submitted for approval."
        )

    if action.lead_id is None:
        raise ApprovalNotAllowedError(
            "Marketing Action is no longer "
            "linked to a lead."
        )

    if (
        action.content is None
        or not action.content.strip()
    ):
        raise ApprovalNotAllowedError(
            "Marketing Action content "
            "is invalid."
        )

    if action.scheduled_at is not None:
        if (
            action.scheduled_at.tzinfo is None
            or action.scheduled_at.utcoffset()
            is None
        ):
            raise ApprovalNotAllowedError(
                "scheduled_at must include "
                "a timezone."
            )

        if action.scheduled_at <= datetime.now(
            timezone.utc
        ):
            raise ApprovalNotAllowedError(
                "scheduled_at is no longer "
                "in the future."
            )

    try:
        lead = validate_lead_eligibility(
            db,
            lead_id=action.lead_id,
        )

        validate_channel_action_pair(
            channel=action.channel,
            action_type=action.action_type,
        )

        validate_subject(
            channel=action.channel,
            subject=action.subject,
        )

        validate_contact(
            db,
            lead=lead,
            contact_id=action.contact_id,
            channel=action.channel,
            action_type=action.action_type,
        )

    except (
        InvalidMarketingActionError,
        MarketingActionContactMismatchError,
        MarketingActionContactNotFoundError,
        MarketingActionLeadNotFoundError,
        MarketingActionNotAllowedError,
    ) as exc:
        raise ApprovalNotAllowedError(
            str(exc)
        ) from exc


def submit_action_for_approval(
    db: Session,
    *,
    action_id: UUID,
    commit: bool = True,
) -> dict:

    action = (
        db.scalars(
            select(MarketingAction)
            .where(
                MarketingAction.id
                == action_id
            )
            .with_for_update()
        )
        .first()
    )

    if action is None:
        raise ApprovalActionNotFoundError(
            "Marketing Action not found."
        )

    validate_action_for_submission(
        db,
        action=action,
    )

    pending = (
        db.scalars(
            select(ApprovalRequest.id)
            .where(
                ApprovalRequest.marketing_action_id
                == action.id,
                ApprovalRequest.status
                == "PENDING",
            )
            .limit(1)
        )
        .first()
    )

    if pending is not None:
        raise ApprovalConflictError(
            "Marketing Action already has "
            "a pending ApprovalRequest."
        )

    now = datetime.now(timezone.utc)

    approval = ApprovalRequest(
        marketing_action_id=action.id,
        status="PENDING",
        content_snapshot=(
            build_content_snapshot(
                action, db
            )
        ),
    )

    db.add(approval)

    action.status = "PENDING_APPROVAL"
    action.updated_at = now

    try:
        db.flush()

        db.add(
            Event(
                event_type="approval_requested",
                entity_type="APPROVAL",
                entity_id=approval.id,
                actor_type="API",
                actor_id="marketing-api",
                metadata_json={
                    "approval_id": str(
                        approval.id
                    ),
                    "marketing_action_id": str(
                        action.id
                    ),
                    "lead_id": (
                        str(action.lead_id)
                        if action.lead_id
                        else None
                    ),
                    "channel": action.channel,
                    "action_type": (
                        action.action_type
                    ),
                    "approval_status": (
                        approval.status
                    ),
                    "marketing_action_status": (
                        action.status
                    ),
                },
            )
        )

        db.add(
            Event(
                event_type=(
                    "marketing_action_submitted"
                ),
                entity_type=(
                    "MARKETING_ACTION"
                ),
                entity_id=action.id,
                actor_type="API",
                actor_id="marketing-api",
                metadata_json={
                    "approval_id": str(
                        approval.id
                    ),
                    "marketing_action_id": str(
                        action.id
                    ),
                    "lead_id": (
                        str(action.lead_id)
                        if action.lead_id
                        else None
                    ),
                    "status": action.status,
                },
            )
        )

        if commit:
            db.commit()
        else:
            db.flush()

    except IntegrityError as exc:
        db.rollback()

        raise ApprovalConflictError(
            "Marketing Action already has "
            "a pending ApprovalRequest."
        ) from exc

    db.refresh(approval)
    db.refresh(action)

    return serialize_approval(
        approval,
        action,
    )


def get_approval(
    db: Session,
    *,
    approval_id: UUID,
) -> dict:

    approval = db.get(
        ApprovalRequest,
        approval_id,
    )

    if approval is None:
        raise ApprovalNotFoundError(
            "ApprovalRequest not found."
        )

    action = db.get(
        MarketingAction,
        approval.marketing_action_id,
    )

    if action is None:
        raise ApprovalActionNotFoundError(
            "Related Marketing Action "
            "not found."
        )

    return serialize_approval(
        approval,
        action,
    )


def list_approvals(
    db: Session,
    *,
    status_filter: str | None = None,
) -> list[dict]:

    statement = select(
        ApprovalRequest
    )

    if status_filter is not None:
        statement = statement.where(
            ApprovalRequest.status
            == status_filter
        )

    statement = statement.order_by(
        ApprovalRequest.requested_at.desc(),
        ApprovalRequest.created_at.desc(),
    )

    approvals = list(
        db.scalars(statement).all()
    )

    result: list[dict] = []

    for approval in approvals:
        action = db.get(
            MarketingAction,
            approval.marketing_action_id,
        )

        if action is None:
            continue

        result.append(
            serialize_approval(
                approval,
                action,
            )
        )

    return result


def list_action_approvals(
    db: Session,
    *,
    action_id: UUID,
) -> list[dict]:

    action = db.get(
        MarketingAction,
        action_id,
    )

    if action is None:
        raise ApprovalActionNotFoundError(
            "Marketing Action not found."
        )

    statement = (
        select(ApprovalRequest)
        .where(
            ApprovalRequest.marketing_action_id
            == action_id
        )
        .order_by(
            ApprovalRequest.requested_at.desc(),
            ApprovalRequest.created_at.desc(),
        )
    )

    approvals = list(
        db.scalars(statement).all()
    )

    return [
        serialize_approval(
            approval,
            action,
        )
        for approval in approvals
    ]


def get_pending_for_decision(
    db: Session,
    *,
    approval_id: UUID,
) -> tuple[
    ApprovalRequest,
    MarketingAction,
]:

    approval = (
        db.scalars(
            select(ApprovalRequest)
            .where(
                ApprovalRequest.id
                == approval_id
            )
            .with_for_update()
        )
        .first()
    )

    if approval is None:
        raise ApprovalNotFoundError(
            "ApprovalRequest not found."
        )

    if approval.status != "PENDING":
        raise ApprovalNotAllowedError(
            "Only PENDING ApprovalRequests "
            "can be decided."
        )

    action = (
        db.scalars(
            select(MarketingAction)
            .where(
                MarketingAction.id
                == approval.marketing_action_id
            )
            .with_for_update()
        )
        .first()
    )

    if action is None:
        raise ApprovalActionNotFoundError(
            "Related Marketing Action "
            "not found."
        )

    if action.status != "PENDING_APPROVAL":
        raise ApprovalNotAllowedError(
            "Related Marketing Action is not "
            "PENDING_APPROVAL."
        )

    return approval, action


def apply_decision(
    db: Session,
    *,
    approval_id: UUID,
    decided_by: str,
    reviewer_notes: str | None,
    approval_status: str,
    action_status: str,
    event_type: str,
) -> dict:

    approval, action = (
        get_pending_for_decision(
            db,
            approval_id=approval_id,
        )
    )

    previous_approval_status = (
        approval.status
    )

    if approval_status == "APPROVED":
        from app.services.preparation_review import review_context
        readiness = review_context(db, action)
        if not readiness["current"]:
            raise ApprovalNotAllowedError(readiness["reason"])

    previous_action_status = (
        action.status
    )

    now = datetime.now(timezone.utc)

    approval.status = approval_status
    approval.decided_by = decided_by
    approval.decided_at = now
    approval.reviewer_notes = reviewer_notes
    approval.updated_at = now

    action.status = action_status
    action.updated_at = now

    db.flush()

    db.add(
        Event(
            event_type=event_type,
            entity_type="APPROVAL",
            entity_id=approval.id,
            actor_type="API",
            actor_id="marketing-api",
            metadata_json={
                "approval_id": str(
                    approval.id
                ),
                "marketing_action_id": str(
                    action.id
                ),
                "lead_id": (
                    str(action.lead_id)
                    if action.lead_id
                    else None
                ),
                "decided_by": decided_by,
                "previous_approval_status": (
                    previous_approval_status
                ),
                "approval_status": (
                    approval.status
                ),
                "previous_marketing_action_status": (
                    previous_action_status
                ),
                "marketing_action_status": (
                    action.status
                ),
            },
        )
    )

    db.commit()

    db.refresh(approval)
    db.refresh(action)

    return serialize_approval(
        approval,
        action,
    )


def approve(
    db: Session,
    *,
    approval_id: UUID,
    data: ApprovalDecision,
) -> dict:
    return apply_decision(
        db,
        approval_id=approval_id,
        decided_by=data.decided_by,
        reviewer_notes=data.reviewer_notes,
        approval_status="APPROVED",
        action_status="APPROVED",
        event_type="approval_approved",
    )


def reject(
    db: Session,
    *,
    approval_id: UUID,
    data: ApprovalReject,
) -> dict:
    return apply_decision(
        db,
        approval_id=approval_id,
        decided_by=data.decided_by,
        reviewer_notes=data.reviewer_notes,
        approval_status="REJECTED",
        action_status="REJECTED",
        event_type="approval_rejected",
    )


def request_changes(
    db: Session,
    *,
    approval_id: UUID,
    data: ApprovalRequestChanges,
) -> dict:
    return apply_decision(
        db,
        approval_id=approval_id,
        decided_by=data.decided_by,
        reviewer_notes=data.reviewer_notes,
        approval_status=(
            "CHANGES_REQUESTED"
        ),
        action_status="DRAFT",
        event_type=(
            "approval_changes_requested"
        ),
    )
