"""Workspace-scoped presentation of current automation and retained history."""

from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.models.automation import AutomationJob
from app.models.leads import LeadResearch
from app.models.pipeline import PipelineRun


def current_job_ids(db, jobs):
    related = [job.related_id for job in jobs if job.related_id]
    lead_ids = set(
        db.scalars(select(LeadResearch.lead_id).where(LeadResearch.id.in_(related)))
    )
    lead_ids.update(
        db.scalars(select(PipelineRun.lead_id).where(PipelineRun.id.in_(related)))
    )
    research = list(
        db.scalars(
            select(LeadResearch)
            .where(LeadResearch.lead_id.in_(lead_ids))
            .distinct(LeadResearch.lead_id)
            .order_by(
                LeadResearch.lead_id,
                LeadResearch.created_at.desc(),
                LeadResearch.id.desc(),
            )
        )
    )
    latest_ids = [report.id for report in research]
    runs = list(
        db.scalars(
            select(PipelineRun)
            .where(PipelineRun.research_id.in_(latest_ids))
            .distinct(PipelineRun.lead_id, PipelineRun.stage)
            .order_by(
                PipelineRun.lead_id,
                PipelineRun.stage,
                PipelineRun.created_at.desc(),
                PipelineRun.id.desc(),
            )
        )
    )
    latest_research = {}
    for report in research:
        latest_research.setdefault(report.lead_id, report.id)
    latest_runs = {}
    for run in runs:
        if run.research_id == latest_research.get(run.lead_id):
            latest_runs.setdefault((run.lead_id, run.stage), run.id)
    valid = set(latest_research.values()) | set(latest_runs.values())
    # Setup/discovery have no native record; only their newest workspace job is current.
    latest_control = {}
    for job in db.scalars(
        select(AutomationJob)
        .where(AutomationJob.kind.in_(("SETUP", "DISCOVERY")))
        .distinct(AutomationJob.kind)
        .order_by(
            AutomationJob.kind, AutomationJob.created_at.desc(), AutomationJob.id.desc()
        )
    ):
        latest_control.setdefault(job.kind, job.id)
    return {
        job.id
        for job in jobs
        if job.related_id in valid or latest_control.get(job.kind) == job.id
    }


def describe_job(job, current, enabled, now=None):
    now = now or datetime.now(timezone.utc)
    waiting = job.status == "PENDING" and job.created_at < now - timedelta(minutes=5)
    running = (
        job.status == "RUNNING"
        and job.started_at
        and job.started_at < now - timedelta(minutes=15)
    )
    return {
        key: getattr(job, key)
        for key in (
            "id",
            "kind",
            "status",
            "related_id",
            "failure_reason",
            "result",
            "created_at",
            "started_at",
            "finished_at",
        )
    } | {
        "current": current,
        "needs_attention": current and job.status in ("FAILED", "NEEDS_REVIEW"),
        "stalled": bool(current and enabled and (waiting or running)),
        "failure_help": failure_help(job.failure_reason),
    }


def failure_help(reason):
    if reason == "SUPPORTED_CONTACT_REQUIRED":
        return "Research is saved. Choose a company-linked person with a supported individual LinkedIn profile or published business email, then continue. A general mailbox does not identify a person."
    if reason == "COMPANY_IDENTITY_REVIEW_REQUIRED":
        return "Confirm the official company website and supporting evidence, then request fresh research."
    if reason and (
        "QUOTE" in reason
        or "CITATION" in reason
        or reason
        in (
            "INVALID_SCORE_EVIDENCE",
            "INVALID_PRODUCT_EVIDENCE",
            "INVALID_DRAFT_EVIDENCE",
        )
    ):
        return "The generated result did not meet source-evidence requirements. Saved research is retained. Retry once after checking source coverage; no draft was approved or sent."
    if reason in ("SEARCH_FAILED", "RATE_LIMITED", "MODEL_REQUEST_FAILED"):
        return "The search or model provider could not complete the request. Check connection status before retrying."
    if reason in ("LEASE_EXPIRED", "WORKER_TIMEOUT", "SHARED_WORKFLOW_FAILED"):
        return "The worker did not finish this attempt. Check the worker connection and job activity, then retry explicitly."
    return (
        "Review the saved research, product catalog and job activity before retrying."
        if reason
        else None
    )
