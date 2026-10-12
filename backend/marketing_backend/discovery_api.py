"""Workspace-owned candidate review. Worker discovery cannot accept a lead."""

from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, func
from .auth import user, scope
from .db import session
from .models import DiscoveryMemory, Lead, Workspace, PreparationRun, now
from .pipeline import context, fingerprint, domain, start
from .native_api import workspace_lock, enqueue_workspace
from .public_fetch import checked_url, FetchError
from .research import ProviderFailure
from . import contracts as out

router = APIRouter(prefix="/workspaces/{wid}/candidates")
REVIEW_ROLES = ["ADMIN", "OPERATOR", "REVIEWER"]


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    note: str = Field(default="", max_length=1000)


def candidate_for(db, wid, cid):
    row = db.scalar(
        select(DiscoveryMemory)
        .where(DiscoveryMemory.workspace_id == wid, DiscoveryMemory.id == cid)
        .with_for_update()
    )
    if not row:
        raise HTTPException(404, "Candidate not found")
    return row


def public(row, current_hash):
    fields = {
        k: row.candidate.get(k)
        for k in (
            "company_name",
            "website",
            "industry",
            "prospect_type",
            "confidence",
            "icp_code",
            "reasoning",
            "source_url",
            "evidence_quote",
        )
    }
    return {
        **fields,
        "id": row.id,
        "domain": row.domain,
        "status": row.outcome,
        "unknowns": row.candidate.get("unknowns", []),
        "failure_reason": row.candidate.get("reason"),
        "source_job_id": row.source_job_id,
        "accepted_lead_id": row.accepted_lead_id,
        "reviewed_at": row.reviewed_at,
        "review_note": row.review_note,
        "retry_after": row.retry_after,
        "created_at": row.created_at,
        "stale": row.context_hash is not None and row.context_hash != current_hash,
    }


@router.get("", response_model=out.DiscoveryPage)
def candidates(
    wid: UUID,
    actor=Depends(user),
    db=Depends(session),
    status: str | None = Query(default=None, max_length=24),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100000),
):
    scope(wid, actor, db)
    query = select(DiscoveryMemory).where(DiscoveryMemory.workspace_id == wid)
    if status:
        query = query.where(DiscoveryMemory.outcome == status)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(
        query.order_by(DiscoveryMemory.created_at.desc(), DiscoveryMemory.id.desc())
        .offset(offset)
        .limit(limit)
    )
    current_hash = fingerprint(context(db, wid))
    return {
        "items": [public(row, current_hash) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{cid}", response_model=out.DiscoveryCandidate)
def detail(wid: UUID, cid: UUID, actor=Depends(user), db=Depends(session)):
    scope(wid, actor, db)
    return public(candidate_for(db, wid, cid), fingerprint(context(db, wid)))


@router.post("/{cid}/accept", response_model=out.CandidateAccepted)
def accept(
    wid: UUID, cid: UUID, data: Review, actor=Depends(user), db=Depends(session)
):
    scope(wid, actor, db, REVIEW_ROLES)
    workspace = workspace_lock(db, wid)
    row = candidate_for(db, wid, cid)
    if row.outcome == "ACCEPTED" and row.accepted_lead_id:
        run = db.scalar(
            select(PreparationRun)
            .where(
                PreparationRun.workspace_id == wid,
                PreparationRun.lead_id == row.accepted_lead_id,
            )
            .order_by(PreparationRun.created_at)
            .limit(1)
        )
        return {
            "candidate_id": row.id,
            "lead_id": row.accepted_lead_id,
            "run_id": run.id,
            "status": "ACCEPTED",
        }
    if row.outcome != "READY_FOR_REVIEW":
        raise HTTPException(409, "Only a candidate awaiting review can be accepted")
    if not workspace.automation_enabled:
        raise HTTPException(409, "Resume product automation before acceptance")
    if row.context_hash != fingerprint(context(db, wid)):
        raise HTTPException(
            409, "Targeting changed. Reassess this candidate before acceptance"
        )
    value = row.candidate
    try:
        checked_url(value["website"])
        if domain(value["website"]) != row.domain:
            raise FetchError("CANDIDATE_DOMAIN_CHANGED")
    except (FetchError, KeyError):
        raise HTTPException(409, "Candidate website is invalid") from None
    if any(
        domain(lead.website) == row.domain
        for lead in db.scalars(select(Lead).where(Lead.workspace_id == wid))
    ):
        raise HTTPException(409, "This company already has a lead")
    lead = Lead(
        workspace_id=wid, company_name=value["company_name"], website=value["website"]
    )
    db.add(lead)
    db.flush()
    try:
        run = start(db, lead, f"candidate:{cid}:RESEARCH", value["icp_code"])
    except ProviderFailure:
        raise HTTPException(409, "Active catalog and targeting are required") from None
    row.outcome = "ACCEPTED"
    row.accepted_lead_id = lead.id
    row.reviewed_by, row.reviewed_at, row.review_note = actor.id, now(), data.note
    db.commit()
    return {
        "candidate_id": row.id,
        "lead_id": lead.id,
        "run_id": run.id,
        "status": "ACCEPTED",
    }


@router.post("/{cid}/reject", response_model=out.CandidateReviewed)
def reject(
    wid: UUID, cid: UUID, data: Review, actor=Depends(user), db=Depends(session)
):
    scope(wid, actor, db, REVIEW_ROLES)
    workspace_lock(db, wid)
    row = candidate_for(db, wid, cid)
    if row.outcome == "REJECTED":
        return {"candidate_id": row.id, "status": "REJECTED"}
    if row.outcome != "READY_FOR_REVIEW":
        raise HTTPException(409, "Only a candidate awaiting review can be rejected")
    if len(data.note) < 5:
        raise HTTPException(422, "Provide a short reason for rejection")
    row.outcome = "REJECTED"
    row.reviewed_by, row.reviewed_at, row.review_note = actor.id, now(), data.note
    db.commit()
    return {"candidate_id": row.id, "status": "REJECTED"}


@router.post("/{cid}/retry", response_model=out.CandidateReviewed)
def retry(wid: UUID, cid: UUID, actor=Depends(user), db=Depends(session)):
    scope(wid, actor, db, REVIEW_ROLES)
    workspace = workspace_lock(db, wid)
    row = candidate_for(db, wid, cid)
    if row.outcome in {"ACCEPTED", "REJECTED", "KNOWN"}:
        raise HTTPException(
            409, "Reviewed companies cannot be retried through discovery"
        )
    if not workspace.automation_enabled or not workspace.automation.get(
        "discovery_query"
    ):
        raise HTTPException(409, "Complete setup and resume discovery first")
    row.outcome, row.retry_after = "RETRY_PENDING", None
    job = enqueue_workspace(db, workspace, "DISCOVERY", f"candidate-retry:{uuid4()}")
    job.payload = {
        **job.payload,
        "retry_domain": row.domain,
        "retry_url": row.candidate.get("source_url") or "https://" + row.domain + "/",
    }
    # Retain prior evidence and review history until an actual assessment replaces it.
    db.commit()
    return {"candidate_id": row.id, "status": "RETRY_PENDING", "job_id": job.id}
