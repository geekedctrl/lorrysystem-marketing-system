import secrets
from datetime import timedelta
from sqlalchemy import select, or_, and_, case, func, Integer
from sqlalchemy.orm import aliased
from .models import Job, Workspace, ExecutorOwnership, ProductLine, now
from .ownership import capability_for_job, active_python

LEASE_SECONDS = 180


class LeaseLost(Exception):
    pass


def recover_expired(db):
    """Scheduler-only recovery; claims never recover unrelated pool work."""
    instant = now()
    expired = list(
        db.scalars(
            select(Job)
            .where(Job.status == "RUNNING", Job.lease_until <= instant)
            .with_for_update(skip_locked=True)
        )
    )
    for job in expired:
        job.history = [
            *job.history,
            {
                "attempt": job.attempts,
                "code": "LEASE_EXPIRED",
                "at": instant.isoformat(),
            },
        ]
        job.failure_code = "LEASE_EXPIRED"
        job.status = "FAILED" if job.attempts >= job.max_attempts else "PENDING"
        job.available_at = instant + timedelta(seconds=min(300, 2**job.attempts))
        job.lease_token = job.lease_until = None
        from .worker_contracts import record
        record(db, job, "LEASE_LOSS", "LEASE_EXPIRED")
        record(db, job, "FAILURE" if job.status == "FAILED" else "RETRY", "LEASE_EXPIRED")
        if job.run_id and job.status == "FAILED":
            from .models import PreparationRun

            run = db.get(PreparationRun, job.run_id)
            run.status, run.stop_reason = "FAILED", "LEASE_EXPIRED"
    db.commit()
    return len(expired)


def claim(db, pool=None):
    from .pools import get_pool, STAGES
    stages = STAGES if pool is None else get_pool(pool).stages
    if not stages:
        raise ValueError("A stage pool is required for job claims")
    instant = now()
    running = aliased(Job)
    count = select(func.count()).where(running.product_line_id == Job.product_line_id,
        running.kind == Job.kind, running.status == "RUNNING").correlate(Job).scalar_subquery()
    job = db.scalar(
        select(Job)
        .join(Workspace, Workspace.id == Job.workspace_id)
        .join(ProductLine, ProductLine.id == Job.product_line_id)
        .join(ExecutorOwnership, (ExecutorOwnership.workspace_id == Job.workspace_id) &
              (ExecutorOwnership.capability == case(
                  (Job.kind == 'SETUP', 'SETUP'), (Job.kind == 'DISCOVERY', 'DISCOVERY'),
                  else_='PREPARATION')))
        .where(
            Job.kind.in_(stages),
            Job.status == "PENDING",
            Job.available_at <= instant,
            Workspace.active.is_(True),
            or_(Job.managed.is_(False),
                and_(Job.payload.has_key("product_line_id"), ProductLine.paused.is_(False)),
                and_(~Job.payload.has_key("product_line_id"), Workspace.automation_enabled.is_(True))),
            count < func.coalesce(ProductLine.limits["per_pool_concurrency"].astext.cast(Integer),1),
            ExecutorOwnership.owner == 'PYTHON', ExecutorOwnership.state == 'ACTIVE',
        )
        .order_by(Job.created_at, Job.id)
        # Lock the claimable job; ownership is read-only for workers and must
        # not grant them transition privileges merely to inspect it.
        .with_for_update(of=Job, skip_locked=True)
        .limit(1)
    )
    if job:
        from sqlalchemy import text
        # Recheck after the advisory lock to close the concurrent-claim race.
        key = str(job.product_line_id)+":"+job.kind
        if not db.scalar(text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key,0))"), {"key": key}):
            db.commit()
            return None
        active = db.scalar(select(func.count()).select_from(Job).where(Job.product_line_id == job.product_line_id,
            Job.kind == job.kind, Job.status == "RUNNING"))
        limit = db.get(ProductLine, job.product_line_id).limits.get("per_pool_concurrency",1)
        if active >= limit:
            db.commit()
            return None
        job.status = "RUNNING"
        job.attempts += 1
        job.lease_token = secrets.token_hex(32)
        job.lease_until = instant + timedelta(seconds=LEASE_SECONDS)
        job.history = [
            *job.history,
            {
                "code": "STAGE_STARTED",
                "attempt": job.attempts,
                "at": instant.isoformat(),
            },
        ]
        from .worker_contracts import record
        record(db, job, "CLAIM")
    db.commit()
    return job


def owned(db, job_id, token):
    job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
    if (
        not job
        or job.status != "RUNNING"
        or job.lease_token != token
        or job.lease_until <= now()
    ):
        raise LeaseLost()
    workspace = db.scalar(
        select(Workspace).where(Workspace.id == job.workspace_id).with_for_update()
    )
    if (
        not workspace
        or not workspace.active
        or (job.managed and (db.get(ProductLine, job.product_line_id).paused
            if job.payload.get("product_line_id") else not workspace.automation_enabled))
        or not active_python(db, job.workspace_id, capability_for_job(job.kind))
    ):
        raise LeaseLost()
    return job


def checkpoint(db, job_id, token, value):
    job = owned(db, job_id, token)
    job.checkpoint = value
    job.lease_until = now() + timedelta(seconds=LEASE_SECONDS)
    from .worker_contracts import record
    record(db, job, "CHECKPOINT")
    db.commit()


def complete(db, job_id, token, result, review=False, duration_ms=None):
    job = owned(db, job_id, token)
    from .worker_contracts import record, store_output
    result = store_output(db, job, result)
    job.result = result
    job.status = "NEEDS_REVIEW" if review else "COMPLETED"
    job.failure_code = "CONTACT_REVIEW_REQUIRED" if review else None
    job.lease_token = job.lease_until = None
    if job.managed:
        from .pipeline import finalize

        db.flush()
        finalize(db, job, result)
    job.history = [*job.history, {"code": "STAGE_COMPLETED", "at": now().isoformat()}]
    record(db, job, "COMPLETION", duration_ms=duration_ms)
    db.commit()


def fail(db, job_id, token, code, retryable=False, duration_ms=None):
    job = owned(db, job_id, token)
    job.history = [
        *job.history,
        {"attempt": job.attempts, "code": code, "at": now().isoformat()},
    ]
    job.failure_code = code
    job.status = (
        "PENDING" if retryable and job.attempts < job.max_attempts else "FAILED"
    )
    job.available_at = now() + timedelta(seconds=min(300, 2**job.attempts))
    job.lease_token = job.lease_until = None
    if job.run_id and job.status == "FAILED":
        from .models import PreparationRun

        run = db.get(PreparationRun, job.run_id)
        run.status, run.stop_reason = "FAILED", code
    from .worker_contracts import record
    record(db, job, "RETRY" if job.status == "PENDING" else "FAILURE", code, duration_ms)
    db.commit()


def quarantine(db, job_id, token, code, duration_ms=None):
    from .diagnostics import classify
    from .stage_contracts import content_hash
    from .worker_contracts import record

    job = owned(db, job_id, token)
    failure = classify(code)
    # Store only known stable codes, never the exception message or payload.
    job.failure_code = job.quarantine_reason = failure.code
    job.quarantined_task_hash = content_hash(job.task_envelope)
    job.quarantined_input_hash = content_hash(job.payload)
    job.status = "QUARANTINED"
    job.lease_token = job.lease_until = None
    job.history = [*job.history, {"code": "CONTRACT_QUARANTINED", "at": now().isoformat()}]
    if job.run_id:
        from .models import PreparationRun
        run = db.get(PreparationRun, job.run_id)
        if run.status == "PREPARING":
            run.status, run.stop_reason = (
                ("STALE", "CONTEXT_CHANGED") if failure.code == "STALE_CONTEXT"
                else ("NEEDS_REVIEW", "CONTRACT_QUARANTINED")
            )
    record(db, job, "QUARANTINE", failure.code, duration_ms)
    db.commit()


def heartbeat(db, job_id, token):
    job = owned(db, job_id, token)
    job.lease_until = now() + timedelta(seconds=LEASE_SECONDS)
    db.commit()
