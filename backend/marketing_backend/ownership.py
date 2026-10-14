"""Native PostgreSQL is the only executor authority."""
import os
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import select, func
from .models import ExecutorOwnership, Job, DeliveryAttempt, now

CAPABILITIES = ("SETUP", "DISCOVERY", "PREPARATION", "SENDING")


def capability_for_job(kind):
    return kind if kind in ("SETUP", "DISCOVERY") else "PREPARATION"


def active_python(db, workspace_id, capability):
    row = db.get(ExecutorOwnership, (workspace_id, capability))
    return bool(row and row.owner == "PYTHON" and row.state == "ACTIVE")


def active_leases(db, workspace_id, capability):
    if capability == "SENDING":
        return db.scalar(select(func.count()).select_from(DeliveryAttempt).where(
            DeliveryAttempt.workspace_id == workspace_id,
            DeliveryAttempt.status == "SENDING", DeliveryAttempt.lease_until > now())) or 0
    kinds = [capability] if capability in ("SETUP", "DISCOVERY") else [
        "RESEARCH", "CONTACT_SEARCH", "SCORING", "MATCHING", "DRAFTING"]
    return db.scalar(select(func.count()).select_from(Job).where(
        Job.workspace_id == workspace_id, Job.kind.in_(kinds),
        Job.status == "RUNNING", Job.lease_until > now())) or 0


def transition(db, workspace_id, capability, action, expected_version, actor_id):
    if capability not in CAPABILITIES:
        raise HTTPException(404, "Unknown capability")
    row = db.scalar(select(ExecutorOwnership).where(
        ExecutorOwnership.workspace_id == workspace_id,
        ExecutorOwnership.capability == capability).with_for_update())
    if row is None:
        raise HTTPException(503, "Ownership authority incomplete")
    if row.version != expected_version:
        raise HTTPException(409, "Ownership version changed")
    allowed = {
        "drain": ("N8N", "ACTIVE", "N8N", "DRAINING"),
        "activate-python": ("N8N", "DRAINING", "PYTHON", "ACTIVE"),
        "rollback-n8n": ("PYTHON", "ACTIVE", "N8N", "ACTIVE"),
    }
    if action not in allowed:
        raise HTTPException(404, "Unknown transition")
    before_owner, before_state, owner, state = allowed[action]
    if (row.owner, row.state) != (before_owner, before_state):
        raise HTTPException(409, "Invalid ownership transition")
    if action == "rollback-n8n" and row.rollback_deadline and row.rollback_deadline < now():
        raise HTTPException(409, "Rollback window has expired")
    if action != "drain" and active_leases(db, workspace_id, capability):
        raise HTTPException(409, "Active leases must drain first")
    if action == "activate-python":
        if os.environ.get("OWNERSHIP_CUTOVER_READY") != "true":
            raise HTTPException(409, "Legacy claim preflight has not been certified")
        from .migration import unresolved_differences
        if unresolved_differences(db):
            raise HTTPException(409, "Migration reconciliation has unexplained differences")
    row.owner, row.state, row.version = owner, state, row.version + 1
    row.actor_id, row.changed_at = actor_id, now()
    row.rollback_deadline = now() + timedelta(days=14) if owner == "PYTHON" else None
    from sqlalchemy import text
    db.execute(text("""INSERT INTO executor_ownership_events
      (workspace_id,capability,prior_owner,prior_state,owner,state,version,actor_id)
      VALUES (:wid,:cap,:old_owner,:old_state,:owner,:state,:version,:actor)"""),
      dict(wid=workspace_id,cap=capability,old_owner=before_owner,
           old_state=before_state,owner=owner,state=state,version=row.version,actor=actor_id))
    db.commit()
    return row
