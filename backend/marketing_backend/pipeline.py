"""Durable stage transitions. Business results and next jobs share one transaction."""

import hashlib, json
from urllib.parse import urlsplit
from datetime import timedelta
from sqlalchemy import select
from .models import (
    Workspace,
    Catalog,
    Lead,
    Job,
    PreparationRun,
    DiscoveryMemory,
    Approval,
    now,
)
from .research import ProviderFailure

STAGES = ("RESEARCH", "CONTACT_SEARCH", "SCORING", "MATCHING", "DRAFTING")


def domain(url):
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    return host.removeprefix("www.")


def context(db, wid, lead_id=None):
    workspace = db.get(Workspace, wid)
    catalog = [
        dict(
            kind=c.kind,
            code=c.code,
            name=c.name,
            description=c.description,
            rules=c.rules,
        )
        for c in db.scalars(
            select(Catalog)
            .where(Catalog.workspace_id == wid, Catalog.active.is_(True))
            .order_by(Catalog.kind, Catalog.code)
        )
    ]
    snapshot = {"catalog": catalog, "preferences": workspace.automation}
    if lead_id:
        lead = db.scalar(
            select(Lead).where(Lead.workspace_id == wid, Lead.id == lead_id)
        )
        if not lead:
            raise ProviderFailure("LEAD_NOT_FOUND")
        snapshot["company"] = {
            "id": str(lead.id),
            "company_name": lead.company_name,
            "website": lead.website,
        }
    return snapshot


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def start(db, lead, key, icp_code=None):
    snapshot = context(db, lead.workspace_id, lead.id)
    if not any(c["kind"] == "PRODUCT" for c in snapshot["catalog"]) or not any(
        c["kind"] == "ICP" for c in snapshot["catalog"]
    ):
        raise ProviderFailure("CATALOG_NOT_READY")
    icps = [c["code"] for c in snapshot["catalog"] if c["kind"] == "ICP"]
    icp_code = icp_code or icps[0]
    if icp_code not in icps:
        raise ProviderFailure("ICP_NOT_SUPPORTED")
    run = PreparationRun(
        workspace_id=lead.workspace_id,
        lead_id=lead.id,
        context_hash=fingerprint(snapshot),
        snapshot=snapshot,
    )
    db.add(run)
    db.flush()
    db.add(
        Job(
            workspace_id=lead.workspace_id,
            lead_id=lead.id,
            run_id=run.id,
            managed=True,
            kind="RESEARCH",
            idempotency_key=key,
            payload={
                "company_name": lead.company_name,
                "website": lead.website,
                "context": snapshot,
                "context_hash": run.context_hash,
                "icp_code": icp_code,
            },
        )
    )
    return run


def valid_context(db, job):
    if (
        job.managed
        and fingerprint(context(db, job.workspace_id, job.lead_id))
        != job.payload["context_hash"]
    ):
        raise ProviderFailure("CONTEXT_CHANGED")


def next_job(db, job, kind):
    db.add(
        Job(
            workspace_id=job.workspace_id,
            lead_id=job.lead_id,
            run_id=job.run_id,
            managed=True,
            kind=kind,
            idempotency_key=f"{job.run_id}:{kind}",
            payload=job.payload,
        )
    )


def finalize(db, job, result):
    valid_context(db, job)
    if job.kind == "SETUP":
        for item in result["icps"]:
            if not db.scalar(
                select(Catalog.id).where(
                    Catalog.workspace_id == job.workspace_id,
                    Catalog.kind == "ICP",
                    Catalog.code == item["code"],
                )
            ):
                db.add(Catalog(workspace_id=job.workspace_id, kind="ICP", **item))
        db.flush()
        workspace = db.get(Workspace, job.workspace_id)
        workspace.automation = {
            **workspace.automation,
            "discovery_query": result["discovery_query"],
        }
        workspace.next_discovery_at = now()
        return
    if job.kind == "DISCOVERY":
        for item in result["candidates"]:
            host = domain(item["website"])
            # Concurrent discovery commits lock this workspace in queue.owned().
            if db.scalar(
                select(DiscoveryMemory.id).where(
                    DiscoveryMemory.workspace_id == job.workspace_id,
                    DiscoveryMemory.domain == host,
                )
            ):
                continue
            known = any(
                domain(l.website) == host
                for l in db.scalars(
                    select(Lead).where(Lead.workspace_id == job.workspace_id)
                )
            )
            db.add(
                DiscoveryMemory(
                    workspace_id=job.workspace_id,
                    domain=host,
                    candidate=item,
                    outcome="KNOWN" if known else "ACCEPTED",
                )
            )
            if not known:
                lead = Lead(
                    workspace_id=job.workspace_id,
                    company_name=item["company_name"],
                    website=item["website"],
                )
                db.add(lead)
                db.flush()
                start(db, lead, f"{job.id}:{host}:RESEARCH", item["icp_code"])
        db.flush()
        for item in result.get("evaluated_domains", []):
            if not db.scalar(
                select(DiscoveryMemory.id).where(
                    DiscoveryMemory.workspace_id == job.workspace_id,
                    DiscoveryMemory.domain == item["domain"],
                )
            ):
                db.add(
                    DiscoveryMemory(
                        workspace_id=job.workspace_id,
                        domain=item["domain"],
                        candidate=item,
                        outcome="REVIEW_REQUIRED",
                    )
                )
        return
    run = db.scalar(
        select(PreparationRun)
        .where(
            PreparationRun.id == job.run_id,
            PreparationRun.workspace_id == job.workspace_id,
        )
        .with_for_update()
    )
    if run.status != "PREPARING":
        raise ProviderFailure("RUN_NOT_ACTIVE")
    run.results = {**run.results, job.kind: result}
    reason = result.get("stop_reason")
    if reason:
        run.status, run.stop_reason = "NEEDS_REVIEW", reason
        job.status, job.failure_code = "NEEDS_REVIEW", reason
    elif job.kind == "DRAFTING":
        run.status = "PENDING_APPROVAL"
        db.add(
            Approval(
                workspace_id=job.workspace_id,
                run_id=run.id,
                snapshot={
                    "context_hash": run.context_hash,
                    "inputs": run.snapshot,
                    "results": run.results,
                    "draft": result,
                },
                status="PENDING",
            )
        )
    else:
        next_job(db, job, STAGES[STAGES.index(job.kind) + 1])


def schedule(db):
    for workspace in db.scalars(
        select(Workspace)
        .where(
            Workspace.active.is_(True),
            Workspace.automation_enabled.is_(True),
            Workspace.next_discovery_at <= now(),
        )
        .with_for_update(skip_locked=True)
    ):
        active = db.scalar(
            select(Job.id).where(
                Job.workspace_id == workspace.id,
                Job.managed.is_(True),
                Job.lead_id.is_(None),
                Job.status.in_(["PENDING", "RUNNING"]),
            )
        )
        if active:
            continue
        snapshot = context(db, workspace.id)
        stamp = workspace.next_discovery_at.isoformat()
        db.add(
            Job(
                workspace_id=workspace.id,
                kind="DISCOVERY",
                managed=True,
                idempotency_key="daily:" + stamp,
                payload={"context": snapshot, "context_hash": fingerprint(snapshot)},
            )
        )
        workspace.next_discovery_at = now() + timedelta(days=1)
    db.commit()
