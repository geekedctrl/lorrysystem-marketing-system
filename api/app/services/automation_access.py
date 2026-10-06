"""Only the dispatcher sees global queue metadata; job leases scope business access."""

from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select
from app.db.session import ControlSession
from app.models.automation import AutomationWorker, AutomationJob, ProductAutomationPlan
from app.models.workspaces import Workspace
from app.workspace_context import Principal


def worker_for(db, key):
    from app.auth import token_hash

    if not key or len(key) > 512 or not key.isascii():
        raise HTTPException(401, "Invalid worker credential")
    worker = db.scalar(
        select(AutomationWorker).where(
            AutomationWorker.token_hash == token_hash(key),
            AutomationWorker.active.is_(True),
        )
    )
    if not worker:
        raise HTTPException(401, "Invalid worker credential")
    return worker


def job_principal(job):
    return Principal(
        job.workspace_id,
        f"service:shared-job:{job.id}",
        "SERVICE",
        automation_job_id=job.id,
    )


def lease_principal(request):
    from app.auth import token_hash

    proof = request.headers.get("X-Automation-Lease", "")
    if not proof or len(proof) > 512 or not proof.isascii():
        raise HTTPException(401, "Invalid job lease")
    with ControlSession() as db:
        worker = worker_for(db, request.headers.get("X-API-Key", ""))
        job = db.scalar(
            select(AutomationJob).where(AutomationJob.lease_hash == token_hash(proof))
        )
        if (
            not job
            or job.worker_id != worker.id
            or job.status != "RUNNING"
            or job.lease_expires_at <= datetime.now(timezone.utc)
        ):
            raise HTTPException(401, "Job lease is expired or unavailable")
        workspace = db.get(Workspace, job.workspace_id)
        plan = db.scalar(
            select(ProductAutomationPlan).where(
                ProductAutomationPlan.workspace_id == job.workspace_id
            )
        )
        if not workspace or not workspace.active or not plan or not plan.enabled:
            raise HTTPException(403, "Product automation is paused")
        if request.headers.get("X-Workspace-ID") != str(job.workspace_id):
            raise HTTPException(403, "Job lease is restricted to its workspace")
        path, method = request.url.path, request.method
        allowed = {
            ("GET", "/api/workspace-context"),
            ("GET", "/api/automation/job-context"),
        }
        related = str(job.related_id)
        if job.kind == "DISCOVERY":
            allowed |= {
                ("GET", "/api/automation/memory"),
                ("POST", "/api/automation/candidates"),
                ("POST", "/api/research/fetch-public"),
            }
        elif job.kind == "RESEARCH":
            allowed |= {
                ("GET", f"/api/research/{related}/context"),
                ("POST", "/api/research/fetch-public"),
                ("POST", f"/api/research/{related}/sources"),
            }
            allowed |= {
                ("PATCH", f"/api/research/{related}/{suffix}")
                for suffix in ("complete", "partial", "fail")
            }
        elif job.kind in ("SCORING", "MATCHING", "DRAFTING"):
            allowed |= {
                ("GET", f"/api/pipeline/{related}/context"),
                ("PATCH", f"/api/pipeline/{related}/complete"),
                ("PATCH", f"/api/pipeline/{related}/fail"),
            }
        if (method, path) not in allowed:
            raise HTTPException(403, "This operation is outside the claimed job")
        return job_principal(job)
