"""Product commands and review APIs; no sending endpoint."""

from datetime import timedelta
from uuid import UUID
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from .db import session
from .auth import user, scope
from .models import (
    Workspace,
    Catalog,
    Job,
    Lead,
    PreparationRun,
    Approval,
    ProviderUsage,
    now,
)
from .pipeline import context, fingerprint, start
from .research import ProviderFailure
from .stages import Person, cite, normalize

router = APIRouter(prefix="/workspaces/{wid}")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Request(Strict):
    idempotency_key: str = Field(min_length=8, max_length=120)


class Activation(Request):
    product_description: str = Field(min_length=20, max_length=5000)
    target_customers: str = Field(default="", max_length=2000)
    country: str = Field(default="MY", pattern="^[A-Z]{2}$")
    language: str = Field(default="English", min_length=2, max_length=80)
    brand_voice: str = Field(default="Professional and concise", max_length=500)
    batch_size: int = Field(default=3, ge=1, le=10, strict=True)


class PrepareRequest(Request):
    icp_code: str | None = Field(default=None, max_length=80)


class ContactChoice(Strict):
    person_index: int | None = Field(default=None, ge=0, le=4, strict=True)
    profile_url: str | None = Field(default=None, max_length=1500)
    business_contact: Person | None = None


class Decision(Strict):
    decision: Literal["APPROVED", "REJECTED", "CHANGES_REQUESTED"]
    note: str = Field(min_length=5, max_length=1000)


def run_for(db, wid, rid):
    run = db.scalar(
        select(PreparationRun)
        .where(PreparationRun.workspace_id == wid, PreparationRun.id == rid)
        .with_for_update()
    )
    if not run:
        raise HTTPException(404, "Preparation run not found")
    return run


def workspace_lock(db, wid):
    return db.scalar(select(Workspace).where(Workspace.id == wid).with_for_update())


def public_run(run):
    return {
        k: getattr(run, k)
        for k in ("id", "lead_id", "status", "stop_reason", "results", "created_at")
    }


def enqueue_workspace(db, workspace, kind, key):
    old = db.scalar(
        select(Job).where(Job.workspace_id == workspace.id, Job.idempotency_key == key)
    )
    if old:
        if old.kind != kind:
            raise HTTPException(409, "Idempotency key belongs to another command")
        return old
    if db.scalar(
        select(Job.id).where(
            Job.workspace_id == workspace.id,
            Job.lead_id.is_(None),
            Job.status.in_(["PENDING", "RUNNING"]),
        )
    ):
        raise HTTPException(409, "Workspace setup/discovery is already active")
    ctx = context(db, workspace.id)
    job = Job(
        workspace_id=workspace.id,
        kind=kind,
        managed=True,
        idempotency_key=key,
        payload={"context": ctx, "context_hash": fingerprint(ctx)},
    )
    db.add(job)
    db.flush()
    return job


@router.post("/automation/activate", status_code=202)
def activate(wid: UUID, data: Activation, actor=Depends(user), db=Depends(session)):
    scope(wid, actor, db, ["ADMIN"])
    workspace = workspace_lock(db, wid)
    old = db.scalar(
        select(Job).where(
            Job.workspace_id == wid, Job.idempotency_key == data.idempotency_key
        )
    )
    if old:
        if old.kind != "SETUP" or {
            k: old.payload["context"]["preferences"].get(k)
            for k in data.model_dump(exclude={"idempotency_key"})
        } != data.model_dump(exclude={"idempotency_key"}):
            raise HTTPException(409, "Idempotency key belongs to another activation")
        return {"job_id": old.id, "status": old.status}
    if db.scalar(
        select(Job.id).where(
            Job.workspace_id == wid,
            Job.managed.is_(True),
            Job.status.in_(["PENDING", "RUNNING"]),
        )
    ):
        raise HTTPException(409, "Finish existing preparation before reconfiguration")
    if not db.scalar(
        select(Catalog.id).where(
            Catalog.workspace_id == wid,
            Catalog.kind == "PRODUCT",
            Catalog.active.is_(True),
        )
    ):
        raise HTTPException(409, "Add an actual offering before activation")
    workspace.automation = data.model_dump(exclude={"idempotency_key"})
    workspace.automation_enabled = True
    workspace.next_discovery_at = None
    job = enqueue_workspace(db, workspace, "SETUP", data.idempotency_key)
    db.commit()
    return {"job_id": job.id, "status": job.status}


@router.post("/automation/pause")
def pause(wid: UUID, actor=Depends(user), db=Depends(session)):
    scope(wid, actor, db, ["ADMIN"])
    # Lock jobs before workspace, matching worker completion lock ordering.
    running = list(
        db.scalars(
            select(Job)
            .where(
                Job.workspace_id == wid, Job.managed.is_(True), Job.status == "RUNNING"
            )
            .with_for_update()
        )
    )
    workspace_lock(db, wid).automation_enabled = False
    for job in running:
        job.status, job.failure_code = "FAILED", "PRODUCT_PAUSED"
        job.lease_token = job.lease_until = None
        job.history = [
            *job.history,
            {"code": "PRODUCT_PAUSED", "at": now().isoformat()},
        ]
        if job.run_id:
            run = db.get(PreparationRun, job.run_id)
            run.status, run.stop_reason = "FAILED", "PRODUCT_PAUSED"
    db.commit()
    return {"enabled": False}


@router.post("/automation/resume")
def resume(wid: UUID, actor=Depends(user), db=Depends(session)):
    scope(wid, actor, db, ["ADMIN"])
    workspace = workspace_lock(db, wid)
    if not workspace.automation.get("discovery_query") and not db.scalar(
        select(Job.id).where(
            Job.workspace_id == wid,
            Job.kind == "SETUP",
            Job.status.in_(["PENDING", "FAILED"]),
        )
    ):
        raise HTTPException(409, "Finish or retry product setup first")
    workspace.automation_enabled = True
    db.commit()
    return {"enabled": True}


@router.post("/discovery", status_code=202)
def discover(wid: UUID, data: Request, actor=Depends(user), db=Depends(session)):
    scope(wid, actor, db, ["ADMIN", "OPERATOR"])
    workspace = workspace_lock(db, wid)
    if not workspace.automation_enabled or not workspace.automation.get(
        "discovery_query"
    ):
        raise HTTPException(409, "Activate and complete product setup first")
    job = enqueue_workspace(db, workspace, "DISCOVERY", data.idempotency_key)
    workspace.next_discovery_at = now() + timedelta(days=1)
    db.commit()
    return {"job_id": job.id, "status": job.status}


@router.post("/leads/{lid}/prepare", status_code=202)
def prepare(
    wid: UUID, lid: UUID, data: PrepareRequest, actor=Depends(user), db=Depends(session)
):
    scope(wid, actor, db, ["ADMIN", "OPERATOR"])
    lead = db.scalar(
        select(Lead).where(Lead.workspace_id == wid, Lead.id == lid).with_for_update()
    )
    if not lead:
        raise HTTPException(404, "Lead not found")
    old = db.scalar(
        select(Job).where(
            Job.workspace_id == wid, Job.idempotency_key == data.idempotency_key
        )
    )
    if old:
        if (
            old.lead_id != lid
            or not old.run_id
            or old.kind != "RESEARCH"
            or (data.icp_code and old.payload.get("icp_code") != data.icp_code)
        ):
            raise HTTPException(409, "Idempotency key belongs to another request")
        return {"run_id": old.run_id}
    if not db.get(Workspace, wid).automation_enabled:
        raise HTTPException(409, "Activate product preparation first")
    if db.scalar(
        select(Job.id).where(
            Job.workspace_id == wid,
            Job.lead_id == lid,
            Job.status.in_(["PENDING", "RUNNING"]),
        )
    ):
        raise HTTPException(409, "Preparation is already active")
    try:
        run = start(db, lead, data.idempotency_key, data.icp_code)
        db.commit()
    except ProviderFailure as exc:
        raise HTTPException(409, exc.code) from None
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Another preparation run is active") from None
    return {"run_id": run.id}


@router.get("/leads/{lid}/preparation")
def runs(wid: UUID, lid: UUID, actor=Depends(user), db=Depends(session)):
    scope(wid, actor, db)
    return [
        {**public_run(r), "current": index == 0}
        for index, r in enumerate(
            db.scalars(
                select(PreparationRun)
                .where(
                    PreparationRun.workspace_id == wid, PreparationRun.lead_id == lid
                )
                .order_by(PreparationRun.created_at.desc(), PreparationRun.id.desc())
                .limit(50)
            )
        )
    ]


@router.get("/preparation/{rid}")
def run(wid: UUID, rid: UUID, actor=Depends(user), db=Depends(session)):
    scope(wid, actor, db)
    return public_run(run_for(db, wid, rid))


@router.post("/preparation/{rid}/contact", status_code=202)
def contact(
    wid: UUID, rid: UUID, data: ContactChoice, actor=Depends(user), db=Depends(session)
):
    scope(wid, actor, db, ["ADMIN", "OPERATOR"])
    contact_job = db.scalar(
        select(Job)
        .where(Job.workspace_id == wid, Job.run_id == rid, Job.kind == "CONTACT_SEARCH")
        .with_for_update()
    )
    workspace_lock(db, wid)
    item = run_for(db, wid, rid)
    if item.status != "NEEDS_REVIEW" or item.stop_reason not in (
        "SUPPORTED_CONTACT_REQUIRED",
        "CONTACT_SEARCH_UNAVAILABLE",
    ):
        raise HTTPException(409, "Run is not waiting for contact resolution")
    if (
        not db.get(Workspace, wid).automation_enabled
        or fingerprint(context(db, wid, item.lead_id)) != item.context_hash
    ):
        raise HTTPException(
            409, "Resume product or start fresh preparation after context changes"
        )
    people = item.results.get("CONTACT_SEARCH", {}).get("people", [])
    if (data.person_index is None) == (data.business_contact is None):
        raise HTTPException(
            422, "Select a researched person or enter a source-backed business contact"
        )
    if data.business_contact:
        selected = data.business_contact.model_dump()
        try:
            cite(selected, item.results["RESEARCH"]["pages"])
        except ProviderFailure:
            raise HTTPException(
                422, "Use an exact quote from saved company research"
            ) from None
        quote = normalize(selected["evidence_quote"]).lower()
        if (
            any(
                normalize(selected[field]).lower() not in quote
                for field in ("name", "role", "email")
                if selected[field]
            )
            or not selected["email"]
            or not __import__("re").fullmatch(
                r"[^\s@]+@[^\s@]+\.[^\s@]+", selected["email"]
            )
        ):
            raise HTTPException(
                422,
                "Name, role and business email must be supported by the saved quote",
            )
        selected.update(profiles=[], profile_candidates=[])
    else:
        if data.person_index >= len(people):
            raise HTTPException(422, "Select a saved researched person")
        selected = dict(people[data.person_index])
    if data.profile_url:
        match = next(
            (
                p
                for p in selected["profile_candidates"]
                if p["url"] == data.profile_url and p["platform"] == "linkedin.com"
            ),
            None,
        )
        if not match:
            raise HTTPException(422, "Select a supported saved individual profile")
        selected["profiles"] = [
            p for p in selected["profiles"] if p["platform"] != "linkedin.com"
        ] + [match]
    if not selected.get("email") and not any(
        p["platform"] == "linkedin.com" for p in selected["profiles"]
    ):
        raise HTTPException(422, "Selected person has no supported outreach channel")
    selected["human_review"] = {"actor_id": str(actor.id), "at": now().isoformat()}
    item.results = {
        **item.results,
        "CONTACT_SEARCH": {
            **item.results["CONTACT_SEARCH"],
            "selected_contact": selected,
            "stop_reason": None,
        },
    }
    item.status, item.stop_reason = "PREPARING", None
    if contact_job:
        previous_reason = contact_job.failure_code
        contact_job.status, contact_job.failure_code = "COMPLETED", None
        contact_job.result = item.results["CONTACT_SEARCH"]
        contact_job.history = [
            *contact_job.history,
            {
                "code": "CONTACT_RESOLVED",
                "previous_reason": previous_reason,
                "actor_id": str(actor.id),
                "at": now().isoformat(),
            },
        ]
    research_job = db.scalar(
        select(Job).where(Job.run_id == item.id, Job.kind == "RESEARCH")
    )
    db.add(
        Job(
            workspace_id=wid,
            lead_id=item.lead_id,
            run_id=item.id,
            kind="SCORING",
            managed=True,
            idempotency_key=f"{item.id}:SCORING",
            payload=research_job.payload,
        )
    )
    db.commit()
    return {"run_id": item.id, "status": item.status}


@router.post("/preparation/{rid}/retry-contact-search", status_code=202)
def retry_contacts(wid: UUID, rid: UUID, actor=Depends(user), db=Depends(session)):
    scope(wid, actor, db, ["ADMIN", "OPERATOR"])
    # Same lock order as queue completion: job, workspace, run.
    job = db.scalar(
        select(Job)
        .where(Job.workspace_id == wid, Job.run_id == rid, Job.kind == "CONTACT_SEARCH")
        .with_for_update()
    )
    if not job:
        raise HTTPException(404, "Contact search job not found")
    workspace = workspace_lock(db, wid)
    item = run_for(db, wid, rid)
    if item.status == "PREPARING" and job.status in ("PENDING", "RUNNING"):
        return {"run_id": item.id, "status": item.status}
    if item.status != "NEEDS_REVIEW" or item.stop_reason not in (
        "SUPPORTED_CONTACT_REQUIRED",
        "CONTACT_SEARCH_UNAVAILABLE",
    ):
        raise HTTPException(409, "Run is not waiting for contact resolution")
    if (
        not workspace.automation_enabled
        or fingerprint(context(db, wid, item.lead_id)) != item.context_hash
    ):
        raise HTTPException(
            409, "Resume product or start fresh preparation after context changes"
        )
    item.status, item.stop_reason = "PREPARING", None
    job.status, job.failure_code = "PENDING", None
    job.attempts = 0
    job.available_at = now()
    job.checkpoint = {
        k: v for k, v in job.checkpoint.items() if not k.startswith("search:")
    }
    job.history = [
        *job.history,
        {
            "code": "MANUAL_CONTACT_SEARCH_RETRY",
            "actor_id": str(actor.id),
            "at": now().isoformat(),
        },
    ]
    db.commit()
    return {"run_id": item.id, "status": item.status}


@router.get("/approvals")
def approvals(wid: UUID, actor=Depends(user), db=Depends(session)):
    scope(wid, actor, db)
    output = []
    for a in db.scalars(
        select(Approval)
        .where(Approval.workspace_id == wid)
        .order_by(Approval.created_at.desc())
        .limit(100)
    ):
        item = db.get(PreparationRun, a.run_id)
        latest = db.scalar(
            select(PreparationRun.id)
            .where(
                PreparationRun.workspace_id == wid,
                PreparationRun.lead_id == item.lead_id,
            )
            .order_by(PreparationRun.created_at.desc(), PreparationRun.id.desc())
            .limit(1)
        )
        output.append(
            {
                **{
                    k: getattr(a, k)
                    for k in (
                        "id",
                        "run_id",
                        "snapshot",
                        "status",
                        "decision",
                        "created_at",
                    )
                },
                "stale": item.context_hash
                != fingerprint(context(db, wid, item.lead_id))
                or latest != item.id,
            }
        )
    return output


@router.post("/approvals/{aid}/decision")
def decide(
    wid: UUID, aid: UUID, data: Decision, actor=Depends(user), db=Depends(session)
):
    scope(wid, actor, db, ["ADMIN", "REVIEWER"])
    approval = db.scalar(
        select(Approval)
        .where(Approval.workspace_id == wid, Approval.id == aid)
        .with_for_update()
    )
    if not approval:
        raise HTTPException(404, "Approval not found")
    if approval.status != "PENDING":
        if (
            approval.status == data.decision
            and approval.decision.get("actor_id") == str(actor.id)
            and approval.decision.get("note") == data.note
        ):
            return {"status": approval.status, "sent": False}
        raise HTTPException(409, "Approval already decided")
    item = run_for(db, wid, approval.run_id)
    latest = db.scalar(
        select(PreparationRun.id)
        .where(
            PreparationRun.workspace_id == wid, PreparationRun.lead_id == item.lead_id
        )
        .order_by(PreparationRun.created_at.desc(), PreparationRun.id.desc())
        .limit(1)
    )
    if data.decision == "APPROVED" and (
        fingerprint(context(db, wid, item.lead_id)) != item.context_hash
        or latest != item.id
        or item.status != "PENDING_APPROVAL"
    ):
        raise HTTPException(
            409, "Draft context is stale; prepare and review a fresh draft"
        )
    approval.status = data.decision
    approval.decision = {
        "actor_id": str(actor.id),
        "at": now().isoformat(),
        "note": data.note,
    }
    item.status = data.decision
    db.commit()
    return {"status": approval.status, "sent": False}


@router.get("/operations")
def operations(wid: UUID, actor=Depends(user), db=Depends(session)):
    scope(wid, actor, db)
    usage = list(
        db.scalars(
            select(ProviderUsage)
            .where(ProviderUsage.workspace_id == wid)
            .order_by(ProviderUsage.created_at.desc())
            .limit(100)
        )
    )
    workspace = db.get(Workspace, wid)
    stalled = list(
        db.scalars(
            select(Job.id).where(
                Job.workspace_id == wid,
                Job.status == "RUNNING",
                Job.lease_until <= now(),
            )
        )
    )
    rows = [
        {
            k: getattr(u, k)
            for k in (
                "provider",
                "operation",
                "status",
                "estimated_microusd",
                "usage",
                "created_at",
            )
        }
        for u in usage
    ]
    current_runs = list(
        db.scalars(
            select(PreparationRun)
            .where(PreparationRun.workspace_id == wid)
            .distinct(PreparationRun.lead_id)
            .order_by(
                PreparationRun.lead_id,
                PreparationRun.created_at.desc(),
                PreparationRun.id.desc(),
            )
        )
    )
    provider_health = {}
    for row in rows:
        provider_health.setdefault(
            row["provider"],
            {"last_request_status": row["status"], "at": row["created_at"]},
        )
    waiting = (
        list(
            db.scalars(
                select(Job.id).where(
                    Job.workspace_id == wid,
                    Job.status == "PENDING",
                    Job.available_at < now() - timedelta(minutes=15),
                )
            )
        )
        if workspace.automation_enabled
        else []
    )
    return {
        "enabled": workspace.automation_enabled,
        "preferences": workspace.automation,
        "next_discovery_at": workspace.next_discovery_at,
        "stalled_jobs": stalled,
        "delayed_pending_jobs": waiting,
        "current_preparation": [public_run(r) for r in current_runs],
        "provider_health": provider_health,
        "recent_provider_usage": rows,
        "cost_basis": "Conservative reservations, not reconciled provider billing.",
    }
