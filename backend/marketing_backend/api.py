import secrets
from uuid import UUID
from datetime import timedelta
from fastapi import FastAPI, Depends, HTTPException, Header
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError
from . import contracts as out
from .db import session
from .models import (
    User,
    LoginSession,
    LoginAttempt,
    Workspace,
    Membership,
    Catalog,
    Lead,
    Job,
    now,
)
from .auth import user, scope, digest, verify_password, DUMMY
from .public_fetch import checked_url, FetchError

app = FastAPI(title="Marketing Backend Rebuild", version="0.1.0")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(Strict):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class WorkspaceInput(Strict):
    name: str = Field(min_length=2, max_length=120)


class CatalogInput(Strict):
    kind: Literal["PRODUCT", "ICP"]
    code: str = Field(pattern=r"^[A-Z0-9_]+$", max_length=80)
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=10, max_length=5000)
    rules: dict = Field(default_factory=dict)


class LeadInput(Strict):
    company_name: str = Field(min_length=2, max_length=200)
    website: str = Field(min_length=8, max_length=1500)


class ResearchRequest(Strict):
    idempotency_key: str = Field(min_length=8, max_length=120)


def lead_for(db, wid, lid):
    lead = db.scalar(
        select(Lead).where(Lead.workspace_id == wid, Lead.id == lid).with_for_update()
    )
    if not lead:
        raise HTTPException(404, "Lead not found")
    return lead


def job_read(j):
    return {
        k: getattr(j, k)
        for k in (
            "id",
            "workspace_id",
            "lead_id",
            "kind",
            "run_id",
            "managed",
            "status",
            "attempts",
            "max_attempts",
            "result",
            "failure_code",
            "history",
            "created_at",
            "available_at",
            "lease_until",
        )
    }


@app.get("/health")
def health(db=Depends(session)):
    db.execute(text("SELECT 1 FROM alembic_version"))
    return {"status": "ok", "backend": "python-workers"}


@app.post("/auth/login", response_model=out.LoginResponse)
def login(data: Login, db=Depends(session)):
    identity = digest(data.email.lower())
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:identity,0))"),
        {"identity": identity},
    )
    count = db.scalar(
        select(func.count())
        .select_from(LoginAttempt)
        .where(
            LoginAttempt.identity_hash == identity,
            LoginAttempt.created_at > now() - timedelta(minutes=5),
        )
    )
    if count >= 10:
        raise HTTPException(429, "Try signing in later")
    actor = db.scalar(select(User).where(User.email == data.email.lower()))
    valid = verify_password(data.password, actor.password_hash if actor else DUMMY)
    if not valid or not actor or not actor.active:
        db.add(LoginAttempt(identity_hash=identity))
        db.commit()
        raise HTTPException(401, "Invalid email or password")
    token = secrets.token_urlsafe(32)
    db.add(
        LoginSession(
            token_hash=digest(token),
            user_id=actor.id,
            expires_at=now() + timedelta(hours=12),
        )
    )
    db.commit()
    return {"token": token, "token_type": "bearer"}


@app.post("/auth/logout", status_code=204)
def logout(
    actor=Depends(user), db=Depends(session), authorization: str = Header(default="")
):
    login = db.get(LoginSession, digest(authorization[7:]))
    db.delete(login)
    db.commit()


@app.get("/workspaces", response_model=list[out.WorkspaceResponse])
def workspaces(actor=Depends(user), db=Depends(session)):
    return [
        {"id": w.id, "name": w.name, "role": m.role}
        for w, m in db.execute(
            select(Workspace, Membership)
            .join(Membership)
            .where(Membership.user_id == actor.id, Workspace.active.is_(True))
        )
    ]


@app.post("/workspaces", status_code=201, response_model=out.WorkspaceCreated)
def create_workspace(data: WorkspaceInput, actor=Depends(user), db=Depends(session)):
    if not actor.platform_admin:
        raise HTTPException(403, "Platform administrator required")
    w = Workspace(name=data.name)
    db.add(w)
    db.flush()
    db.add(Membership(workspace_id=w.id, user_id=actor.id, role="ADMIN"))
    db.commit()
    return {"id": w.id, "name": w.name}


@app.get("/workspaces/{wid}/catalog", response_model=list[out.CatalogResponse])
def catalog(wid: UUID, actor=Depends(user), db=Depends(session)):
    scope(wid, actor, db)
    return [
        {
            "id": c.id,
            "kind": c.kind,
            "code": c.code,
            "name": c.name,
            "description": c.description,
            "rules": c.rules,
        }
        for c in db.scalars(
            select(Catalog).where(Catalog.workspace_id == wid, Catalog.active.is_(True))
        )
    ]


@app.put("/workspaces/{wid}/catalog", status_code=201, response_model=out.CatalogSaved)
def save_catalog(
    wid: UUID, data: CatalogInput, actor=Depends(user), db=Depends(session)
):
    scope(wid, actor, db, ["ADMIN"])
    from .catalog_policy import lock_catalog_change

    lock_catalog_change(
        db, wid, kind=data.kind, code=data.code, desired=data.model_dump()
    )
    item = db.scalar(
        select(Catalog)
        .where(
            Catalog.workspace_id == wid,
            Catalog.kind == data.kind,
            Catalog.code == data.code,
        )
        .with_for_update()
    )
    if not item:
        item = Catalog(workspace_id=wid, **data.model_dump())
        db.add(item)
    else:
        if any(getattr(item, key) != value for key, value in data.model_dump().items()):
            item.context_version += 1
        for key, value in data.model_dump().items():
            setattr(item, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Catalog changed concurrently; try again") from None
    return {"id": item.id, "code": item.code}


@app.post("/workspaces/{wid}/leads", status_code=201, response_model=out.LeadResponse)
def create_lead(wid: UUID, data: LeadInput, actor=Depends(user), db=Depends(session)):
    scope(wid, actor, db, ["ADMIN", "OPERATOR"])
    from .pipeline import domain

    db.scalar(select(Workspace).where(Workspace.id == wid).with_for_update())
    try:
        checked_url(data.website)
    except FetchError:
        raise HTTPException(422, "Use a public company HTTP(S) website") from None
    if any(
        domain(lead.website) == domain(data.website)
        for lead in db.scalars(select(Lead).where(Lead.workspace_id == wid))
    ):
        raise HTTPException(409, "This company already has a lead")
    lead = Lead(workspace_id=wid, **data.model_dump())
    db.add(lead)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Company website already saved") from None
    return {"id": lead.id, "company_name": lead.company_name, "website": lead.website}


@app.get("/workspaces/{wid}/leads", response_model=list[out.LeadResponse])
def leads(wid: UUID, actor=Depends(user), db=Depends(session)):
    scope(wid, actor, db)
    return [
        {"id": l.id, "company_name": l.company_name, "website": l.website}
        for l in db.scalars(
            select(Lead)
            .where(Lead.workspace_id == wid)
            .order_by(Lead.created_at.desc(), Lead.id.desc())
            .limit(100)
        )
    ]


@app.post(
    "/workspaces/{wid}/leads/{lid}/research",
    status_code=202,
    response_model=out.JobResponse,
)
def research(
    wid: UUID,
    lid: UUID,
    data: ResearchRequest,
    actor=Depends(user),
    db=Depends(session),
):
    scope(wid, actor, db, ["ADMIN", "OPERATOR"])
    lead = lead_for(db, wid, lid)
    existing = db.scalar(
        select(Job).where(
            Job.workspace_id == wid, Job.idempotency_key == data.idempotency_key
        )
    )
    if existing:
        if existing.lead_id != lid:
            raise HTTPException(409, "Idempotency key belongs to another request")
        return job_read(existing)
    active = db.scalar(
        select(Job).where(
            Job.workspace_id == wid,
            Job.lead_id == lid,
            Job.status.in_(["PENDING", "RUNNING"]),
        )
    )
    if active:
        raise HTTPException(409, "Research already pending or running")
    context = [
        {
            "kind": c.kind,
            "code": c.code,
            "name": c.name,
            "description": c.description,
            "rules": c.rules,
        }
        for c in db.scalars(
            select(Catalog).where(Catalog.workspace_id == wid, Catalog.active.is_(True))
        )
    ]
    if not any(c["kind"] == "PRODUCT" for c in context) or not any(
        c["kind"] == "ICP" for c in context
    ):
        raise HTTPException(409, "Configure products and ICPs first")
    job = Job(
        workspace_id=wid,
        lead_id=lid,
        idempotency_key=data.idempotency_key,
        payload={
            "company_name": lead.company_name,
            "website": lead.website,
            "context": context,
        },
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409, "Concurrent research request; retry with the same key"
        ) from None
    return job_read(job)


@app.get("/workspaces/{wid}/jobs/{jid}", response_model=out.JobResponse)
def job(wid: UUID, jid: UUID, actor=Depends(user), db=Depends(session)):
    scope(wid, actor, db)
    item = db.scalar(select(Job).where(Job.workspace_id == wid, Job.id == jid))
    if not item:
        raise HTTPException(404, "Job not found")
    return job_read(item)


@app.get("/workspaces/{wid}/jobs", response_model=list[out.JobResponse])
def jobs(wid: UUID, actor=Depends(user), db=Depends(session)):
    scope(wid, actor, db)
    return [
        job_read(j)
        for j in db.scalars(
            select(Job)
            .where(Job.workspace_id == wid)
            .order_by(Job.created_at.desc())
            .limit(100)
        )
    ]


@app.post(
    "/workspaces/{wid}/jobs/{jid}/retry",
    status_code=202,
    response_model=out.JobResponse,
)
def retry(wid: UUID, jid: UUID, actor=Depends(user), db=Depends(session)):
    scope(wid, actor, db, ["ADMIN", "OPERATOR"])
    item = db.scalar(
        select(Job).where(Job.workspace_id == wid, Job.id == jid).with_for_update()
    )
    if not item:
        raise HTTPException(404, "Job not found")
    if item.status != "FAILED":
        raise HTTPException(409, "Only failed jobs can be retried")
    if item.lead_id:
        lead_for(db, wid, item.lead_id)
    if db.scalar(
        select(Job.id).where(
            Job.workspace_id == wid,
            Job.lead_id == item.lead_id,
            Job.status.in_(["PENDING", "RUNNING"]),
        )
    ):
        raise HTTPException(409, "Another attempt is already active")
    item.history = [
        *item.history,
        {
            "code": "MANUAL_RETRY",
            "previous_attempts": item.attempts,
            "at": now().isoformat(),
        },
    ]
    item.status = "PENDING"
    item.attempts = 0
    item.failure_code = None
    item.available_at = now()
    if item.managed:
        # Explicit retries regenerate invalid model outputs, retaining fetched/search evidence.
        item.checkpoint = {
            k: v for k, v in item.checkpoint.items() if not k.startswith("model:")
        }
        from .pipeline import valid_context
        from .research import ProviderFailure
        from .models import PreparationRun

        if not db.get(Workspace, wid).automation_enabled:
            raise HTTPException(409, "Resume automation before retrying")
        try:
            valid_context(db, item)
        except ProviderFailure:
            raise HTTPException(
                409, "Context changed; start a fresh preparation run"
            ) from None
        if item.run_id:
            run = db.get(PreparationRun, item.run_id)
            run.status, run.stop_reason = "PREPARING", None
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409, "Another preparation attempt is already active"
        ) from None
    return job_read(item)


from .frontend_api import router as frontend_router

app.include_router(frontend_router)

from .native_api import router as native_router

app.include_router(native_router)

from .discovery_api import router as discovery_router

app.include_router(discovery_router)
