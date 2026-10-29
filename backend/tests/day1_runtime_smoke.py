"""Actual restricted API/worker smoke: synthetic identities, empty provider keys."""
import os,secrets,time
from uuid import UUID
import httpx
from sqlalchemy import select,delete
from marketing_backend.db import Session,engine
from marketing_backend.models import (User,Organization,Workspace,Membership,OrganizationMembership,ExecutorOwnership,
    JobReplay,StageEvent,StageArtifact,CompanyEvidence,ProviderUsage,DiscoveryMemory,Job,Approval,PreparationRun,
    DeliveryAttempt,Delivery,Lead,Catalog,ProductLine,LoginSession)
from marketing_backend.auth import hash_password

if os.getenv("APP_ENV")!="local-smoke" or engine.url.database!="marketing_rebuild":
    raise RuntimeError("Use only the isolated compose smoke service")
password=secrets.token_urlsafe(24);email="day1-smoke-"+secrets.token_hex(8)+"@example.test"
with Session() as db:
    actor=User(email=email,password_hash=hash_password(password));org=Organization(name="DAY1 SYNTHETIC SMOKE")
    db.add_all([actor,org]);db.flush()
    workspace=Workspace(organization_id=org.id,name="DAY1 SYNTHETIC SMOKE");db.add(workspace);db.flush()
    uid,wid,oid=actor.id,workspace.id,org.id
    db.add_all([Membership(user_id=uid,workspace_id=wid,role="ADMIN"),OrganizationMembership(user_id=uid,organization_id=oid,role="OWNER")])
    db.query(ExecutorOwnership).filter(ExecutorOwnership.workspace_id==wid).update({ExecutorOwnership.owner:"PYTHON"},synchronize_session=False)
    db.commit()
try:
    with httpx.Client(base_url="http://backend-api:8000",timeout=15) as client:
        response=client.post("/auth/login",json=dict(email=email,password=password));response.raise_for_status()
        client.headers["Authorization"]="Bearer "+response.json()["token"]
        response=client.post(f"/workspaces/{wid}/product-lines",json=dict(code="SMOKE",name="Synthetic smoke line",settings=dict(discovery_query="Synthetic customers Malaysia")))
        response.raise_for_status();lid=response.json()["id"]
        for kind in ("PRODUCT","ICP"):
            response=client.put(f"/workspaces/{wid}/product-lines/{lid}/catalog",json=dict(kind=kind,code=kind,name="Synthetic "+kind,description="A documented synthetic transport offering or customer segment"))
            response.raise_for_status()
        client.post(f"/workspaces/{wid}/product-lines/{lid}/resume").raise_for_status()
        response=client.post(f"/workspaces/{wid}/leads",json=dict(company_name="Synthetic Example",website="https://example.com/"))
        response.raise_for_status();lead_id=response.json()["id"]
        response=client.post(f"/workspaces/{wid}/product-lines/{lid}/leads/{lead_id}/prepare",json=dict(idempotency_key="day1-synthetic-smoke"))
        response.raise_for_status();run_id=UUID(response.json()["run_id"])
        with Session() as db:jid=db.scalar(select(Job.id).where(Job.run_id==run_id))
        deadline=time.monotonic()+30
        while True:
            response=client.get(f"/workspaces/{wid}/jobs/{jid}");response.raise_for_status();job=response.json()
            if job["status"] in ("FAILED","QUARANTINED","COMPLETED","NEEDS_REVIEW"):break
            if time.monotonic()>=deadline:raise RuntimeError("Worker did not finish the synthetic smoke task")
            time.sleep(0.25)
        assert job["status"]=="FAILED" and job["failure_code"]=="PROVIDER_NOT_CONFIGURED",job["failure_code"]
        assert job["contract_mode"]=="VERSIONED" and job["product_line_id"]==lid
        response=client.get(f"/workspaces/{wid}/jobs/{jid}/events");response.raise_for_status();events=response.json()
        assert [e["event"] for e in events]==["CLAIM","FAILURE"]
        assert all(e["trace_id"]==job["trace_id"] and e["schema_version"]==2 for e in events)
        with Session() as db:assert not list(db.scalars(select(ProviderUsage).where(ProviderUsage.workspace_id==wid)))
        print("PASS: restricted running API/worker, line-specific typed job, persisted trace/events, no provider calls or messages.")
finally:
    with Session() as db:
        for model in (JobReplay,StageEvent,StageArtifact,CompanyEvidence,DeliveryAttempt,Delivery,Approval,ProviderUsage,DiscoveryMemory,Job,PreparationRun,Lead,Catalog):
            db.execute(delete(model).where(model.workspace_id==wid))
        db.execute(delete(Membership).where(Membership.workspace_id==wid))
        db.execute(delete(ExecutorOwnership).where(ExecutorOwnership.workspace_id==wid))
        db.execute(delete(Workspace).where(Workspace.id==wid))
        db.execute(delete(OrganizationMembership).where(OrganizationMembership.organization_id==oid))
        db.execute(delete(Organization).where(Organization.id==oid))
        db.execute(delete(LoginSession).where(LoginSession.user_id==uid))
        db.execute(delete(User).where(User.id==uid));db.commit()
