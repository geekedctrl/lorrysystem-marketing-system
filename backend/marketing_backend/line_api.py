"""Canonical product-line commands. Human approval stays in the existing API."""
from uuid import UUID
from datetime import timedelta, datetime
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .auth import scope, user
from .db import session
from .models import ProductLine, Catalog, Lead, Job, PreparationRun, Workspace, now
from .product_lines import line_for, mutation_lock, invalidate, mirror_default, enqueue, scoped_key
from .research import ProviderFailure
from .stage_contracts import content_hash
from . import contracts as out

router = APIRouter(prefix="/workspaces/{wid}/product-lines", tags=["Product lines"])


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Settings(Strict):
    product_description: str = Field(default="", max_length=5000)
    target_customers: str = Field(default="", max_length=2000)
    discovery_query: str = Field(default="", max_length=300)
    country: str = Field(default="MY", pattern=r"^[A-Z]{2}$")
    language: str = Field(default="English", min_length=2, max_length=80)
    brand_voice: str = Field(default="Professional and concise", max_length=500)
    batch_size: int = Field(default=3, ge=1, le=10, strict=True)
    discovery_interval_minutes: int = Field(default=1440, ge=60, le=43200, strict=True)
    qualification_score: int = Field(default=60, ge=0, le=100, strict=True)
    matching_fit: int = Field(default=60, ge=0, le=100, strict=True)


class Limits(Strict):
    per_pool_concurrency: int = Field(default=1, ge=1, le=5, strict=True)
    provider_requests_per_minute: int = Field(default=60, ge=1, le=600, strict=True)
    monthly_budget_microusd: int = Field(default=50000000, ge=0, le=50000000, strict=True)


class CreateLine(Strict):
    code: str = Field(min_length=2, max_length=80, pattern=r"^[A-Z0-9_]+$")
    name: str = Field(min_length=2, max_length=120)
    settings: Settings = Field(default_factory=Settings)
    limits: Limits = Field(default_factory=Limits)


class PatchLine(Strict):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    settings: Settings | None = None
    limits: Limits | None = None


class LineResponse(Strict):
    id: UUID
    code: str
    name: str
    paused: bool
    versioned: bool
    settings: dict
    limits: dict
    context_version: int
    context_hash: str
    next_discovery_at: datetime | None


class CatalogWrite(Strict):
    kind: Literal["PRODUCT", "ICP"]
    code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Z0-9_]+$")
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=10, max_length=5000)
    rules: dict = Field(default_factory=dict)
    active: bool = Field(default=True, strict=True)


class Command(Strict):
    idempotency_key: str = Field(min_length=8, max_length=120)


class Prepare(Command):
    icp_code: str | None = Field(default=None, max_length=80)


def read(line):
    return {key: getattr(line,key) for key in ("id","code","name","paused","versioned","settings","limits","context_version","context_hash","next_discovery_at")}


def get_line(db, wid, lid):
    try:
        return line_for(db, wid, lid)
    except ProviderFailure:
        raise HTTPException(404, "Product line not found") from None


def commit(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Concurrent product-line change; retry the same request") from None


@router.get("", response_model=list[LineResponse])
def list_lines(wid: UUID, actor=Depends(user), db=Depends(session)):
    scope(wid,actor,db)
    return [read(line) for line in db.scalars(select(ProductLine).where(ProductLine.workspace_id==wid).order_by(ProductLine.code))]


@router.post("", status_code=201, response_model=LineResponse)
def create_line(wid: UUID, body: CreateLine, actor=Depends(user), db=Depends(session)):
    scope(wid,actor,db,["ADMIN"])
    db.scalar(select(Workspace).where(Workspace.id==wid).with_for_update())
    if body.code=="DEFAULT":
        raise HTTPException(409,"Use the workspace's existing default line")
    old=db.scalar(select(ProductLine).where(ProductLine.workspace_id==wid,ProductLine.code==body.code))
    values=dict(name=body.name,settings=body.settings.model_dump(),limits=body.limits.model_dump())
    if old:
        if any(getattr(old,k)!=v for k,v in values.items()):
            raise HTTPException(409,"Product-line code already exists with different settings")
        return read(old)
    line=ProductLine(workspace_id=wid,code=body.code,paused=True,versioned=True,
                     context_hash=content_hash(values),**values)
    db.add(line);commit(db)
    return read(line)


@router.get("/{lid}", response_model=LineResponse)
def detail(wid: UUID,lid: UUID,actor=Depends(user),db=Depends(session)):
    scope(wid,actor,db)
    return read(get_line(db,wid,lid))


@router.patch("/{lid}", response_model=LineResponse)
def update_line(wid: UUID,lid: UUID,body: PatchLine,actor=Depends(user),db=Depends(session)):
    scope(wid,actor,db,["ADMIN"]);get_line(db,wid,lid)
    line=mutation_lock(db,wid,lid)
    changed=False
    if body.name is not None:line.name=body.name
    for field,schema in (("settings",Settings),("limits",Limits)):
        patch=getattr(body,field)
        if patch is not None:
            merged=schema.model_validate({**getattr(line,field),**patch.model_dump(exclude_unset=True)}).model_dump()
            if merged!=getattr(line,field):setattr(line,field,merged);changed=True
    if changed:invalidate(db,line)
    db.flush();mirror_default(db,line);commit(db);db.refresh(line)
    return read(line)


@router.get("/{lid}/catalog", response_model=list[out.CatalogState])
def catalog(wid: UUID,lid: UUID,actor=Depends(user),db=Depends(session)):
    scope(wid,actor,db);get_line(db,wid,lid)
    return [dict(id=c.id,kind=c.kind,code=c.code,name=c.name,description=c.description,rules=c.rules,
                 active=c.active,version=c.context_version,product_line_id=c.product_line_id)
            for c in db.scalars(select(Catalog).where(Catalog.workspace_id==wid,Catalog.product_line_id==lid).order_by(Catalog.kind,Catalog.code))]


@router.put("/{lid}/catalog", status_code=201, response_model=out.CatalogState)
def save_catalog(wid: UUID,lid: UUID,body: CatalogWrite,actor=Depends(user),db=Depends(session)):
    scope(wid,actor,db,["ADMIN"]);get_line(db,wid,lid)
    line=mutation_lock(db,wid,lid)
    row=db.scalar(select(Catalog).where(Catalog.workspace_id==wid,Catalog.product_line_id==lid,Catalog.kind==body.kind,Catalog.code==body.code))
    values=body.model_dump();changed=not row or any(getattr(row,k)!=v for k,v in values.items())
    if changed:
        invalidate(db,line)
        if row:
            row.context_version+=1
            for key,value in values.items():setattr(row,key,value)
        else:
            row=Catalog(workspace_id=wid,product_line_id=lid,**values);db.add(row)
    commit(db)
    return dict(id=row.id,kind=row.kind,code=row.code,name=row.name,description=row.description,rules=row.rules,
                active=row.active,version=row.context_version,product_line_id=lid)


@router.post("/{lid}/pause", response_model=LineResponse)
def pause(wid: UUID,lid: UUID,actor=Depends(user),db=Depends(session)):
    scope(wid,actor,db,["ADMIN"]);get_line(db,wid,lid)
    line=mutation_lock(db,wid,lid);line.paused=True
    for job in db.scalars(select(Job).where(Job.product_line_id==lid,Job.status=="RUNNING")):
        job.status,job.failure_code="FAILED","PRODUCT_LINE_PAUSED"
        job.lease_token=job.lease_until=None
        if job.run_id:
            run=db.get(PreparationRun,job.run_id)
            if run.status=="PREPARING":run.status,run.stop_reason="FAILED","PRODUCT_LINE_PAUSED"
        from .worker_contracts import record
        record(db,job,"FAILURE","CONFIGURATION_ERROR")
    mirror_default(db,line);commit(db)
    return read(line)


@router.post("/{lid}/resume", response_model=LineResponse)
def resume(wid: UUID,lid: UUID,actor=Depends(user),db=Depends(session)):
    scope(wid,actor,db,["ADMIN"]);get_line(db,wid,lid)
    line=mutation_lock(db,wid,lid)
    kinds=set(db.scalars(select(Catalog.kind).where(Catalog.product_line_id==lid,Catalog.active.is_(True))))
    if not {"PRODUCT","ICP"}<=kinds or not line.settings.get("discovery_query"):
        raise HTTPException(409,"Add active products/ICPs and a query, or run product setup first")
    line.paused,line.versioned=False,True
    if line.next_discovery_at is None:line.next_discovery_at=now()+timedelta(minutes=line.settings.get("discovery_interval_minutes",1440))
    mirror_default(db,line);commit(db)
    return read(line)


@router.post("/{lid}/setup", status_code=202, response_model=out.JobQueued)
def setup(wid: UUID,lid: UUID,body: Command,actor=Depends(user),db=Depends(session)):
    scope(wid,actor,db,["ADMIN"]);get_line(db,wid,lid)
    line=mutation_lock(db,wid,lid)
    if not db.scalar(select(Catalog.id).where(Catalog.product_line_id==lid,Catalog.kind=="PRODUCT",Catalog.active.is_(True))):
        raise HTTPException(409,"Add an actual product before setup")
    line.paused,line.versioned=False,True;mirror_default(db,line)
    try:job=enqueue(db,line,"SETUP",body.idempotency_key)
    except ProviderFailure as exc:raise HTTPException(409,exc.code) from None
    commit(db);return dict(job_id=job.id,status=job.status)


@router.post("/{lid}/discovery", status_code=202, response_model=out.JobQueued)
def discover(wid: UUID,lid: UUID,body: Command,actor=Depends(user),db=Depends(session)):
    scope(wid,actor,db,["ADMIN","OPERATOR"]);get_line(db,wid,lid)
    line=mutation_lock(db,wid,lid)
    if not line.settings.get("discovery_query"):raise HTTPException(409,"Complete product setup first")
    line.versioned=True
    try:job=enqueue(db,line,"DISCOVERY",body.idempotency_key)
    except ProviderFailure as exc:raise HTTPException(409,exc.code) from None
    line.next_discovery_at=now()+timedelta(minutes=line.settings.get("discovery_interval_minutes",1440))
    mirror_default(db,line);commit(db);return dict(job_id=job.id,status=job.status)


@router.post("/{lid}/leads/{lead_id}/prepare", status_code=202, response_model=out.PreparationStarted)
def prepare(wid: UUID,lid: UUID,lead_id: UUID,body: Prepare,actor=Depends(user),db=Depends(session)):
    scope(wid,actor,db,["ADMIN","OPERATOR"]);line=get_line(db,wid,lid)
    lead=db.scalar(select(Lead).where(Lead.workspace_id==wid,Lead.id==lead_id).with_for_update())
    if not lead:raise HTTPException(404,"Company not found")
    old=db.scalar(select(Job).where(Job.workspace_id==wid,Job.idempotency_key==scoped_key(line,body.idempotency_key)))
    if old:
        if old.product_line_id!=lid or old.lead_id!=lead_id or not old.run_id or (body.icp_code and old.payload.get("icp_code")!=body.icp_code):
            raise HTTPException(409,"Idempotency key belongs to another preparation")
        return dict(run_id=old.run_id)
    from .pipeline import start
    try:run=start(db,lead,body.idempotency_key,body.icp_code,lid)
    except ProviderFailure as exc:raise HTTPException(409,exc.code) from None
    commit(db);return dict(run_id=run.id)


@router.get("/{lid}/preparation", response_model=list[out.PreparationResponse],response_model_exclude_unset=True)
def runs(wid: UUID,lid: UUID,actor=Depends(user),db=Depends(session)):
    scope(wid,actor,db);get_line(db,wid,lid)
    from .native_api import public_run
    return [public_run(r) for r in db.scalars(select(PreparationRun).where(PreparationRun.workspace_id==wid,
        PreparationRun.product_line_id==lid).order_by(PreparationRun.created_at.desc()).limit(100))]
