from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.catalog import ICPProfile
from app.models.companies import Company, Contact
from app.models.discovery import (
    LeadCandidate,
    LeadCandidateSource,
)
from app.models.leads import (
    Lead,
    LeadResearch,
    ResearchSource,
)
from app.models.marketing import Event
from app.schemas.research import (
    ResearchComplete,
    ResearchFail,
    ResearchPartial,
    ResearchSourceCreate,
)
from app.services.lead_service import (
    ACTIVE_STATUSES,
    LeadNotFoundError,
)


# ============================================================
# Exceptions
# ============================================================

class ResearchNotFoundError(Exception):
    pass


class InvalidResearchTransitionError(Exception):
    pass


class InvalidLeadResearchStateError(Exception):
    pass


class ResearchContextIntegrityError(Exception):
    pass


# ============================================================
# Research Lifecycle
# ============================================================

RESEARCH_TRANSITIONS = {
    "PENDING": {
        "RUNNING",
    },
    "RUNNING": {
        "COMPLETED",
        "PARTIAL",
        "FAILED",
    },
    "COMPLETED": set(),
    "PARTIAL": set(),
    "FAILED": set(),
}


def validate_research_transition(
    current_status: str,
    new_status: str,
) -> None:

    allowed = RESEARCH_TRANSITIONS.get(
        current_status,
        set(),
    )

    if new_status not in allowed:
        raise InvalidResearchTransitionError(
            f"Cannot transition research from "
            f"{current_status} to {new_status}."
        )


# ============================================================
# Create Research Run
# ============================================================

def create_research_run(
    db: Session,
    *,
    lead_id: UUID,
) -> LeadResearch:

    lead = db.get(
        Lead,
        lead_id,
    )

    if lead is None:
        raise LeadNotFoundError(
            "Lead not found."
        )

    if lead.status not in ACTIVE_STATUSES:
        raise InvalidLeadResearchStateError(
            f"Research cannot be created for "
            f"a lead in {lead.status} status."
        )

    # --------------------------------------------------------
    # Important lifecycle rule:
    #
    # Creating a Research run only queues work.
    #
    # Lead:
    #   stays in its current active status
    #
    # Research:
    #   starts as PENDING
    #
    # DISCOVERED → RESEARCHING happens only when the
    # Research Worker actually starts/claims the job.
    # --------------------------------------------------------

    research = LeadResearch(
        lead_id=lead.id,
    )

    db.add(research)

    try:
        db.flush()

        db.add(
            Event(
                event_type="research_requested",
                entity_type="RESEARCH",
                entity_id=research.id,
                actor_type="API",
                actor_id="marketing-api",
                metadata_json={
                    "lead_id": str(lead.id),
                    "research_status": "PENDING",
                    "lead_status_at_request": (
                        lead.status
                    ),
                    "lead_moved_to_researching": False,
                },
            )
        )

        db.commit()
        db.refresh(research)

        return research

    except IntegrityError as exc:
        db.rollback()

        raise ValueError(
            "Research run conflicts with "
            "database constraints."
        ) from exc


# ============================================================
# List Research Runs
# ============================================================

def list_research_runs(
    db: Session,
    *,
    research_status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[LeadResearch]:

    statement = select(
        LeadResearch
    )

    if research_status is not None:
        statement = statement.where(
            LeadResearch.research_status
            == research_status
        )

    statement = (
        statement
        .order_by(
            LeadResearch.created_at.asc()
        )
        .limit(limit)
        .offset(offset)
    )

    return list(
        db.scalars(statement).all()
    )


# ============================================================
# List Research for Lead
# ============================================================

def list_research_for_lead(
    db: Session,
    *,
    lead_id: UUID,
) -> list[LeadResearch]:

    lead = db.get(
        Lead,
        lead_id,
    )

    if lead is None:
        raise LeadNotFoundError(
            "Lead not found."
        )

    statement = (
        select(LeadResearch)
        .where(
            LeadResearch.lead_id == lead_id
        )
        .order_by(
            LeadResearch.created_at.desc()
        )
    )

    return list(
        db.scalars(statement).all()
    )


# ============================================================
# Get Research
# ============================================================

def get_research(
    db: Session,
    research_id: UUID,
) -> LeadResearch | None:

    return db.get(
        LeadResearch,
        research_id,
    )


def get_research_detail(
    db: Session,
    *,
    research_id: UUID,
) -> tuple[
    LeadResearch,
    list[ResearchSource],
]:

    research = get_research(
        db,
        research_id,
    )

    if research is None:
        raise ResearchNotFoundError(
            "Research run not found."
        )

    statement = (
        select(ResearchSource)
        .where(
            ResearchSource.research_id
            == research.id
        )
        .order_by(
            ResearchSource.created_at.asc()
        )
    )

    sources = list(
        db.scalars(statement).all()
    )

    return research, sources


# ============================================================
# Research Seed Context
# ============================================================

def get_research_context(
    db: Session,
    *,
    research_id: UUID,
) -> dict:

    research = get_research(
        db,
        research_id,
    )

    if research is None:
        raise ResearchNotFoundError(
            "Research run not found."
        )

    lead = db.get(
        Lead,
        research.lead_id,
    )

    if lead is None:
        raise ResearchContextIntegrityError(
            "Research Lead is missing."
        )

    company = db.get(
        Company,
        lead.company_id,
    )

    if company is None:
        raise ResearchContextIntegrityError(
            "Research Company is missing."
        )

    primary_contact = None

    if lead.primary_contact_id is not None:
        primary_contact = db.get(
            Contact,
            lead.primary_contact_id,
        )

        if primary_contact is None:
            raise ResearchContextIntegrityError(
                "Primary Contact is missing."
            )

        if primary_contact.company_id != company.id:
            raise ResearchContextIntegrityError(
                "Primary Contact does not belong "
                "to the Lead Company."
            )

    icp_profile = db.get(
        ICPProfile,
        lead.icp_profile_id,
    )

    if icp_profile is None:
        raise ResearchContextIntegrityError(
            "Lead ICP Profile is missing."
        )

    candidate_statement = (
        select(LeadCandidate)
        .where(
            LeadCandidate.accepted_lead_id
            == lead.id,
            LeadCandidate.status
            == "ACCEPTED",
        )
        .order_by(
            LeadCandidate.reviewed_at.desc(),
            LeadCandidate.created_at.desc(),
        )
        .limit(1)
    )

    accepted_candidate = db.scalar(
        candidate_statement
    )

    candidate_sources = []

    if accepted_candidate is not None:
        source_statement = (
            select(LeadCandidateSource)
            .where(
                LeadCandidateSource.candidate_id
                == accepted_candidate.id
            )
            .order_by(
                LeadCandidateSource.discovered_at.asc(),
                LeadCandidateSource.created_at.asc(),
            )
        )

        candidate_sources = list(
            db.scalars(
                source_statement
            ).all()
        )

    return {
        "research": research,
        "lead": lead,
        "company": company,
        "primary_contact": primary_contact,
        "icp_profile": icp_profile,
        "accepted_candidate": accepted_candidate,
        "candidate_sources": candidate_sources,
    }


# ============================================================
# Claim Next Pending Research
# ============================================================

def claim_next_research(
    db: Session,
) -> LeadResearch | None:

    # --------------------------------------------------------
    # Atomically select the oldest available PENDING job.
    #
    # FOR UPDATE SKIP LOCKED prevents multiple Research
    # Workers from claiming the same job concurrently.
    # --------------------------------------------------------

    statement = (
        select(LeadResearch)
        .where(
            LeadResearch.research_status
            == "PENDING"
        )
        .order_by(
            LeadResearch.created_at.asc(),
            LeadResearch.id.asc(),
        )
        .with_for_update(
            skip_locked=True
        )
        .limit(1)
    )

    research = db.scalar(statement)

    if research is None:
        # Release the transaction opened by the SELECT.
        db.rollback()
        return None

    # --------------------------------------------------------
    # Lock the associated Lead as part of the same
    # transaction so Lead lifecycle state cannot race with
    # the Research claim.
    # --------------------------------------------------------

    lead_statement = (
        select(Lead)
        .where(
            Lead.id == research.lead_id
        )
        .with_for_update()
    )

    lead = db.scalar(
        lead_statement
    )

    if lead is None:
        db.rollback()

        raise LeadNotFoundError(
            "Lead not found."
        )

    if lead.status not in ACTIVE_STATUSES:
        db.rollback()

        raise InvalidLeadResearchStateError(
            f"Research cannot start for "
            f"a lead in {lead.status} status."
        )

    now = datetime.now(
        timezone.utc
    )

    previous_lead_status = lead.status
    lead_changed = False

    research.research_status = "RUNNING"
    research.started_at = now

    # --------------------------------------------------------
    # Only DISCOVERED → RESEARCHING.
    #
    # Never move a Lead backwards if it is already at a later
    # active lifecycle stage.
    # --------------------------------------------------------

    if lead.status == "DISCOVERED":
        lead.status = "RESEARCHING"
        lead.updated_at = now
        lead_changed = True

        db.add(
            Event(
                event_type="lead_status_changed",
                entity_type="LEAD",
                entity_id=lead.id,
                actor_type="API",
                actor_id="marketing-api",
                metadata_json={
                    "previous_status": (
                        previous_lead_status
                    ),
                    "new_status": "RESEARCHING",
                    "reason": "research_claimed",
                    "research_id": str(
                        research.id
                    ),
                },
            )
        )

    db.add(
        Event(
            event_type="research_started",
            entity_type="RESEARCH",
            entity_id=research.id,
            actor_type="API",
            actor_id="marketing-api",
            metadata_json={
                "lead_id": str(
                    research.lead_id
                ),
                "claim_method": (
                    "FOR_UPDATE_SKIP_LOCKED"
                ),
                "lead_previous_status": (
                    previous_lead_status
                ),
                "lead_status": lead.status,
                "lead_moved_to_researching": (
                    lead_changed
                ),
            },
        )
    )

    db.commit()
    db.refresh(research)

    return research


# ============================================================
# Start Research
# ============================================================

def start_research(
    db: Session,
    *,
    research_id: UUID,
) -> LeadResearch:

    research = get_research(
        db,
        research_id,
    )

    if research is None:
        raise ResearchNotFoundError(
            "Research run not found."
        )

    validate_research_transition(
        research.research_status,
        "RUNNING",
    )

    lead = db.get(
        Lead,
        research.lead_id,
    )

    if lead is None:
        raise LeadNotFoundError(
            "Lead not found."
        )

    if lead.status not in ACTIVE_STATUSES:
        raise InvalidLeadResearchStateError(
            f"Research cannot start for "
            f"a lead in {lead.status} status."
        )

    now = datetime.now(
        timezone.utc
    )

    research.research_status = "RUNNING"
    research.started_at = now

    # --------------------------------------------------------
    # Research creation does NOT move the Lead.
    #
    # Only an actual Research start does:
    #
    # DISCOVERED → RESEARCHING
    #
    # Existing later active stages are not moved backwards.
    # --------------------------------------------------------

    lead_changed = False
    previous_lead_status = lead.status

    if lead.status == "DISCOVERED":
        lead.status = "RESEARCHING"
        lead.updated_at = now
        lead_changed = True

        db.add(
            Event(
                event_type="lead_status_changed",
                entity_type="LEAD",
                entity_id=lead.id,
                actor_type="API",
                actor_id="marketing-api",
                metadata_json={
                    "previous_status": (
                        previous_lead_status
                    ),
                    "new_status": "RESEARCHING",
                    "reason": "research_started",
                    "research_id": str(
                        research.id
                    ),
                },
            )
        )

    db.add(
        Event(
            event_type="research_started",
            entity_type="RESEARCH",
            entity_id=research.id,
            actor_type="API",
            actor_id="marketing-api",
            metadata_json={
                "lead_id": str(
                    research.lead_id
                ),
                "lead_previous_status": (
                    previous_lead_status
                ),
                "lead_status": lead.status,
                "lead_moved_to_researching": (
                    lead_changed
                ),
            },
        )
    )

    db.commit()
    db.refresh(research)

    return research


# ============================================================
# Add Research Source
# ============================================================

def add_research_source(
    db: Session,
    *,
    research_id: UUID,
    data: ResearchSourceCreate,
) -> ResearchSource:

    research = get_research(
        db,
        research_id,
    )

    if research is None:
        raise ResearchNotFoundError(
            "Research run not found."
        )

    source = ResearchSource(
        research_id=research.id,
        source_type=data.source_type,
        url=str(data.url),
        title=data.title,
        evidence=data.evidence,
        confidence=data.confidence,
        observed_at=data.observed_at,
    )

    db.add(source)
    db.flush()

    db.add(
        Event(
            event_type="research_source_added",
            entity_type="RESEARCH",
            entity_id=research.id,
            actor_type="API",
            actor_id="marketing-api",
            metadata_json={
                "lead_id": str(
                    research.lead_id
                ),
                "source_id": str(
                    source.id
                ),
                "source_type": (
                    data.source_type
                ),
                "url": str(
                    data.url
                ),
            },
        )
    )

    db.commit()
    db.refresh(source)

    return source


# ============================================================
# Source Count
# ============================================================

def count_research_sources(
    db: Session,
    *,
    research_id: UUID,
) -> int:

    statement = (
        select(
            func.count(
                ResearchSource.id
            )
        )
        .where(
            ResearchSource.research_id
            == research_id
        )
    )

    return int(
        db.scalar(statement) or 0
    )


# ============================================================
# Complete Research
# ============================================================

def complete_research(
    db: Session,
    *,
    research_id: UUID,
    data: ResearchComplete,
) -> LeadResearch:

    research = get_research(
        db,
        research_id,
    )

    if research is None:
        raise ResearchNotFoundError(
            "Research run not found."
        )

    validate_research_transition(
        research.research_status,
        "COMPLETED",
    )

    now = datetime.now(
        timezone.utc
    )

    research.summary = data.summary
    research.pain_points = data.pain_points
    research.buying_signals = (
        data.buying_signals
    )
    research.company_facts = (
        data.company_facts
    )
    research.confidence = data.confidence
    research.model_provider = (
        data.model_provider
    )
    research.model_name = data.model_name
    research.raw_output = data.raw_output

    research.research_status = "COMPLETED"
    research.completed_at = now

    # Legacy compatibility field.
    research.researched_at = now

    source_count = count_research_sources(
        db,
        research_id=research.id,
    )

    db.add(
        Event(
            event_type="research_completed",
            entity_type="RESEARCH",
            entity_id=research.id,
            actor_type="API",
            actor_id="marketing-api",
            metadata_json={
                "lead_id": str(
                    research.lead_id
                ),
                "confidence": (
                    research.confidence
                ),
                "source_count": (
                    source_count
                ),
            },
        )
    )

    db.commit()
    db.refresh(research)

    return research


# ============================================================
# Partial Research
# ============================================================

def mark_research_partial(
    db: Session,
    *,
    research_id: UUID,
    data: ResearchPartial,
) -> LeadResearch:

    research = get_research(
        db,
        research_id,
    )

    if research is None:
        raise ResearchNotFoundError(
            "Research run not found."
        )

    validate_research_transition(
        research.research_status,
        "PARTIAL",
    )

    now = datetime.now(
        timezone.utc
    )

    research.summary = data.summary
    research.pain_points = data.pain_points
    research.buying_signals = (
        data.buying_signals
    )
    research.company_facts = (
        data.company_facts
    )
    research.confidence = data.confidence
    research.model_provider = (
        data.model_provider
    )
    research.model_name = data.model_name
    research.raw_output = data.raw_output

    research.research_status = "PARTIAL"
    research.completed_at = now

    # Legacy compatibility field.
    research.researched_at = now

    source_count = count_research_sources(
        db,
        research_id=research.id,
    )

    db.add(
        Event(
            event_type="research_partial",
            entity_type="RESEARCH",
            entity_id=research.id,
            actor_type="API",
            actor_id="marketing-api",
            metadata_json={
                "lead_id": str(
                    research.lead_id
                ),
                "confidence": (
                    research.confidence
                ),
                "source_count": (
                    source_count
                ),
            },
        )
    )

    db.commit()
    db.refresh(research)

    return research


# ============================================================
# Fail Research
# ============================================================

def fail_research(
    db: Session,
    *,
    research_id: UUID,
    data: ResearchFail,
) -> LeadResearch:

    research = get_research(
        db,
        research_id,
    )

    if research is None:
        raise ResearchNotFoundError(
            "Research run not found."
        )

    validate_research_transition(
        research.research_status,
        "FAILED",
    )

    now = datetime.now(
        timezone.utc
    )

    research.research_status = "FAILED"
    research.completed_at = now

    db.add(
        Event(
            event_type="research_failed",
            entity_type="RESEARCH",
            entity_id=research.id,
            actor_type="API",
            actor_id="marketing-api",
            metadata_json={
                "lead_id": str(
                    research.lead_id
                ),
                "reason": data.reason,
            },
        )
    )

    db.commit()
    db.refresh(research)

    return research
