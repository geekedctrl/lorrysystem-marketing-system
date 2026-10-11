"""One catalog mutation policy for edits and soft lifecycle changes."""

from fastapi import HTTPException
from sqlalchemy import select
from .models import Job, Workspace, PreparationRun, Catalog, now


def lock_catalog_change(db, wid, *, kind=None, code=None, cid=None, desired=None):
    pending = list(
        db.scalars(
            select(Job)
            .where(
                Job.workspace_id == wid,
                Job.managed.is_(True),
                Job.status.in_(["PENDING", "RUNNING"]),
            )
            .with_for_update()
        )
    )
    workspace = db.scalar(
        select(Workspace).where(Workspace.id == wid).with_for_update()
    )
    filters = [Catalog.workspace_id == wid]
    filters += (
        [Catalog.id == cid] if cid else [Catalog.kind == kind, Catalog.code == code]
    )
    item = db.scalar(select(Catalog).where(*filters).with_for_update())
    if item and desired and all(getattr(item, k) == v for k, v in desired.items()):
        return item
    if pending and workspace.automation_enabled:
        raise HTTPException(
            409, "Pause or finish preparation before changing the catalog"
        )
    for job in pending:
        job.status, job.failure_code = "FAILED", "CATALOG_CHANGED"
        job.lease_token = job.lease_until = None
        job.history = [
            *job.history,
            {"code": "CATALOG_CHANGED", "at": now().isoformat()},
        ]
        if job.run_id:
            run = db.get(PreparationRun, job.run_id)
            run.status, run.stop_reason = "FAILED", "CATALOG_CHANGED"
    return item
