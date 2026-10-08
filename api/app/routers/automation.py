import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from app.auth import authenticated_user, token_hash
from app.db.session import ControlSession, SessionLocal, get_db
from app.models.automation import AutomationWorker, AutomationJob, ProductAutomationPlan
from app.models.workspaces import Workspace, AccessAudit
from app.models.catalog import Product, ICPProfile
from app.models.discovery import LeadCandidate
from app.models.leads import LeadResearch
from app.models.marketing import Event
from app.services.automation_access import worker_for, job_principal
from app.services.product_automation import (
    schedule,
    prepare_claim,
    after_research,
    after_stage,
    fail_native,
)
from app.workspace_context import current_principal

router = APIRouter(prefix="/api/automation", tags=["Product automation"])


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Offering(Strict):
    id: UUID | None = None
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=10, max_length=5000)


class ProductSetup(Strict):
    product_type: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=20, max_length=5000)
    target_customers: str = Field(default="", max_length=2000)
    country_code: str = Field(default="MY", pattern=r"^[A-Z]{2}$")
    language: str = Field(default="English", min_length=2, max_length=60)
    brand_voice: str = Field(
        default="Clear, professional and helpful", min_length=3, max_length=2000
    )
    daily_new_companies: int = Field(default=5, ge=1, le=10, strict=True)
    products: list[Offering] = Field(min_length=1, max_length=30)


class ICPProposal(Strict):
    name: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=15, max_length=2000)


class SetupOutput(Strict):
    discovery_query: str = Field(min_length=3, max_length=300)
    icps: list[ICPProposal] = Field(min_length=1, max_length=5)


class CatalogOffering(Offering):
    code: str = Field(pattern=r"^[A-Z0-9_]+$", max_length=80)


class CatalogICP(ICPProposal):
    code: str = Field(pattern=r"^[A-Z0-9_]+$", max_length=80)
    qualification_rules: dict = Field(default_factory=dict)


class CatalogImport(Strict):
    source: str = Field(min_length=3, max_length=300)
    product_type: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=20, max_length=5000)
    target_customers: str = Field(max_length=2000)
    discovery_query: str = Field(min_length=3, max_length=300)
    products: list[CatalogOffering] = Field(min_length=1, max_length=30)
    icps: list[CatalogICP] = Field(min_length=1, max_length=30)


class WorkerCreate(Strict):
    name: str = Field(min_length=3, max_length=100)


class Finish(Strict):
    job_id: UUID
    lease_token: str = Field(min_length=32, max_length=128)
    output: dict = Field(default_factory=dict)
    failure_reason: str | None = Field(default=None, pattern=r"^[A-Z0-9_]{1,80}$")
    usage: "JobUsage | None" = None


class JobUsage(Strict):
    search_requests: int = Field(default=0, ge=0, le=100, strict=True)
    fetch_requests: int = Field(default=0, ge=0, le=100, strict=True)
    model_requests: int = Field(default=0, ge=0, le=10, strict=True)
    input_tokens: int | None = Field(default=None, ge=0, le=1000000, strict=True)
    output_tokens: int | None = Field(default=None, ge=0, le=1000000, strict=True)
    search_status: str = Field(default="NOT_USED", pattern=r"^(OK|ERROR|NOT_USED)$")
    model_status: str = Field(default="NOT_USED", pattern=r"^(OK|ERROR|NOT_USED)$")


Finish.model_rebuild()


def admin():
    principal = current_principal.get()
    if not principal or principal.role != "ADMIN" or principal.automation_job_id:
        raise HTTPException(403, "A workspace administrator is required")
    return principal


def job_read(job):
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
            "finished_at",
        )
    }


def scoped_job(db, kind=None, lock=False):
    principal = current_principal.get()
    if not principal or not principal.automation_job_id:
        raise HTTPException(403, "A claimed job is required")
    statement = select(AutomationJob).where(
        AutomationJob.id == principal.automation_job_id
    )
    job = db.scalar(statement.with_for_update() if lock else statement)
    if not job or job.status != "RUNNING" or (kind and job.kind != kind):
        raise HTTPException(409, "Job is unavailable")
    return job


@router.get("/plan")
def plan(db=Depends(get_db)):
    from app.services.automation_metrics import operational_summary

    row = db.scalar(select(ProductAutomationPlan))
    if not row:
        return {
            "configured": False,
            "enabled": False,
            "state": "DRAFT",
            "profile": {},
            "jobs": [],
            "operations": operational_summary(db, [], set(), False),
        }
    from app.services.automation_status import current_job_ids, describe_job

    jobs = list(
        db.scalars(
            select(AutomationJob).order_by(AutomationJob.created_at.desc()).limit(25)
        )
    )
    current_ids = current_job_ids(db, jobs)
    from app.services.automation_metrics import operational_summary

    return {
        "configured": True,
        "enabled": row.enabled,
        "state": row.state,
        "profile": row.profile,
        "configuration": row.configuration,
        "next_discovery_at": row.next_discovery_at,
        "operations": operational_summary(db, jobs, current_ids, row.enabled),
        "jobs": [describe_job(j, j.id in current_ids, row.enabled) for j in jobs],
    }


@router.post("/activate", status_code=202)
def activate(data: ProductSetup, db=Depends(get_db)):
    principal = admin()
    db.execute(
        text(
            "SELECT pg_advisory_xact_lock(hashtextextended('shared-automation-claim',0))"
        )
    )
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": f"onboarding:{principal.workspace_id}"},
    )
    if db.scalar(
        select(AutomationJob.id)
        .where(AutomationJob.status.in_(("PENDING", "RUNNING")))
        .limit(1)
    ):
        raise HTTPException(
            409, "Finish the current setup/jobs before changing this product"
        )
    products = list(db.scalars(select(Product)))
    if len({o.name.casefold() for o in data.products}) != len(data.products):
        raise HTTPException(422, "Offering names must be distinct")
    from app.models.pipeline import PipelineRun

    if db.scalar(
        select(PipelineRun.id)
        .where(PipelineRun.status.in_(("PENDING", "RUNNING")))
        .limit(1)
    ) or db.scalar(
        select(LeadResearch.id)
        .where(LeadResearch.research_status.in_(("PENDING", "RUNNING")))
        .limit(1)
    ):
        raise HTTPException(
            409, "Finish existing lead preparation jobs before changing this product"
        )
    selected = []
    for offering in data.products:
        product = (
            db.get(Product, offering.id)
            if offering.id
            else next(
                (p for p in products if p.name.casefold() == offering.name.casefold()),
                None,
            )
        )
        if offering.id and not product:
            raise HTTPException(404, "Catalog item not found")
        if not product:
            product = Product(
                code="PRODUCT_" + secrets.token_hex(5).upper(), name=offering.name
            )
            db.add(product)
        if product in selected:
            raise HTTPException(422, "Catalog items must be distinct")
        product.name = offering.name
        product.description = offering.description
        product.active = True
        selected.append(product)
    for product in products:
        if product not in selected:
            product.active = False
    row = db.scalar(select(ProductAutomationPlan))
    if not row:
        row = ProductAutomationPlan()
        db.add(row)
    row.profile = data.model_dump(mode="json")
    row.enabled = True
    row.state = "CONFIGURING"
    row.activated_by = principal.actor
    row.configuration = {}
    schedule(db, "SETUP")
    db.add(
        Event(
            event_type="product_automation_activated",
            entity_type="WORKSPACE",
            entity_id=principal.workspace_id,
            actor_type="USER",
            actor_id=principal.actor,
            metadata_json={
                "automatic_preparation": True,
                "human_outreach_approval_required": True,
                "sending_enabled": False,
            },
        )
    )
    db.commit()
    return plan(db)


@router.post("/catalog-import")
def import_catalog(data: CatalogImport, db=Depends(get_db)):
    principal = admin()
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('shared-automation-claim',0))"))
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
               {"key": f"onboarding:{principal.workspace_id}"})
    from app.models.pipeline import PipelineRun
    if (db.scalar(select(AutomationJob.id).where(AutomationJob.status.in_(("PENDING", "RUNNING"))).limit(1))
        or db.scalar(select(PipelineRun.id).where(PipelineRun.status.in_(("PENDING", "RUNNING"))).limit(1))
        or db.scalar(select(LeadResearch.id).where(LeadResearch.research_status.in_(("PENDING", "RUNNING"))).limit(1))):
        raise HTTPException(409, "Finish current product jobs before importing catalog context")
    row = db.scalar(select(ProductAutomationPlan).with_for_update())
    if not row:
        raise HTTPException(409, "Set up this product before importing its catalog")
    for entries in (data.products, data.icps):
        if len({e.code for e in entries}) != len(entries) or len({e.name.casefold() for e in entries}) != len(entries):
            raise HTTPException(422, "Catalog codes and names must be distinct")
    from app.routers.pipeline import scoring_rubric
    for proposal in data.icps:
        scoring_rubric(ICPProfile(qualification_rules=proposal.qualification_rules))
    selected_products = []
    selected_icps = []
    for model, entries, selected in ((Product, data.products, selected_products), (ICPProfile, data.icps, selected_icps)):
        existing = list(db.scalars(select(model)))
        for entry in entries:
            item = next((i for i in existing if i.code == entry.code), None)
            if model is Product and entry.id:
                item = db.get(Product, entry.id)
                if not item:
                    raise HTTPException(404, "Workspace catalog item not found")
                if any(i.code == entry.code and i.id != item.id for i in existing):
                    raise HTTPException(409, "Catalog code belongs to another offering")
            if not item:
                item = model(code=entry.code, name=entry.name)
                db.add(item)
            if item in selected:
                raise HTTPException(422, "An offering cannot be imported twice")
            item.code, item.name, item.description, item.active = entry.code, entry.name, entry.description, True
            if model is ICPProfile:
                item.qualification_rules = entry.qualification_rules
            selected.append(item)
        for item in existing:
            if item not in selected:
                item.active = False
    db.flush()
    row.profile = {**row.profile, "product_type": data.product_type, "description": data.description,
                   "target_customers": data.target_customers,
                   "products": [{"id": str(p.id), "name": p.name, "description": p.description} for p in selected_products]}
    row.configuration = {"discovery_query": data.discovery_query,
                         "icps": [{"name": i.name, "description": i.description} for i in selected_icps],
                         "catalog_source": data.source}
    row.state = "ACTIVE"
    db.add(Event(event_type="product_catalog_imported", entity_type="WORKSPACE", entity_id=principal.workspace_id,
                 actor_type="USER", actor_id=principal.actor,
                 metadata_json={"source": data.source, "products": len(selected_products), "icps": len(selected_icps)}))
    db.commit()
    with ControlSession() as settings_db:
        workspace = settings_db.get(Workspace, principal.workspace_id)
        workspace.settings = {**workspace.settings, "description": data.description}
        settings_db.commit()
    db.commit()
    return {"source": data.source, "products": len(selected_products), "icps": len(selected_icps), "enabled": row.enabled}


@router.post("/pause")
def pause(db=Depends(get_db)):
    principal = admin()
    row = db.scalar(select(ProductAutomationPlan))
    if not row:
        raise HTTPException(404, "Product setup not found")
    row.enabled = False
    db.add(
        Event(
            event_type="product_automation_paused",
            entity_type="WORKSPACE",
            entity_id=principal.workspace_id,
            actor_type="USER",
            actor_id=principal.actor,
            metadata_json={},
        )
    )
    db.commit()
    return plan(db)


@router.post("/resume")
def resume(db=Depends(get_db)):
    principal = admin()
    row = db.scalar(select(ProductAutomationPlan))
    if not row:
        raise HTTPException(404, "Product setup not found")
    row.enabled = True
    db.add(
        Event(
            event_type="product_automation_resumed",
            entity_type="WORKSPACE",
            entity_id=principal.workspace_id,
            actor_type="USER",
            actor_id=principal.actor,
            metadata_json={},
        )
    )
    db.commit()
    return plan(db)


@router.post("/jobs/{job_id}/retry", status_code=202)
def retry(job_id: UUID, db=Depends(get_db)):
    admin()
    # Internal contact/qualification services can commit; hold the lock outside
    # that session so concurrent retries/worker finishes remain serialized.
    with ControlSession() as guard:
        guard.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": f"finish:{job_id}"},
        )
        return retry_job(job_id, db)


def retry_job(job_id, db):
    principal = admin()
    job = db.scalar(
        select(AutomationJob).where(AutomationJob.id == job_id).with_for_update()
    )
    if not job:
        raise HTTPException(404, "Automation job not found")
    p = db.scalar(select(ProductAutomationPlan))
    if not p.enabled:
        raise HTTPException(409, "Resume product automation before retrying")
    if job.status not in ("FAILED", "NEEDS_REVIEW"):
        raise HTTPException(409, "Only interrupted jobs can be retried")
    from app.services.automation_status import current_job_ids

    if job.id not in current_job_ids(db, [job]):
        raise HTTPException(
            409,
            "A newer attempt supersedes this job. Review the current preparation status.",
        )
    from app.models.pipeline import PipelineRun

    if job.kind == "RESEARCH":
        report = db.get(LeadResearch, job.related_id)
        if not report:
            raise HTTPException(409, "Research no longer exists")
        if db.scalar(
            select(LeadResearch.id)
            .where(
                LeadResearch.lead_id == report.lead_id,
                LeadResearch.id != report.id,
                LeadResearch.research_status.in_(("PENDING", "RUNNING")),
            )
            .limit(1)
        ):
            raise HTTPException(
                409, "Another research run is already queued for this lead"
            )
        if report.research_status in ("COMPLETED", "PARTIAL"):
            if not after_research(db, job):
                raise HTTPException(
                    409, "Add a supported reachable business contact before continuing"
                )
            job.status = "COMPLETED"
            job.failure_reason = None
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
            return job_read(job)
        report.research_status = "PENDING"
        report.started_at = None
        report.completed_at = None
    elif job.kind in ("SCORING", "MATCHING", "DRAFTING"):
        run = db.get(PipelineRun, job.related_id)
        if not run:
            raise HTTPException(409, "Stage no longer exists")
        if db.scalar(
            select(PipelineRun.id)
            .where(
                PipelineRun.lead_id == run.lead_id,
                PipelineRun.id != run.id,
                PipelineRun.status.in_(("PENDING", "RUNNING")),
            )
            .limit(1)
        ):
            raise HTTPException(
                409, "Another preparation stage is already queued for this lead"
            )
        if run.status == "COMPLETED":
            after_stage(db, job)
            job.status = "COMPLETED"
            job.failure_reason = None
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
            return job_read(job)
        run.status = "PENDING"
        run.started_at = None
        run.finished_at = None
        run.claimed_by = None
        run.failure_reason = None
    job.status = "PENDING"
    job.failure_reason = None
    job.lease_hash = None
    job.worker_id = None
    job.started_at = None
    job.finished_at = None
    job.lease_expires_at = None
    if job.kind == "SETUP":
        p.state = "CONFIGURING"
    db.add(
        Event(
            event_type="product_automation_retry_requested",
            entity_type="AUTOMATION_JOB",
            entity_id=job.id,
            actor_type="USER",
            actor_id=principal.actor,
            metadata_json={},
        )
    )
    db.commit()
    return job_read(job)


@router.get("/job-context")
def context(db=Depends(get_db)):
    job = scoped_job(db)
    row = db.scalar(select(ProductAutomationPlan))
    return {
        "job": job_read(job),
        "profile": row.profile,
        "configuration": row.configuration,
        "products": [
            {
                "id": str(p.id),
                "code": p.code,
                "name": p.name,
                "description": p.description,
            }
            for p in db.scalars(select(Product).where(Product.active.is_(True)))
        ],
    }


@router.get("/memory")
def memory(db=Depends(get_db)):
    scoped_job(db, "DISCOVERY")
    # Candidate history is workspace-owned discovery memory, independent of n8n tables.
    from app.models.companies import Company

    domains = (
        select(LeadCandidate.domain)
        .where(LeadCandidate.domain.is_not(None))
        .union(select(Company.domain).where(Company.domain.is_not(None)))
        .limit(10000)
    )
    return {"domains": list(db.scalars(domains))}


@router.post("/candidates")
def candidate(data: dict, db=Depends(get_db)):
    from app.schemas.candidate import CandidateCreate, CandidateAccept
    from app.services.candidate_service import (
        create_candidate,
        accept_candidate,
        ICPProfileNotFoundError,
        CandidateStateError,
        CandidateContactConflictError,
        ExistingActiveLeadError,
    )
    from pydantic import ValidationError

    # Read under the lock once: a cached pre-lock result could lose accepted
    # counts or allow concurrent requests to exceed the batch limit.
    job = scoped_job(db, "DISCOVERY", lock=True)
    try:
        parsed = CandidateCreate.model_validate(data)
    except ValidationError:
        raise HTTPException(422, "Invalid sourced discovery candidate") from None
    if parsed.icp_confidence < 0.75:
        raise HTTPException(
            422,
            "Automatic acceptance requires supported ICP confidence of at least 75%",
        )
    if job.result.get("accepted_leads", 0) >= job.payload.get(
        "target_new_companies", 5
    ):
        raise HTTPException(409, "Discovery batch limit reached")
    try:
        result = create_candidate(db, parsed, commit=False)
    except (ValueError, ICPProfileNotFoundError):
        raise HTTPException(422, "Candidate evidence or targeting is invalid") from None
    if result["outcome"] != "NEW_CANDIDATE":
        db.commit()
        return {"outcome": result["outcome"]}
    saved = result["candidate"]
    candidate_id = saved.id if hasattr(saved, "id") else saved["id"]
    try:
        accepted = accept_candidate(
            db,
            candidate_id=UUID(str(candidate_id)),
            data=CandidateAccept(
                reviewed_by=current_principal.get().actor,
                review_notes="Automatically accepted under the activated product discovery policy.",
            ),
            commit=False,
        )
    except (
        ValueError,
        CandidateStateError,
        CandidateContactConflictError,
        ExistingActiveLeadError,
    ):
        raise HTTPException(422, "Candidate cannot be accepted automatically") from None
    research = db.scalar(
        select(LeadResearch).where(
            LeadResearch.lead_id == accepted["lead_id"],
            LeadResearch.research_status == "PENDING",
        )
    )
    if research:
        schedule(db, "RESEARCH", research.id)
    job.result = {
        **job.result,
        "accepted_leads": job.result.get("accepted_leads", 0) + 1,
    }
    db.commit()
    return {"outcome": "ACCEPTED", "lead_id": str(accepted["lead_id"])}


@router.post("/workers", status_code=201)
def enroll(data: WorkerCreate, request: Request):
    admin()
    with ControlSession() as control:
        user = authenticated_user(control, request)
        if not user.platform_admin:
            raise HTTPException(
                403, "Only a platform administrator can enroll shared workers"
            )
        if control.scalar(
            select(AutomationWorker.id).where(AutomationWorker.name == data.name)
        ):
            raise HTTPException(409, "Worker name already exists")
        token = "aw_" + secrets.token_urlsafe(48)
        worker = AutomationWorker(name=data.name, token_hash=token_hash(token))
        control.add(worker)
        control.add(
            AccessAudit(
                actor=user.email,
                action="automation_worker_enrolled",
                detail={"name": data.name},
            )
        )
        control.commit()
        return {"id": str(worker.id), "name": worker.name, "token": token}


@router.get("/workers")
def workers(request: Request):
    admin()
    with ControlSession() as control:
        if not authenticated_user(control, request).platform_admin:
            raise HTTPException(403, "Platform administrator required")
        return [
            {
                "id": str(w.id),
                "name": w.name,
                "active": w.active,
                "created_at": w.created_at,
            }
            for w in control.scalars(
                select(AutomationWorker).order_by(AutomationWorker.created_at.desc())
            )
        ]


@router.delete("/workers/{worker_id}")
def revoke_worker(worker_id: UUID, request: Request):
    admin()
    with ControlSession() as control:
        user = authenticated_user(control, request)
        if not user.platform_admin:
            raise HTTPException(403, "Platform administrator required")
        worker = control.get(AutomationWorker, worker_id)
        if not worker:
            raise HTTPException(404, "Worker not found")
        worker.active = False
        control.add(
            AccessAudit(
                actor=user.email,
                action="automation_worker_revoked",
                detail={"worker_id": str(worker.id)},
            )
        )
        control.commit()
        return {"revoked": True}


@router.get("/worker/health")
def health(request: Request):
    with ControlSession() as control:
        worker = worker_for(control, request.headers.get("X-API-Key", ""))
        worker.last_seen_at = datetime.now(timezone.utc)
        control.commit()
    return {"shared_automation_version": 1, "automation_metrics_version": 1}


@router.post("/worker/claim")
def claim(request: Request):
    with ControlSession() as control:
        worker = worker_for(control, request.headers.get("X-API-Key", ""))
        worker.last_seen_at = datetime.now(timezone.utc)
        control.execute(
            text(
                "SELECT pg_advisory_xact_lock(hashtextextended('shared-automation-claim',0))"
            )
        )
        now = datetime.now(timezone.utc)
        for stale in control.scalars(
            select(AutomationJob).where(
                AutomationJob.status == "RUNNING", AutomationJob.lease_expires_at < now
            )
        ):
            control.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                {"key": f"finish:{stale.id}"},
            )
            control.refresh(stale, with_for_update=True)
            if stale.status != "RUNNING":
                continue
            stale.status = "FAILED"
            stale.failure_reason = "WORKER_TIMEOUT"
            stale.finished_at = now
            if stale.kind == "SETUP":
                p = control.scalar(
                    select(ProductAutomationPlan).where(
                        ProductAutomationPlan.workspace_id == stale.workspace_id
                    )
                )
                p.state = "NEEDS_ATTENTION"
            principal = job_principal(stale)
            with SessionLocal(
                info={"workspace_id": stale.workspace_id, "principal": principal}
            ) as scoped:
                fail_native(scoped, stale, "WORKER_TIMEOUT")
                scoped.commit()
        control.flush()
        for p in control.scalars(
            select(ProductAutomationPlan)
            .join(Workspace, Workspace.id == ProductAutomationPlan.workspace_id)
            .where(
                Workspace.active.is_(True),
                ProductAutomationPlan.enabled.is_(True),
                ProductAutomationPlan.state == "ACTIVE",
                ProductAutomationPlan.next_discovery_at <= now,
            )
        ):
            pending = control.scalar(
                select(AutomationJob.id).where(
                    AutomationJob.workspace_id == p.workspace_id,
                    AutomationJob.kind == "DISCOVERY",
                    AutomationJob.status.in_(("PENDING", "RUNNING")),
                )
            )
            if not pending:
                control.add(
                    AutomationJob(
                        workspace_id=p.workspace_id,
                        kind="DISCOVERY",
                        payload={
                            "query": p.configuration["discovery_query"],
                            "target_new_companies": p.profile.get(
                                "daily_new_companies", 5
                            ),
                        },
                    )
                )
                p.next_discovery_at = now + timedelta(days=1)
        control.flush()
        busy = select(AutomationJob.workspace_id).where(
            AutomationJob.status == "RUNNING"
        )
        job = control.scalar(
            select(AutomationJob)
            .join(
                ProductAutomationPlan,
                ProductAutomationPlan.workspace_id == AutomationJob.workspace_id,
            )
            .join(Workspace, Workspace.id == AutomationJob.workspace_id)
            .where(
                AutomationJob.status == "PENDING",
                ProductAutomationPlan.enabled.is_(True),
                Workspace.active.is_(True),
                AutomationJob.workspace_id.not_in(busy),
            )
            .order_by(AutomationJob.created_at)
            .with_for_update(of=AutomationJob, skip_locked=True)
            .limit(1)
        )
        if not job:
            control.commit()
            return None
        proof = secrets.token_urlsafe(48)
        job.lease_hash = token_hash(proof)
        job.worker_id = worker.id
        job.status = "RUNNING"
        job.started_at = now
        job.lease_expires_at = now + timedelta(minutes=30)
        principal = job_principal(job)
        ctx = current_principal.set(principal)
        try:
            with SessionLocal(
                info={"workspace_id": job.workspace_id, "principal": principal}
            ) as scoped:
                inputs = prepare_claim(scoped, job, principal.actor)
                scoped.commit()
        except HTTPException:
            with SessionLocal(
                info={"workspace_id": job.workspace_id, "principal": principal}
            ) as scoped:
                fail_native(scoped, job, "STALE_JOB_CONTEXT")
                scoped.commit()
            job.status = "FAILED"
            job.failure_reason = "STALE_JOB_CONTEXT"
            job.finished_at = now
            control.commit()
            return None
        finally:
            current_principal.reset(ctx)
        control.commit()
        return {
            "job_id": str(job.id),
            "kind": job.kind,
            "workspace_id": str(job.workspace_id),
            "lease_token": proof,
            "input": {**inputs, "workspace_id": str(job.workspace_id), **job.payload},
        }


@router.post("/worker/finish")
def finish(data: Finish, request: Request):
    with ControlSession() as control:
        worker = worker_for(control, request.headers.get("X-API-Key", ""))
        control.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": f"finish:{data.job_id}"},
        )
        job = control.scalar(
            select(AutomationJob).where(AutomationJob.id == data.job_id)
        )
        if (
            not job
            or job.worker_id != worker.id
            or not secrets.compare_digest(
                job.lease_hash or "", token_hash(data.lease_token)
            )
        ):
            raise HTTPException(403, "Job ownership mismatch")
        if job.status in ("COMPLETED", "FAILED", "NEEDS_REVIEW"):
            return {"status": job.status}
        if job.status != "RUNNING" or job.lease_expires_at <= datetime.now(
            timezone.utc
        ):
            raise HTTPException(409, "Job lease expired")
        return finish_scoped(job, data)


def finish_scoped(job, data):
    workspace_id = job.workspace_id
    principal = job_principal(job)
    ctx = current_principal.set(principal)
    try:
        with SessionLocal(
            info={"workspace_id": workspace_id, "principal": principal}
        ) as scoped:
            owned = scoped.scalar(
                select(AutomationJob)
                .where(AutomationJob.id == data.job_id)
                .with_for_update()
            )
            if owned.status in ("COMPLETED", "FAILED", "NEEDS_REVIEW"):
                return {"status": owned.status}
            if data.usage is not None:
                from app.services.automation_metrics import usage_snapshot

                owned.usage = usage_snapshot(data.usage.model_dump())
            p = scoped.scalar(select(ProductAutomationPlan))
            if data.failure_reason or not p.enabled:
                owned.status = "FAILED"
                owned.failure_reason = data.failure_reason or "PRODUCT_PAUSED"
                fail_native(scoped, owned, owned.failure_reason)
                if owned.kind == "SETUP":
                    p.state = "NEEDS_ATTENTION"
            else:
                if owned.kind == "SETUP":
                    from pydantic import ValidationError

                    try:
                        config = SetupOutput.model_validate(data.output)
                    except ValidationError:
                        raise HTTPException(
                            422, "Invalid generated product targeting"
                        ) from None
                    for old in scoped.scalars(
                        select(ICPProfile).where(
                            ICPProfile.code.in_([f"AUTO_{n}" for n in range(1, 6)])
                        )
                    ):
                        old.active = False
                    for index, proposal in enumerate(config.icps):
                        code = f"AUTO_{index+1}"
                        icp = scoped.scalar(
                            select(ICPProfile).where(ICPProfile.code == code)
                        )
                        if not icp:
                            icp = ICPProfile(code=code, name=proposal.name)
                            scoped.add(icp)
                        icp.name = proposal.name
                        icp.description = proposal.description
                        icp.active = True
                        icp.qualification_rules = {
                            "fit_description": proposal.description
                        }
                    p.configuration = config.model_dump()
                    p.state = "ACTIVE"
                    p.next_discovery_at = datetime.now(timezone.utc)
                    with ControlSession() as settings_db:
                        w = settings_db.get(Workspace, workspace_id)
                        w.settings = {
                            **w.settings,
                            "description": p.profile["description"],
                            "brand_voice": p.profile["brand_voice"],
                            "country_code": p.profile["country_code"],
                            "language": p.profile["language"],
                        }
                        settings_db.commit()
                elif owned.kind == "DISCOVERY":
                    accepted = owned.result.get("accepted_leads", 0)
                    owned.result = {
                        **owned.result,
                        "accepted_leads": accepted,
                        "outcome": (
                            "COMPANIES_ACCEPTED"
                            if accepted
                            else "NO_NEW_SUITABLE_COMPANIES"
                        ),
                    }
                elif owned.kind == "RESEARCH":
                    after_research(scoped, owned)
                elif owned.kind in ("SCORING", "MATCHING", "DRAFTING"):
                    after_stage(scoped, owned)
                if owned.status == "RUNNING":
                    owned.status = "COMPLETED"
            owned.finished_at = datetime.now(timezone.utc)
            scoped.add(
                Event(
                    event_type="product_automation_job_finished",
                    entity_type="AUTOMATION_JOB",
                    entity_id=owned.id,
                    actor_type="SERVICE",
                    actor_id=principal.actor,
                    metadata_json={
                        "kind": owned.kind,
                        "status": owned.status,
                        "related_id": (
                            str(owned.related_id) if owned.related_id else None
                        ),
                        "failure_reason": owned.failure_reason,
                    },
                )
            )
            scoped.commit()
            return {"status": owned.status, "result": owned.result}
    finally:
        current_principal.reset(ctx)
