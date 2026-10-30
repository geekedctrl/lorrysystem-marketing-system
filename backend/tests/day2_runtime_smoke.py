"""Actual isolated API and seven stage processes; no provider or channel calls."""
import os
import secrets
import subprocess
import sys
import time
from sqlalchemy import select,delete
from marketing_backend.db import Session,engine
from marketing_backend.models import (User,Organization,OrganizationMembership,Membership,Workspace,
    ExecutorOwnership,Lead,PreparationRun,Job,StageEvent,StageArtifact,JobReplay,CompanyEvidence,
    ProviderUsage,DiscoveryMemory,Approval,Delivery,DeliveryAttempt,DeliveryEvent,Catalog)
from marketing_backend.auth import hash_password
from marketing_backend.pools import STAGES

if os.getenv("APP_ENV")!="local-smoke" or engine.url.database!="marketing_rebuild":
    raise RuntimeError("Use the isolated compose backend-smoke service")

# First exercise a normal HTTP preparation request and real research worker.
subprocess.run([sys.executable,"-m","tests.day1_runtime_smoke"],check=True)
with Session() as db:
    actor=User(email="day2-smoke-"+secrets.token_hex(8)+"@example.test",password_hash=hash_password(secrets.token_urlsafe(24)))
    org=Organization(name="DAY2 SYNTHETIC POOL SMOKE")
    db.add_all([actor,org]);db.flush()
    workspace=Workspace(organization_id=org.id,name="DAY2 SYNTHETIC POOL SMOKE",automation_enabled=True)
    db.add(workspace);db.flush();uid,wid,oid=actor.id,workspace.id,org.id
    db.query(ExecutorOwnership).filter(ExecutorOwnership.workspace_id==wid).update({ExecutorOwnership.owner:"PYTHON"},synchronize_session=False)
    db.add_all([Membership(workspace_id=wid,user_id=uid,role="ADMIN"),OrganizationMembership(organization_id=oid,user_id=uid,role="OWNER")])
    jobs={}
    for stage in STAGES:
        lead=run=None
        if stage not in ("SETUP","DISCOVERY"):
            lead=Lead(workspace_id=wid,company_name="Synthetic "+stage,website="https://"+stage.lower().replace('_','-')+".example.test/")
            db.add(lead);db.flush()
            run=PreparationRun(workspace_id=wid,lead_id=lead.id,context_hash="a"*64,snapshot={},results={})
            db.add(run);db.flush()
        # A malformed header must be quarantined before any handler or provider.
        job=Job(workspace_id=wid,kind=stage,managed=True,lead_id=lead.id if lead else None,
            run_id=run.id if run else None,idempotency_key="day2-smoke-"+stage,payload={},task_envelope={"schema_version":999})
        db.add(job);db.flush();jobs[stage]=job.id
    db.commit()
try:
    deadline=time.monotonic()+45
    while True:
        with Session() as db:states={stage:db.get(Job,jid).status for stage,jid in jobs.items()}
        if all(v=="QUARANTINED" for v in states.values()):break
        if time.monotonic()>=deadline:raise RuntimeError("Some stage pools did not process synthetic tasks: "+str(states))
        time.sleep(.25)
    with Session() as db:
        for stage,jid in jobs.items():
            events=list(db.scalars(select(StageEvent).where(StageEvent.job_id==jid).order_by(StageEvent.created_at)))
            assert [e.event for e in events]==["CLAIM","QUARANTINE"]
            assert all(e.pool==stage for e in events)
        assert not list(db.scalars(select(ProviderUsage).where(ProviderUsage.workspace_id==wid)))
        assert not list(db.scalars(select(StageArtifact).where(StageArtifact.workspace_id==wid)))
    print("PASS: seven independent stage pools claimed their own tasks; malformed inputs quarantined; no provider calls or messages.")
finally:
    with Session() as db:
        for model in (DeliveryEvent,JobReplay,StageEvent,StageArtifact,CompanyEvidence,DeliveryAttempt,Delivery,Approval,ProviderUsage,DiscoveryMemory,Job,PreparationRun,Lead,Catalog):
            db.execute(delete(model).where(model.workspace_id==wid))
        db.execute(delete(Membership).where(Membership.workspace_id==wid))
        db.execute(delete(ExecutorOwnership).where(ExecutorOwnership.workspace_id==wid))
        db.execute(delete(Workspace).where(Workspace.id==wid))
        db.execute(delete(OrganizationMembership).where(OrganizationMembership.organization_id==oid))
        db.execute(delete(Organization).where(Organization.id==oid))
        db.execute(delete(User).where(User.id==uid));db.commit()
