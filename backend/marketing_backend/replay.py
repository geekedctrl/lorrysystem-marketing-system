"""Explicit same-job replay. No contract adaptation or historical data erasure."""
from sqlalchemy import select
from .models import Job, JobReplay, Membership, Workspace, StageArtifact, PreparationRun, now
from .stage_contracts import content_hash
from .worker_contracts import record, validate_task, IMPLEMENTATION
from .ownership import active_python, capability_for_job


class ReplayConflict(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def replay(db, workspace_id, job_id, actor_id, key):
    membership = db.get(Membership, (workspace_id, actor_id))
    if not membership or membership.role not in ("ADMIN", "OPERATOR"):
        raise ReplayConflict("REPLAY_PERMISSION_REQUIRED")
    job = db.scalar(select(Job).where(Job.workspace_id == workspace_id, Job.id == job_id).with_for_update())
    if not job:
        raise ReplayConflict("JOB_NOT_FOUND")
    previous = db.scalar(select(JobReplay).where(
        JobReplay.workspace_id == workspace_id, JobReplay.job_id == job_id,
        JobReplay.idempotency_key == key,
    ))
    if previous:
        return previous, True
    if job.status != "QUARANTINED":
        raise ReplayConflict("ONLY_QUARANTINED_JOBS_CAN_REPLAY")
    if job.replay_generation >= 3:
        raise ReplayConflict("REPLAY_LIMIT_REACHED")
    if job.task_envelope is None:
        raise ReplayConflict("REPLAY_REQUIRES_VERSIONED_TASK")
    if (job.quarantined_task_hash != content_hash(job.task_envelope)
            or job.quarantined_input_hash != content_hash(job.payload)):
        raise ReplayConflict("REPLAY_INPUT_CHANGED")
    workspace = db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    from .product_lines import line_mode, line_for
    if (not workspace or not workspace.active or (job.managed and
            (line_for(db,workspace_id,job.product_line_id).paused if line_mode(job) else not workspace.automation_enabled))
            or not active_python(db, workspace_id, capability_for_job(job.kind))):
        raise ReplayConflict("REPLAY_EXECUTION_DISABLED")
    # Validating again is mandatory: registering/deploying a compatible consumer
    # is not equivalent to accepting the original malformed data blindly.
    validate_task(db, job)
    if job.managed:
        from .pipeline import valid_context
        from .research import ProviderFailure
        try:
            valid_context(db, job)
        except ProviderFailure:
            raise ReplayConflict("STALE_CONTEXT") from None
    if db.scalar(select(StageArtifact.id).where(StageArtifact.job_id == job.id).limit(1)):
        raise ReplayConflict("REPLAY_HAS_COMMITTED_ARTIFACTS")
    competing = select(Job.id).where(
        Job.workspace_id == workspace_id, Job.id != job.id,
        Job.status.in_(["PENDING", "RUNNING"]),
    )
    if job.lead_id:
        competing = competing.where(Job.lead_id == job.lead_id)
    else:
        competing = competing.where(Job.lead_id.is_(None), Job.kind == job.kind)
    if db.scalar(competing.limit(1)):
        raise ReplayConflict("ANOTHER_JOB_IS_ACTIVE")
    event = record(db, job, "REPLAY", actor_id=actor_id)
    row = JobReplay(workspace_id=workspace_id, product_line_id=job.product_line_id,
        job_id=job.id, event_id=event.id, actor_id=actor_id, idempotency_key=key,
        generation=job.replay_generation+1, previous_attempts=job.attempts,
        envelope_hash=job.quarantined_task_hash, input_hash=job.quarantined_input_hash,
        consumer_version=IMPLEMENTATION)
    db.add(row)
    # Reopen only execution state. Prior artifacts, reviews and approvals remain.
    job.status = "PENDING"
    job.replay_generation += 1
    job.attempts = 0
    job.failure_code = job.quarantine_reason = None
    job.quarantined_task_hash = job.quarantined_input_hash = None
    job.lease_token = job.lease_until = None
    job.available_at = now()
    job.checkpoint = {k: v for k, v in job.checkpoint.items() if not k.startswith("model:")}
    job.history = [*job.history, {"code": "AUDITED_REPLAY", "generation": job.replay_generation, "at": now().isoformat()}]
    if job.run_id:
        run = db.get(PreparationRun, job.run_id)
        if run.status != "NEEDS_REVIEW" or run.stop_reason != "CONTRACT_QUARANTINED":
            raise ReplayConflict("RUN_NOT_QUARANTINED")
        run.status, run.stop_reason = "PREPARING", None
    db.flush()
    return row, False
