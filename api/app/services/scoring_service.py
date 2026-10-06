from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.leads import (
    Lead,
    LeadResearch,
    LeadScore,
)
from app.models.marketing import Event
from app.schemas.scoring import ScoreCreate


# ============================================================
# Exceptions
# ============================================================

class ScoringLeadNotFoundError(Exception):
    pass


class ScoringNotAllowedError(Exception):
    pass


class CurrentScoreNotFoundError(Exception):
    pass


class ScoreNotFoundError(Exception):
    pass


class ScoringConflictError(Exception):
    pass


# ============================================================
# Scoring Rules
# ============================================================

USABLE_RESEARCH_STATUSES = {
    "COMPLETED",
    "PARTIAL",
}


TERMINAL_LEAD_STATUSES = {
    "CONVERTED",
    "DISQUALIFIED",
    "LOST",
}


# ============================================================
# Research Eligibility
# ============================================================

def get_latest_usable_research(
    db: Session,
    *,
    lead_id: UUID,
) -> LeadResearch | None:

    statement = (
        select(LeadResearch)
        .where(
            LeadResearch.lead_id == lead_id,
            LeadResearch.research_status.in_(
                USABLE_RESEARCH_STATUSES
            ),
        )
        .order_by(
            LeadResearch.completed_at
            .desc()
            .nullslast(),
            LeadResearch.created_at.desc(),
        )
        .limit(1)
    )

    return db.scalars(
        statement
    ).first()


# ============================================================
# Create Score
# ============================================================

def create_score(
    db: Session,
    *,
    lead_id: UUID,
    data: ScoreCreate,
    commit: bool = True,
) -> LeadScore:

    # --------------------------------------------------------
    # 1. Lock lead
    #
    # Serializes concurrent scoring requests for the same
    # lead and protects current-score replacement.
    # --------------------------------------------------------

    statement = (
        select(Lead)
        .where(
            Lead.id == lead_id
        )
        .with_for_update()
    )

    lead = db.scalars(
        statement
    ).first()

    if lead is None:
        raise ScoringLeadNotFoundError(
            "Lead not found."
        )

    # --------------------------------------------------------
    # 2. Reject terminal leads
    #
    # Rescoring terminal leads is not yet defined by MVP1
    # policy and must not be silently enabled.
    # --------------------------------------------------------

    if lead.status in TERMINAL_LEAD_STATUSES:
        raise ScoringNotAllowedError(
            f"Lead in {lead.status} status "
            "cannot be scored."
        )

    # --------------------------------------------------------
    # 3. Require usable research
    # --------------------------------------------------------

    research = get_latest_usable_research(
        db,
        lead_id=lead.id,
    )

    if research is None:
        raise ScoringNotAllowedError(
            "Lead has no COMPLETED or PARTIAL "
            "research run available for scoring."
        )

    # --------------------------------------------------------
    # 4. Find current score
    # --------------------------------------------------------

    current_statement = (
        select(LeadScore)
        .where(
            LeadScore.lead_id == lead.id,
            LeadScore.is_current.is_(True),
        )
    )

    current_score = db.scalars(
        current_statement
    ).first()

    previous_score = None

    if current_score is not None:
        previous_score = (
            current_score.total_score
        )

        current_score.is_current = False

    # --------------------------------------------------------
    # 5. Create new historical score row
    # --------------------------------------------------------

    score = LeadScore(
        lead_id=lead.id,
        total_score=data.total_score,
        score_breakdown=(
            data.score_breakdown
        ),
        scoring_version=(
            data.scoring_version
        ),
        rationale=data.rationale,
        is_current=True,
    )

    db.add(score)

    # --------------------------------------------------------
    # 6. Synchronize lead.current_score
    # --------------------------------------------------------

    now = datetime.now(
        timezone.utc
    )

    lead.current_score = (
        data.total_score
    )

    lead.updated_at = now

    try:
        # Generate score UUID before event logging.
        #
        # This also allows the unique current-score DB index
        # to act as a second concurrency protection layer.
        db.flush()

        # ----------------------------------------------------
        # 7. Log lead_scored
        # ----------------------------------------------------

        event = Event(
            event_type="lead_scored",
            entity_type="LEAD",
            entity_id=lead.id,
            actor_type="API",
            actor_id="marketing-api",
            metadata_json={
                "lead_id": str(
                    lead.id
                ),
                "score_id": str(
                    score.id
                ),
                "total_score": (
                    score.total_score
                ),
                "scoring_version": (
                    score.scoring_version
                ),
                "previous_score": (
                    previous_score
                ),
            },
        )

        db.add(event)

        # ----------------------------------------------------
        # Qualification intentionally deferred.
        #
        # No QUALIFIED / DISQUALIFIED transition occurs here
        # until an approved scoring threshold/policy exists.
        # ----------------------------------------------------

        if commit:
            db.commit()
        else:
            db.flush()
        db.refresh(score)

        return score

    except IntegrityError as exc:
        db.rollback()

        raise ScoringConflictError(
            "Score creation conflicts with "
            "the current scoring state."
        ) from exc


# ============================================================
# Score History
# ============================================================

def list_scores_for_lead(
    db: Session,
    *,
    lead_id: UUID,
) -> list[LeadScore]:

    lead = db.get(
        Lead,
        lead_id,
    )

    if lead is None:
        raise ScoringLeadNotFoundError(
            "Lead not found."
        )

    statement = (
        select(LeadScore)
        .where(
            LeadScore.lead_id == lead_id
        )
        .order_by(
            LeadScore.created_at.desc()
        )
    )

    return list(
        db.scalars(statement).all()
    )


# ============================================================
# Current Score
# ============================================================

def get_current_score(
    db: Session,
    *,
    lead_id: UUID,
) -> LeadScore:

    lead = db.get(
        Lead,
        lead_id,
    )

    if lead is None:
        raise ScoringLeadNotFoundError(
            "Lead not found."
        )

    statement = (
        select(LeadScore)
        .where(
            LeadScore.lead_id == lead_id,
            LeadScore.is_current.is_(True),
        )
    )

    score = db.scalars(
        statement
    ).first()

    if score is None:
        raise CurrentScoreNotFoundError(
            "Current score not found."
        )

    return score


# ============================================================
# Score Detail
# ============================================================

def get_score(
    db: Session,
    *,
    score_id: UUID,
) -> LeadScore:

    score = db.get(
        LeadScore,
        score_id,
    )

    if score is None:
        raise ScoreNotFoundError(
            "Score not found."
        )

    return score
