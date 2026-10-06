from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.catalog import ICPProfile
from app.models.companies import Company, Contact
from app.models.leads import Lead
from app.models.marketing import Event
from app.schemas.lead import LeadCreate


# ============================================================
# Exceptions
# ============================================================

class CompanyNotFoundError(Exception):
    pass


class ContactNotFoundError(Exception):
    pass


class ContactCompanyMismatchError(Exception):
    pass


class ICPProfileNotFoundError(Exception):
    pass


class LeadNotFoundError(Exception):
    pass


class InvalidLeadTransitionError(Exception):
    pass


class DuplicateLeadError(Exception):
    def __init__(self, lead: Lead):
        self.lead = lead

        super().__init__(
            "An active lead already exists "
            "for this company and ICP profile."
        )


# ============================================================
# Lead Lifecycle
# ============================================================

BASE_TRANSITIONS = {
    "DISCOVERED": {
        "RESEARCHING",
    },
    "RESEARCHING": {
        "QUALIFIED",
    },
    "QUALIFIED": {
        "READY_FOR_OUTREACH",
    },
    "READY_FOR_OUTREACH": {
        "CONTACTED",
    },
    "CONTACTED": {
        "REPLIED",
    },
    "REPLIED": {
        "CONVERTED",
    },
    "CONVERTED": set(),
    "DISQUALIFIED": set(),
    "LOST": set(),
}


ACTIVE_STATUSES = {
    "DISCOVERED",
    "RESEARCHING",
    "QUALIFIED",
    "READY_FOR_OUTREACH",
    "CONTACTED",
    "REPLIED",
}


TERMINAL_STATUSES = {
    "CONVERTED",
    "DISQUALIFIED",
    "LOST",
}


CLOSURE_REASON_STATUS = {
    "NO_RESPONSE": "LOST",
    "NOT_INTERESTED": "LOST",
    "OTHER": "LOST",
    "WRONG_FIT": "DISQUALIFIED",
    "DUPLICATE": "DISQUALIFIED",
}


CLOSURE_STATUSES = {
    "LOST",
    "DISQUALIFIED",
}


def allowed_transitions(
    status: str,
) -> set[str]:

    transitions = set(
        BASE_TRANSITIONS.get(
            status,
            set(),
        )
    )

    if status in ACTIVE_STATUSES:
        transitions.update(
            {
                "DISQUALIFIED",
                "LOST",
            }
        )

    return transitions


# ============================================================
# Duplicate Lead Detection
# ============================================================

def find_active_duplicate_lead(
    db: Session,
    *,
    company_id: UUID,
    icp_profile_id: UUID,
) -> Lead | None:
    """
    Find an existing active lead for the same:

        company_id + icp_profile_id

    Primary contact is intentionally not used as part
    of duplicate detection because a contact can change
    while the sales opportunity remains the same.
    """

    statement = select(Lead).where(
        Lead.company_id == company_id,
        Lead.icp_profile_id == icp_profile_id,
        Lead.status.in_(ACTIVE_STATUSES),
    )

    return db.scalars(
        statement
    ).first()


# ============================================================
# Create Lead
# ============================================================

def create_lead(
    db: Session,
    data: LeadCreate,
) -> Lead:

    # --------------------------------------------------------
    # 1. Validate company
    # --------------------------------------------------------

    company = db.get(
        Company,
        data.company_id,
    )

    if company is None:
        raise CompanyNotFoundError(
            "Company not found."
        )

    # --------------------------------------------------------
    # 2. Validate primary contact
    # --------------------------------------------------------

    if data.primary_contact_id:
        contact = db.get(
            Contact,
            data.primary_contact_id,
        )

        if contact is None:
            raise ContactNotFoundError(
                "Primary contact not found."
            )

        if contact.company_id != data.company_id:
            raise ContactCompanyMismatchError(
                "Primary contact does not belong "
                "to the selected company."
            )

    # --------------------------------------------------------
    # 3. Validate ICP profile
    # --------------------------------------------------------
    #
    # ICP is now mandatory for every lead.
    # LeadCreate should require icp_profile_id,
    # and PostgreSQL will also enforce NOT NULL.
    # --------------------------------------------------------

    icp = db.get(
        ICPProfile,
        data.icp_profile_id,
    )

    if icp is None:
        raise ICPProfileNotFoundError(
            "ICP profile not found."
        )

    # --------------------------------------------------------
    # 4. Check active lead duplicate
    # --------------------------------------------------------

    duplicate = find_active_duplicate_lead(
        db,
        company_id=data.company_id,
        icp_profile_id=data.icp_profile_id,
    )

    if duplicate:
        raise DuplicateLeadError(
            duplicate
        )

    # --------------------------------------------------------
    # 5. Create lead
    # --------------------------------------------------------

    lead = Lead(
        company_id=data.company_id,
        primary_contact_id=(
            data.primary_contact_id
        ),
        icp_profile_id=(
            data.icp_profile_id
        ),
        priority=data.priority,
    )

    db.add(lead)

    try:
        # Generate the UUID before commit so it can
        # be referenced by the event record.
        db.flush()

        # ----------------------------------------------------
        # 6. Log lead_discovered event
        # ----------------------------------------------------

        event = Event(
            event_type="lead_discovered",
            entity_type="LEAD",
            entity_id=lead.id,
            actor_type="API",
            actor_id="marketing-api",
            metadata_json={
                "company_id": str(
                    data.company_id
                ),
                "primary_contact_id": (
                    str(data.primary_contact_id)
                    if data.primary_contact_id
                    else None
                ),
                "icp_profile_id": str(
                    data.icp_profile_id
                ),
                "priority": data.priority,
            },
        )

        db.add(event)

        db.commit()
        db.refresh(lead)

        return lead

    except IntegrityError as exc:
        db.rollback()

        # This is the second layer of protection.
        # Once migration 003 adds the partial unique
        # active-lead index, PostgreSQL may reject a
        # race-condition duplicate here.
        raise ValueError(
            "Lead conflicts with an existing record."
        ) from exc


# ============================================================
# Get Lead
# ============================================================

def get_lead(
    db: Session,
    lead_id: UUID,
) -> Lead | None:

    return db.get(
        Lead,
        lead_id,
    )


# ============================================================
# List Leads
# ============================================================

def list_leads(
    db: Session,
    *,
    company_id: UUID | None = None,
    status: str | None = None,
    priority: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Lead]:

    statement = select(Lead)

    if company_id is not None:
        statement = statement.where(
            Lead.company_id == company_id
        )

    if status is not None:
        statement = statement.where(
            Lead.status == status
        )

    if priority is not None:
        statement = statement.where(
            Lead.priority == priority
        )

    statement = (
        statement
        .order_by(
            Lead.discovered_at.desc()
        )
        .offset(offset)
        .limit(limit)
    )

    return list(
        db.scalars(statement).all()
    )


# ============================================================
# Lead Status Transition
# ============================================================

def transition_lead(
    db: Session,
    *,
    lead_id: UUID,
    new_status: str,
    reason: str | None = None,
    note: str | None = None,
    closed_by: str | None = None,
    commit: bool = True,
) -> Lead:

    lead = db.get(
        Lead,
        lead_id,
    )

    if lead is None:
        raise LeadNotFoundError(
            "Lead not found."
        )

    old_status = lead.status

    reason = (
        reason.strip().upper()
        if reason and reason.strip()
        else None
    )

    note = (
        note.strip()
        if note and note.strip()
        else None
    )

    closed_by = (
        closed_by.strip()
        if closed_by and closed_by.strip()
        else None
    )

    # --------------------------------------------------------
    # Closure validation
    # --------------------------------------------------------

    if new_status in CLOSURE_STATUSES:
        if reason is None:
            raise InvalidLeadTransitionError(
                "A closure reason is required."
            )

        expected_status = CLOSURE_REASON_STATUS.get(
            reason
        )

        if expected_status is None:
            raise InvalidLeadTransitionError(
                "Invalid Lead closure reason."
            )

        if expected_status != new_status:
            raise InvalidLeadTransitionError(
                f"Closure reason {reason} must map to "
                f"{expected_status}, not {new_status}."
            )

    elif reason is not None:
        raise InvalidLeadTransitionError(
            "Closure reason may only be supplied when "
            "closing a Lead."
        )

    # Normal status changes remain idempotent.
    # Re-closing an already terminal Lead is rejected.
    if new_status == old_status:
        if new_status in CLOSURE_STATUSES:
            raise InvalidLeadTransitionError(
                "Lead is already closed."
            )

        return lead

    allowed = allowed_transitions(
        old_status
    )

    if new_status not in allowed:
        raise InvalidLeadTransitionError(
            f"Cannot transition lead from "
            f"{old_status} to {new_status}."
        )

    now = datetime.now(
        timezone.utc
    )

    lead.status = new_status
    lead.updated_at = now

    # --------------------------------------------------------
    # Lifecycle timestamps
    # --------------------------------------------------------

    if new_status == "QUALIFIED":
        if lead.qualified_at is None:
            lead.qualified_at = now

    elif new_status == "CONTACTED":
        if lead.contacted_at is None:
            lead.contacted_at = now

    elif new_status == "CONVERTED":
        if lead.converted_at is None:
            lead.converted_at = now

    # --------------------------------------------------------
    # Event logging
    # --------------------------------------------------------

    event_type = "lead_status_changed"

    actor_type = "API"
    actor_id = "marketing-api"

    metadata = {
        "previous_status": old_status,
        "new_status": new_status,
    }

    if new_status == "QUALIFIED":
        event_type = "lead_qualified"

    elif new_status in CLOSURE_STATUSES:
        event_type = "lead_closed"

        metadata.update(
            {
                "reason": reason,
                "note": note,
                "closed_by": closed_by,
            }
        )

        if closed_by:
            actor_type = "DASHBOARD"
            actor_id = closed_by

    event = Event(
        event_type=event_type,
        entity_type="LEAD",
        entity_id=lead.id,
        actor_type=actor_type,
        actor_id=actor_id,
        metadata_json=metadata,
    )

    db.add(event)

    try:
        if commit:
            db.commit()
        else:
            db.flush()
        db.refresh(lead)

        return lead

    except IntegrityError as exc:
        db.rollback()

        raise ValueError(
            "Lead status change conflicts "
            "with an existing active lead."
        ) from exc
