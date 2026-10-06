"""Progress only managed product jobs; outreach approval is never automated."""

from datetime import datetime, timezone
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import select
from app.models.automation import AutomationJob, ProductAutomationPlan
from app.models.companies import Contact
from app.models.leads import Lead, LeadResearch, LeadScore, ProductMatch
from app.models.pipeline import PipelineRun
from app.routers import pipeline
from app.workspace_context import current_principal


def schedule(db, kind, related_id=None, payload=None):
    existing = (
        db.scalar(
            select(AutomationJob).where(
                AutomationJob.kind == kind, AutomationJob.related_id == related_id
            )
        )
        if related_id
        else None
    )
    if existing:
        return existing
    job = AutomationJob(kind=kind, related_id=related_id, payload=payload or {})
    db.add(job)
    db.flush()
    return job


def attach_stage(db, lead, stage, **options):
    existing = db.scalar(
        select(PipelineRun).where(
            PipelineRun.lead_id == lead.id,
            PipelineRun.stage == stage,
            PipelineRun.status.in_(("PENDING", "RUNNING")),
        )
    )
    if existing:
        return schedule(db, stage, existing.id)
    run = pipeline.enqueue(
        db, lead, pipeline.QueueStage(stage=stage, **options), current_principal.get()
    )
    return schedule(db, stage, run.id)


def after_research(db, job):
    report = db.get(LeadResearch, job.related_id)
    if not report or report.research_status not in ("COMPLETED", "PARTIAL"):
        raise HTTPException(409, "Research did not produce a usable report")
    lead = pipeline.lead_for(db, report.lead_id)
    if report.company_facts.get("company_identity_verified") is not True:
        job.status = "NEEDS_REVIEW"
        job.failure_reason = "COMPANY_IDENTITY_REVIEW_REQUIRED"
        return False
    # Use supported public business identities, never conflicting profile candidates.
    people = report.company_facts.get("people", [])
    options = sorted(
        enumerate(people[:5] if isinstance(people, list) else []),
        key=lambda entry: (
            entry[1].get("confidence", 0)
            if isinstance(entry[1], dict) and type(entry[1].get("confidence")) is int
            else 0
        ),
        reverse=True,
    )
    chosen = False
    for index, person in options:
        if (
            not isinstance(person, dict)
            or type(person.get("confidence")) is not int
            or person["confidence"] < 75
        ):
            continue
        if not isinstance(person, dict) or not (
            person.get("business_email")
            or pipeline.profile_url(person.get("linkedin_url"))
        ):
            continue
        try:
            pipeline.review_contact(
                lead.id,
                pipeline.ContactReview(
                    research_id=report.id, person_index=index, confirmed=True
                ),
                db,
            )
            chosen = True
            break
        except HTTPException as exc:
            if exc.status_code not in (404, 409, 422):
                raise
            db.rollback()
    if not chosen and lead.primary_contact_id and pipeline.reviewed(db, lead):
        contact = db.get(Contact, lead.primary_contact_id)
        if (
            contact
            and contact.status == "ACTIVE"
            and contact.full_name
            and (contact.email or pipeline.profile_url(contact.linkedin_url))
        ):
            pipeline.review_contact(
                lead.id,
                pipeline.ContactReview(contact_id=contact.id, confirmed=True),
                db,
            )
            chosen = True
    if not chosen:
        job.status = "NEEDS_REVIEW"
        job.failure_reason = "SUPPORTED_CONTACT_REQUIRED"
        return False
    job.failure_reason = None
    attach_stage(db, lead, "SCORING")
    return True


def after_stage(db, job):
    run = db.get(PipelineRun, job.related_id)
    if not run or run.status != "COMPLETED":
        raise HTTPException(409, "Stage did not complete")
    lead = pipeline.lead_for(db, run.lead_id)
    if job.kind == "SCORING":
        score = db.scalar(
            select(LeadScore).where(
                LeadScore.lead_id == lead.id, LeadScore.is_current.is_(True)
            )
        )
        if not score or str(score.id) != run.result.get("score_id"):
            job.result = {**job.result, "outcome": "SCORING_CONTEXT_CHANGED"}
            return
        supported = any(
            c.get("criterion") == "icp_fit" and c.get("points", 0) > 0
            for c in score.score_breakdown.get("components", [])
        )
        if score.total_score < 60 or not supported:
            job.result = {**job.result, "outcome": "BELOW_QUALIFICATION_THRESHOLD"}
            return
        # The administrator authorized this rule on product activation; no human actor is impersonated.
        result = pipeline.qualify(
            lead.id,
            pipeline.Qualification(
                note="Automatically qualified under the activated product policy: score at least 60 and supported ICP fit."
            ),
            db,
        )
        schedule(db, "MATCHING", result["id"])
    elif job.kind == "MATCHING":
        matches = sorted(
            run.result.get("matches", []),
            key=lambda m: m.get("fit_score", 0),
            reverse=True,
        )
        match = None
        for saved in matches:
            candidate = db.get(ProductMatch, UUID(saved["id"]))
            if (
                candidate
                and candidate.lead_id == lead.id
                and candidate.fit_score >= 60
                and candidate.fit_score == saved.get("fit_score")
            ):
                match = candidate
                break
        if not match:
            job.result = {**job.result, "outcome": "NO_SUPPORTED_PRODUCT_MATCH"}
            return
        contact = db.get(Contact, lead.primary_contact_id)
        attach_stage(
            db,
            lead,
            "DRAFTING",
            product_id=match.product_id,
            channel="EMAIL" if contact.email else "LINKEDIN",
        )
    elif job.kind == "DRAFTING":
        job.result = {**job.result, "outcome": "AWAITING_HUMAN_APPROVAL", **run.result}


def prepare_claim(db, job, actor):
    if job.kind == "RESEARCH":
        from app.services.research_service import start_research

        report = db.get(LeadResearch, job.related_id)
        if not report or report.research_status != "PENDING":
            raise HTTPException(409, "Research is not pending")
        lead = db.get(Lead, report.lead_id)
        if not lead or lead.status not in (
            "DISCOVERED",
            "RESEARCHING",
            "QUALIFIED",
            "READY_FOR_OUTREACH",
        ):
            raise HTTPException(409, "Lead is no longer open for research")
        start_research(db, research_id=report.id)
        return {"research_id": str(report.id), "lead_id": str(lead.id)}
    if job.kind in ("SCORING", "MATCHING", "DRAFTING"):
        run = db.get(PipelineRun, job.related_id)
        if not run or run.status != "PENDING":
            raise HTTPException(409, "Stage is not pending")
        pipeline.lead_for(db, run.lead_id)
        run.status = "RUNNING"
        run.claimed_by = actor
        run.started_at = datetime.now(timezone.utc)
        db.flush()
        return pipeline.run_read(run)
    return {}


def fail_native(db, job, reason):
    """Release native queues as well, so a failed lease can be retried explicitly."""
    now = datetime.now(timezone.utc)
    if job.kind == "RESEARCH":
        report = db.get(LeadResearch, job.related_id)
        if report and report.research_status in ("PENDING", "RUNNING"):
            report.research_status = "FAILED"
            report.completed_at = now
            report.raw_output = {"failure_reason": reason}
    elif job.kind in ("SCORING", "MATCHING", "DRAFTING"):
        run = db.get(PipelineRun, job.related_id)
        if run and run.status in ("PENDING", "RUNNING"):
            run.status = "FAILED"
            run.failure_reason = reason
            run.finished_at = now


def managed(db):
    # A paused managed product must not fall back to a legacy worker.
    return db.scalar(select(ProductAutomationPlan.id)) is not None
