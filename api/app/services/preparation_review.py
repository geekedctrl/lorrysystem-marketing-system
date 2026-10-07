"""Keep generated outreach tied to the preparation that produced it."""

from sqlalchemy import select
from app.models.pipeline import PipelineRun
from app.models.leads import Lead, LeadResearch, LeadScore
from app.models.companies import Contact


def review_context(db, action):
    run = db.scalar(
        select(PipelineRun)
        .where(
            PipelineRun.lead_id == action.lead_id,
            PipelineRun.stage == "DRAFTING",
            PipelineRun.result["action_id"].astext == str(action.id),
        )
        .order_by(PipelineRun.created_at.desc())
        .limit(1)
    )
    if not run:
        return {"current": True, "reason": None}
    lead = db.get(Lead, action.lead_id)
    research = db.scalar(
        select(LeadResearch)
        .where(LeadResearch.lead_id == action.lead_id)
        .order_by(LeadResearch.created_at.desc(), LeadResearch.id.desc())
        .limit(1)
    )
    score = db.scalar(
        select(LeadScore).where(
            LeadScore.lead_id == action.lead_id, LeadScore.is_current.is_(True)
        )
    )
    contact = db.get(Contact, action.contact_id) if action.contact_id else None
    valid = bool(
        lead
        and research
        and score
        and contact
        and contact.status == "ACTIVE"
        and research.id == run.research_id
        and contact.id == run.contact_id
        and lead.primary_contact_id == contact.id
        and str(score.id) == run.input_snapshot.get("score_id")
    )
    if valid:
        from app.routers.pipeline import fingerprint
        from fastapi import HTTPException

        try:
            valid = fingerprint(db, lead, contact) == run.input_snapshot.get(
                "context_hash"
            )
        except HTTPException:
            valid = False
    return {
        "current": valid,
        "reason": (
            None
            if valid
            else "Preparation changed after this draft was created. Review the current research and score, then prepare a fresh draft before approving or sending."
        ),
    }
