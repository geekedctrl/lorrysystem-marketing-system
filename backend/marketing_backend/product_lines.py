"""Line-owned snapshots and producer commands; old/default snapshots stay intact."""
from uuid import UUID
from sqlalchemy import select
from .models import ProductLine, Catalog, Job, StageArtifact, Workspace, PreparationRun, now
from .research import ProviderFailure
from .stage_contracts import STAGE_CONTRACTS, content_hash, validate_envelope


def default_id(db, wid):
    return db.scalar(select(ProductLine.id).where(ProductLine.workspace_id == wid, ProductLine.code == "DEFAULT"))


def default_expr(wid):
    return select(ProductLine.id).where(ProductLine.workspace_id == wid, ProductLine.code == "DEFAULT").scalar_subquery()


def line_for(db, wid, lid, *, lock=False):
    query = select(ProductLine).where(ProductLine.workspace_id == wid, ProductLine.id == lid)
    line = db.scalar((query.with_for_update() if lock else query).execution_options(populate_existing=True))
    if not line:
        raise ProviderFailure("PRODUCT_LINE_NOT_FOUND")
    return line


def line_mode(job):
    return isinstance(job.payload, dict) and job.payload.get("product_line_id") is not None


def for_run(db, run):
    from .pipeline import context
    return context(db, run.workspace_id, run.lead_id,
                   run.product_line_id if run.snapshot.get("product_line") else None)


def enabled(db, run):
    return not line_for(db, run.workspace_id, run.product_line_id).paused if run.snapshot.get("product_line") else db.get(Workspace, run.workspace_id).automation_enabled


def scoped_key(line, key):
    return key if line.code == "DEFAULT" else f"line:{line.id}:{content_hash(key)}"


def bind_task(db, job):
    """Bind newly produced line work to immutable input hashes and artifact refs."""
    db.flush()
    line = line_for(db, job.workspace_id, job.product_line_id)
    db.refresh(line)
    refs = []
    if job.payload.get("source_candidate_id"):
        from .models import DiscoveryMemory
        candidate=db.get(DiscoveryMemory,UUID(job.payload["source_candidate_id"]))
        row=db.scalar(select(StageArtifact).where(StageArtifact.job_id==candidate.source_job_id,
            StageArtifact.artifact_key=="candidate:"+content_hash(candidate.domain))) if candidate else None
        if row:refs.append(dict(artifact_id=str(row.id),contract_name=row.contract_name,schema_version=row.schema_version,content_hash=row.content_hash))
    if job.run_id:
        rows = db.scalars(select(StageArtifact).join(Job, Job.id == StageArtifact.job_id).where(
            Job.run_id == job.run_id, StageArtifact.product_line_id == line.id,
            StageArtifact.artifact_key.startswith("result"),
        ).order_by(StageArtifact.created_at.desc(), StageArtifact.id.desc()))
        seen = set()
        for row in rows:
            if row.job_id not in seen:
                seen.add(row.job_id)
                refs.append(dict(artifact_id=str(row.id), contract_name=row.contract_name,
                                 schema_version=row.schema_version, content_hash=row.content_hash))
    job.task_envelope = dict(workspace_id=str(job.workspace_id), product_line_id=str(line.id),
        candidate_id=job.payload.get("source_candidate_id"),
        job_id=str(job.id), lead_id=str(job.lead_id) if job.lead_id else None,
        stage=job.kind, idempotency_key=job.idempotency_key, trace_id=str(job.trace_id),
        contract_name=STAGE_CONTRACTS[job.kind], schema_version=2, producer_version="native.day1.1",
        context_version=line.context_version, context_hash=line.context_hash,
        input_hash=content_hash(job.payload), attempt=0, max_attempts=job.max_attempts, prior_artifacts=refs)
    validate_envelope(job.task_envelope)
    db.flush()
    return job


def enqueue(db, line, kind, key):
    from .pipeline import context, fingerprint
    key = scoped_key(line, key)
    prior = db.scalar(select(Job).where(Job.workspace_id == line.workspace_id, Job.idempotency_key == key))
    if prior:
        if prior.product_line_id != line.id or prior.kind != kind:
            raise ProviderFailure("IDEMPOTENCY_CONFLICT")
        return prior
    if line.paused:
        raise ProviderFailure("PRODUCT_LINE_PAUSED")
    if db.scalar(select(Job.id).where(Job.product_line_id == line.id, Job.lead_id.is_(None), Job.status.in_(["PENDING", "RUNNING"]))):
        raise ProviderFailure("PRODUCT_LINE_BUSY")
    snapshot = context(db, line.workspace_id, product_line_id=line.id)
    job = Job(workspace_id=line.workspace_id, product_line_id=line.id, managed=True, kind=kind,
              idempotency_key=key, payload=dict(product_line_id=str(line.id), context=snapshot, context_hash=fingerprint(snapshot)))
    db.add(job)
    return bind_task(db, job)


def invalidate(db, line):
    """Invalidate execution/readiness without rewriting human decisions or assets."""
    for job in db.scalars(select(Job).where(Job.product_line_id == line.id, Job.status.in_(["PENDING", "RUNNING"])).with_for_update()):
        job.status, job.failure_code = "FAILED", "CONTEXT_CHANGED"
        job.lease_token = job.lease_until = None
        job.history = [*job.history, {"code": "CONTEXT_CHANGED", "at": now().isoformat()}]
        from .worker_contracts import record
        record(db, job, "FAILURE", "STALE_CONTEXT")
    for run in db.scalars(select(PreparationRun).where(PreparationRun.product_line_id == line.id,
        PreparationRun.status.in_(["PREPARING", "PENDING_APPROVAL", "NEEDS_REVIEW"])).with_for_update()):
        run.status, run.stop_reason = "STALE", "CONTEXT_CHANGED"


def mutation_lock(db, wid, lid):
    # Same order as worker completion: jobs, workspace, product line.
    list(db.scalars(select(Job).where(Job.workspace_id == wid, Job.product_line_id == lid).order_by(Job.id).with_for_update()))
    db.scalar(select(Workspace).where(Workspace.id == wid).with_for_update())
    return line_for(db, wid, lid, lock=True)


def mirror_default(db, line):
    if line.code == "DEFAULT":
        workspace = db.get(Workspace, line.workspace_id)
        workspace.automation, workspace.automation_enabled = dict(line.settings), not line.paused
        workspace.next_discovery_at = line.next_discovery_at
