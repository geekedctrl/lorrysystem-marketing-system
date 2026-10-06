from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.companies import Contact
from app.models.leads import (
    Lead,
    ProductMatch,
)
from app.models.marketing import (
    Event,
    MarketingAction,
)
from app.schemas.marketing_action import (
    MarketingActionCreate,
    MarketingActionUpdate,
)


# ============================================================
# Exceptions
# ============================================================

class MarketingActionLeadNotFoundError(Exception):
    pass


class MarketingActionNotFoundError(Exception):
    pass


class MarketingActionContactNotFoundError(Exception):
    pass


class MarketingActionContactMismatchError(Exception):
    pass


class MarketingActionNotAllowedError(Exception):
    pass


class InvalidMarketingActionError(Exception):
    pass


# ============================================================
# Rules
# ============================================================

TERMINAL_LEAD_STATUSES = {
    "CONVERTED",
    "DISQUALIFIED",
    "LOST",
}


VALID_CHANNEL_ACTION_PAIRS = {
    "EMAIL": {
        "EMAIL",
        "FOLLOW_UP",
    },
    "LINKEDIN": {
        "POST",
        "COMMENT",
        "DIRECT_MESSAGE",
    },
    "FACEBOOK": {
        "POST",
    },
    "INSTAGRAM": {
        "POST",
    },
    "X": {
        "POST",
    },
}


CANCELLABLE_STATUSES = {
    "DRAFT",
}


# ============================================================
# Validation Helpers
# ============================================================

def validate_channel_action_pair(
    *,
    channel: str,
    action_type: str,
) -> None:

    valid_types = (
        VALID_CHANNEL_ACTION_PAIRS.get(
            channel,
            set(),
        )
    )

    if action_type not in valid_types:
        raise InvalidMarketingActionError(
            f"{channel} + {action_type} "
            "is not a supported Marketing Action."
        )


def validate_lead_eligibility(
    db: Session,
    *,
    lead_id: UUID,
) -> Lead:

    lead = db.get(
        Lead,
        lead_id,
    )

    if lead is None:
        raise MarketingActionLeadNotFoundError(
            "Lead not found."
        )

    if lead.status in TERMINAL_LEAD_STATUSES:
        raise MarketingActionNotAllowedError(
            f"Lead in {lead.status} status "
            "cannot create or edit "
            "Marketing Actions."
        )

    if lead.current_score is None:
        raise MarketingActionNotAllowedError(
            "Lead has no current score. "
            "Complete Scoring first."
        )

    match_statement = (
        select(ProductMatch.id)
        .where(
            ProductMatch.lead_id == lead.id
        )
        .limit(1)
    )

    product_match_id = db.scalars(
        match_statement
    ).first()

    if product_match_id is None:
        raise MarketingActionNotAllowedError(
            "Lead has no ProductMatch. "
            "Complete Product Matching first."
        )

    return lead


def validate_contact(
    db: Session,
    *,
    lead: Lead,
    contact_id: UUID | None,
    channel: str,
    action_type: str,
) -> Contact | None:

    contact_required = (
        channel == "EMAIL"
        or action_type == "DIRECT_MESSAGE"
    )

    if contact_required and contact_id is None:
        raise InvalidMarketingActionError(
            "contact_id is required for "
            f"{channel} {action_type}."
        )

    if contact_id is None:
        return None

    contact = db.get(
        Contact,
        contact_id,
    )

    if contact is None:
        raise MarketingActionContactNotFoundError(
            "Contact not found."
        )

    if contact.company_id != lead.company_id:
        raise MarketingActionContactMismatchError(
            "Contact does not belong to "
            "the lead's company."
        )

    if channel == "EMAIL":
        if (
            contact.email is None
            or not contact.email.strip()
        ):
            raise InvalidMarketingActionError(
                "EMAIL actions require a contact "
                "with an email address."
            )

    return contact


def validate_subject(
    *,
    channel: str,
    subject: str | None,
) -> None:

    if channel == "EMAIL":
        if (
            subject is None
            or not subject.strip()
        ):
            raise InvalidMarketingActionError(
                "EMAIL actions require "
                "a non-blank subject."
            )


# ============================================================
# Create
# ============================================================

def create_action(
    db: Session,
    *,
    lead_id: UUID,
    data: MarketingActionCreate,
    commit: bool = True,
) -> MarketingAction:

    lead = validate_lead_eligibility(
        db,
        lead_id=lead_id,
    )

    validate_channel_action_pair(
        channel=data.channel,
        action_type=data.action_type,
    )

    validate_subject(
        channel=data.channel,
        subject=data.subject,
    )

    validate_contact(
        db,
        lead=lead,
        contact_id=data.contact_id,
        channel=data.channel,
        action_type=data.action_type,
    )

    action = MarketingAction(
        lead_id=lead.id,
        contact_id=data.contact_id,
        channel=data.channel,
        action_type=data.action_type,
        subject=data.subject,
        content=data.content,
        status="DRAFT",
        scheduled_at=data.scheduled_at,
        created_by=data.created_by,
    )

    db.add(action)
    db.flush()

    event = Event(
        event_type="marketing_action_created",
        entity_type="MARKETING_ACTION",
        entity_id=action.id,
        actor_type="API",
        actor_id="marketing-api",
        metadata_json={
            "lead_id": str(
                lead.id
            ),
            "action_id": str(
                action.id
            ),
            "contact_id": (
                str(data.contact_id)
                if data.contact_id
                else None
            ),
            "channel": action.channel,
            "action_type": (
                action.action_type
            ),
            "status": action.status,
        },
    )

    db.add(event)

    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(action)

    return action


# ============================================================
# Retrieve
# ============================================================

def get_action(
    db: Session,
    *,
    action_id: UUID,
) -> MarketingAction:

    action = db.get(
        MarketingAction,
        action_id,
    )

    if action is None:
        raise MarketingActionNotFoundError(
            "Marketing Action not found."
        )

    return action


def list_actions_for_lead(
    db: Session,
    *,
    lead_id: UUID,
) -> list[MarketingAction]:

    lead = db.get(
        Lead,
        lead_id,
    )

    if lead is None:
        raise MarketingActionLeadNotFoundError(
            "Lead not found."
        )

    statement = (
        select(MarketingAction)
        .where(
            MarketingAction.lead_id == lead_id
        )
        .order_by(
            MarketingAction.created_at.desc()
        )
    )

    return list(
        db.scalars(statement).all()
    )


# ============================================================
# Update Draft
# ============================================================

def update_draft(
    db: Session,
    *,
    action_id: UUID,
    data: MarketingActionUpdate,
) -> MarketingAction:

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
        raise MarketingActionNotFoundError(
            "Marketing Action not found."
        )

    if action.status != "DRAFT":
        raise MarketingActionNotAllowedError(
            "Only DRAFT Marketing Actions "
            "can be edited."
        )

    if action.lead_id is None:
        raise MarketingActionNotAllowedError(
            "Marketing Action is no longer "
            "linked to a lead."
        )

    lead = validate_lead_eligibility(
        db,
        lead_id=action.lead_id,
    )

    fields = data.model_fields_set

    if (
        "content" in fields
        and data.content is None
    ):
        raise InvalidMarketingActionError(
            "content cannot be null."
        )

    if "contact_id" in fields:
        new_contact_id = data.contact_id
    else:
        new_contact_id = action.contact_id

    if "subject" in fields:
        new_subject = data.subject
    else:
        new_subject = action.subject

    validate_subject(
        channel=action.channel,
        subject=new_subject,
    )

    validate_contact(
        db,
        lead=lead,
        contact_id=new_contact_id,
        channel=action.channel,
        action_type=action.action_type,
    )

    changed_fields: list[str] = []

    if "contact_id" in fields:
        action.contact_id = data.contact_id
        changed_fields.append(
            "contact_id"
        )

    if "subject" in fields:
        action.subject = data.subject
        changed_fields.append(
            "subject"
        )

    if "content" in fields:
        action.content = data.content
        changed_fields.append(
            "content"
        )

    if "scheduled_at" in fields:
        action.scheduled_at = (
            data.scheduled_at
        )
        changed_fields.append(
            "scheduled_at"
        )

    if not changed_fields:
        raise InvalidMarketingActionError(
            "No editable fields were provided."
        )

    action.updated_at = datetime.now(
        timezone.utc
    )

    db.flush()

    event = Event(
        event_type="marketing_action_updated",
        entity_type="MARKETING_ACTION",
        entity_id=action.id,
        actor_type="API",
        actor_id="marketing-api",
        metadata_json={
            "lead_id": str(
                lead.id
            ),
            "action_id": str(
                action.id
            ),
            "contact_id": (
                str(action.contact_id)
                if action.contact_id
                else None
            ),
            "channel": action.channel,
            "action_type": (
                action.action_type
            ),
            "status": action.status,
            "changed_fields": (
                changed_fields
            ),
        },
    )

    db.add(event)

    db.commit()
    db.refresh(action)

    return action


# ============================================================
# Cancel
# ============================================================

def cancel_action(
    db: Session,
    *,
    action_id: UUID,
) -> MarketingAction:

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
        raise MarketingActionNotFoundError(
            "Marketing Action not found."
        )

    if action.status not in CANCELLABLE_STATUSES:
        raise MarketingActionNotAllowedError(
            f"Marketing Action in "
            f"{action.status} status "
            "cannot be cancelled."
        )

    previous_status = action.status

    action.status = "CANCELLED"
    action.updated_at = datetime.now(
        timezone.utc
    )

    db.flush()

    event = Event(
        event_type=(
            "marketing_action_cancelled"
        ),
        entity_type="MARKETING_ACTION",
        entity_id=action.id,
        actor_type="API",
        actor_id="marketing-api",
        metadata_json={
            "lead_id": (
                str(action.lead_id)
                if action.lead_id
                else None
            ),
            "action_id": str(
                action.id
            ),
            "contact_id": (
                str(action.contact_id)
                if action.contact_id
                else None
            ),
            "channel": action.channel,
            "action_type": (
                action.action_type
            ),
            "previous_status": (
                previous_status
            ),
            "status": (
                action.status
            ),
        },
    )

    db.add(event)

    db.commit()
    db.refresh(action)

    return action
