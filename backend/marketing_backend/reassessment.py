"""Resolve a targeted discovery attempt without replacing prior review evidence."""
from uuid import UUID
from sqlalchemy import select
from .models import DiscoveryMemory


def resolve_reassessment(db, job, reason):
    value = job.payload.get("retry_candidate_id") if job.kind == "DISCOVERY" else None
    if not value:
        return
    try:
        candidate_id = UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return
    row = db.scalar(select(DiscoveryMemory).where(
        DiscoveryMemory.id == candidate_id,
        DiscoveryMemory.workspace_id == job.workspace_id,
        DiscoveryMemory.product_line_id == job.product_line_id,
    ).with_for_update())
    if not row or row.outcome != "RETRY_PENDING" or row.candidate.get("_retry_job_id") != str(job.id):
        return
    candidate = dict(row.candidate)
    candidate.pop("_retry_job_id", None)
    if candidate.get("reason") == "SOURCE_INELIGIBLE" and reason != "SOURCE_INELIGIBLE":
        candidate["last_reassessment_reason"] = reason
    else:
        candidate["reason"] = reason
    candidate["verification_state"] = "UNCERTAIN"
    row.candidate = candidate
    row.outcome = "OWNERSHIP_UNCERTAIN"
    row.retry_after = None
