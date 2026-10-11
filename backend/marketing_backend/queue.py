import secrets
from datetime import timedelta
from sqlalchemy import select
from .models import Job, Workspace, now

LEASE_SECONDS = 180


class LeaseLost(Exception):
    pass


def claim(db):
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
    db.flush()
    job = db.scalar(
        select(Job)
        .join(Workspace, Workspace.id == Job.workspace_id)
        .where(
            Job.status == "PENDING",
            Job.available_at <= instant,
            Workspace.active.is_(True),
        )
        .order_by(Job.created_at, Job.id)
        .with_for_update(of=Job, skip_locked=True)
        .limit(1)
    )
    if job:
        job.status = "RUNNING"
        job.attempts += 1
        job.lease_token = secrets.token_hex(32)
        job.lease_until = instant + timedelta(seconds=LEASE_SECONDS)
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
    workspace = db.get(Workspace, job.workspace_id)
    if not workspace or not workspace.active:
        raise LeaseLost()
    return job


def checkpoint(db, job_id, token, value):
    job = owned(db, job_id, token)
    job.checkpoint = value
    job.lease_until = now() + timedelta(seconds=LEASE_SECONDS)
    db.commit()


def complete(db, job_id, token, result, review=False):
    job = owned(db, job_id, token)
    job.result = result
    job.status = "NEEDS_REVIEW" if review else "COMPLETED"
    job.failure_code = "CONTACT_REVIEW_REQUIRED" if review else None
    job.lease_token = job.lease_until = None
    db.commit()


def fail(db, job_id, token, code, retryable=False):
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
    db.commit()


def heartbeat(db, job_id, token):
    job = owned(db, job_id, token)
    job.lease_until = now() + timedelta(seconds=LEASE_SECONDS)
    db.commit()
