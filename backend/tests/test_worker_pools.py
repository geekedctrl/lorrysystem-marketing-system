"""PostgreSQL and restricted subprocess acceptance for pool boundaries."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from uuid import UUID
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch
from sqlalchemy import select,func
from test_backend import BackendFixtures
from marketing_backend.db import Session,engine
from marketing_backend.models import Job,Lead,Workspace,StageEvent,StageArtifact,PreparationRun,Approval,ProductLine,Delivery,DeliveryAttempt,DeliveryEvent,ProviderUsage,DiscoveryMemory,now
from marketing_backend.pools import STAGES
from marketing_backend import queue
from marketing_backend.runner import scheduler_tick


class WorkerPoolTests(BackendFixtures):
    def make_jobs(self):
        ids={}
        with Session() as db:
            db.get(Workspace,self.wid).automation_enabled=True
            for stage in STAGES:
                lead=None
                run=None
                if stage not in ("SETUP","DISCOVERY"):
                    lead=Lead(workspace_id=self.wid,company_name="Synthetic "+stage,website="https://"+stage.lower().replace('_','-')+".example.test/")
                    db.add(lead);db.flush()
                    run=PreparationRun(workspace_id=self.wid,lead_id=lead.id,context_hash="a"*64,snapshot={},results={})
                    db.add(run);db.flush()
                job=Job(workspace_id=self.wid,lead_id=lead.id if lead else None,run_id=run.id if run else None,kind=stage,
                    managed=True,idempotency_key="pool-test-"+stage,payload={})
                db.add(job);db.flush();ids[stage]=job.id
            db.commit()
        return ids

    def test_every_pool_claims_only_its_stage_and_other_backlog_remains_pending(self):
        ids=self.make_jobs()
        for stage in reversed(STAGES):
            with Session() as db:
                claimed=queue.claim(db,pool=stage)
                self.assertEqual(claimed.id,ids[stage])
                self.assertIsNone(queue.claim(db,pool=stage))
        with Session() as db:
            self.assertEqual({r.pool for r in db.scalars(select(StageEvent))},set(STAGES))

    def test_stage_claim_does_not_recover_expired_jobs_from_another_pool(self):
        ids=self.make_jobs()
        with Session() as db:
            job=queue.claim(db,pool="RESEARCH")
            token=job.lease_token;job.lease_until=now()-timedelta(seconds=1);db.commit()
        with Session() as db:
            self.assertEqual(queue.claim(db,pool="SCORING").id,ids["SCORING"])
            self.assertEqual(db.get(Job,ids["RESEARCH"]).status,"RUNNING")
        scheduler_tick()
        with Session() as db:
            job=db.get(Job,ids["RESEARCH"])
            self.assertEqual(job.status,"PENDING")
            with self.assertRaises(queue.LeaseLost):queue.complete(db,job.id,token,{})

    def test_concurrent_process_claims_do_not_duplicate_job_ownership(self):
        ids=self.make_jobs()
        def claim():
            with Session() as db:
                result=queue.claim(db,pool="RESEARCH")
                return result.id if result else None
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(lambda _:claim(),range(4)))
        self.assertEqual([v for v in results if v],[ids["RESEARCH"]])

    def line(self,code):
        base=f"/workspaces/{self.wid}/product-lines"
        result=self.client.post(base,headers=self.headers,json=dict(code=code,name=code+" product",settings=dict(discovery_query=code+" transport buyers")))
        self.assertEqual(result.status_code,201,result.text);lid=UUID(result.json()["id"])
        for kind in ("PRODUCT","ICP"):
            response=self.client.put(f"{base}/{lid}/catalog",headers=self.headers,json=dict(kind=kind,code=kind,name=code+" "+kind,description="Documented transport planning for synthetic "+code+" customers"))
            self.assertEqual(response.status_code,201,response.text)
        self.assertEqual(self.client.post(f"{base}/{lid}/resume",headers=self.headers).status_code,200)
        return lid

    def child(self,pool,folder,once=False):
        url=engine.url.set(username="backend_worker",password=os.environ["WORKER_DB_PASSWORD"])
        env={**os.environ,"DATABASE_URL":url.render_as_string(hide_password=False),
            "WORKER_HEALTH_DIR":folder,"DELIVERY_ADAPTER_MODE":"synthetic"}
        command=[sys.executable,"-m","tests.day2_fixture_worker","--pool",pool]
        if once:command.append("--once")
        return subprocess.Popen(command,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

    def test_real_restricted_processes_advance_two_lines_and_stopped_pool_is_independent(self):
        a,b=self.line("ALPHA"),self.line("BETA")
        runs=[]
        for lid in (a,b):
            response=self.client.post(f"/workspaces/{self.wid}/product-lines/{lid}/leads/{self.lid}/prepare",headers=self.headers,json=dict(idempotency_key="process-preparation"))
            self.assertEqual(response.status_code,202,response.text);runs.append(UUID(response.json()["run_id"]))
        with tempfile.TemporaryDirectory() as folder:
            # Start a pool with no eligible work first; it must not steal research.
            process=self.child("MATCHING",folder,once=True)
            self.assertEqual(process.wait(timeout=20),0)
            with Session() as db:self.assertTrue(all(j.status=="PENDING" for j in db.scalars(select(Job).where(Job.run_id.in_(runs)))))
            processes=[self.child(p,folder) for p in ("RESEARCH","CONTACT_SEARCH","SCORING","MATCHING","DRAFTING")]
            try:
                deadline=time.monotonic()+60
                while time.monotonic()<deadline:
                    with Session() as db:
                        states=[db.get(PreparationRun,r).status for r in runs]
                    if states==["PENDING_APPROVAL"]*2:break
                    self.assertFalse(any(p.poll() is not None for p in processes),"Pool exited unexpectedly")
                    time.sleep(.2)
                self.assertEqual(states,["PENDING_APPROVAL"]*2)
                with Session() as db:
                    self.assertEqual(db.scalar(select(func.count()).select_from(StageArtifact)),10)
                    self.assertEqual(db.scalar(select(func.count()).select_from(Approval)),2)
                    self.assertTrue(all(e.pool==e.stage for e in db.scalars(select(StageEvent))))
            finally:
                for p in processes:p.terminate()
                for p in processes:p.wait(timeout=15)

    def test_synthetic_discovery_canary_preserves_candidate_contract_and_history(self):
        from marketing_backend.artifacts import consume_artifact
        from marketing_backend.stage_contracts import validate_payload
        a,b=self.line("BASELINE"),self.line("CANARY")
        response=self.client.patch(f"/workspaces/{self.wid}/product-lines/{b}",headers=self.headers,
            json=dict(settings=dict(discovery_query="CANARY transport buyers",discovery_query_strategy="official")))
        self.assertEqual(response.status_code,200,response.text)
        for lid in (a,b):
            response=self.client.post(f"/workspaces/{self.wid}/product-lines/{lid}/discovery",headers=self.headers,json=dict(idempotency_key="canary-discovery"))
            self.assertEqual(response.status_code,202,response.text)
        with tempfile.TemporaryDirectory() as folder:
            for _ in range(2):
                process=self.child("DISCOVERY",folder,once=True)
                self.assertEqual(process.wait(timeout=25),0)
        with Session() as db:
            rows=list(db.scalars(select(StageArtifact).order_by(StageArtifact.created_at)))
            self.assertEqual(len(rows),2)
            self.assertEqual({r.strategy_versions["query"] for r in rows},{"icp-queries.1","icp-queries.2"})
            for row in rows:
                candidate=consume_artifact(db,row.id,row.workspace_id,row.product_line_id,row.context_version,row.context_hash)
                self.assertEqual(validate_payload("discovery.candidate",row.schema_version,candidate),candidate)
                job=db.get(Job,row.job_id)
                self.assertEqual(job.result["counts"]["candidates_ready"],1)
                self.assertEqual(job.status,"COMPLETED")
            original_ids={r.id for r in rows}
            groups={"baseline":[r.job_id for r in rows if r.product_line_id==a],
                "canary":[r.job_id for r in rows if r.product_line_id==b]}
            from canary_report import collect,evaluate,export
            report=collect(db,groups)
            candidates=list(db.scalars(select(DiscoveryMemory)))
            candidate_ids=[r.id for r in candidates]
            self.assertEqual(len(candidates),2)
        for cid in candidate_ids:
            response=self.client.post(f"/workspaces/{self.wid}/candidates/{cid}/accept",headers=self.headers,json=dict(note="Synthetic canary human acceptance"))
            self.assertEqual(response.status_code,200,response.text)
        with tempfile.TemporaryDirectory() as folder:
            for _ in range(2):
                process=self.child("RESEARCH",folder,once=True)
                self.assertEqual(process.wait(timeout=25),0)
        with Session() as db:
            research_outputs=db.scalar(select(func.count()).select_from(StageArtifact).where(StageArtifact.contract_name=="research.output"))
            self.assertEqual(research_outputs,2)
            report["proof"]["downstream_research_outputs"]=research_outputs
        response=self.client.patch(f"/workspaces/{self.wid}/product-lines/{b}",headers=self.headers,
            json=dict(settings=dict(discovery_query="CANARY transport buyers",discovery_query_strategy="baseline")))
        self.assertEqual(response.status_code,200,response.text)
        with Session() as db:
            self.assertTrue(original_ids.issubset({r.id for r in db.scalars(select(StageArtifact))}))
            self.assertTrue(all(db.get(DiscoveryMemory,cid).outcome=="ACCEPTED" for cid in candidate_ids))
            self.assertEqual(db.scalar(select(func.count()).select_from(ProviderUsage)),0)
            report["proof"].update(historical_artifacts_retained=original_ids.issubset({r.id for r in db.scalars(select(StageArtifact))}),
                human_acceptance_retained=all(db.get(DiscoveryMemory,cid).outcome=="ACCEPTED" for cid in candidate_ids),
                rollback_query_strategy=db.get(ProductLine,b).settings["discovery_query_strategy"])
        evaluate(report)
        self.assertTrue(report["passed"],report["checks"])
        if os.getenv("SYNTHETIC_CANARY_REPORT_DIR"):
            export(report,os.environ["SYNTHETIC_CANARY_REPORT_DIR"])

    def test_another_pool_process_runs_while_research_is_stopped(self):
        ids=self.make_jobs()
        with Session() as db:
            for jid in ids.values():db.get(Job,jid).task_envelope={"schema_version":999}
            db.commit()
        with tempfile.TemporaryDirectory() as folder:
            process=self.child("SCORING",folder,once=True)
            self.assertEqual(process.wait(timeout=20),0)
        with Session() as db:
            self.assertEqual(db.get(Job,ids["SCORING"]).status,"QUARANTINED")
            self.assertEqual(db.get(Job,ids["RESEARCH"]).status,"PENDING")

    def test_restarted_process_finishes_expired_lease_without_duplicate_artifacts(self):
        lid=self.line("RESTART")
        response=self.client.post(f"/workspaces/{self.wid}/product-lines/{lid}/leads/{self.lid}/prepare",headers=self.headers,json=dict(idempotency_key="restart-preparation"))
        run=UUID(response.json()["run_id"])
        with Session() as db:
            job=queue.claim(db,pool="RESEARCH");old_token=job.lease_token
            job.lease_until=now()-timedelta(seconds=1);db.commit()
        scheduler_tick()
        with Session() as db:
            job=db.scalar(select(Job).where(Job.run_id==run));job.available_at=now();db.commit();jid=job.id
        with tempfile.TemporaryDirectory() as folder:
            process=self.child("RESEARCH",folder,once=True);self.assertEqual(process.wait(timeout=25),0)
        with Session() as db:
            self.assertEqual(db.get(Job,jid).status,"COMPLETED")
            self.assertEqual(db.scalar(select(func.count()).select_from(StageArtifact).where(StageArtifact.job_id==jid)),1)
            with self.assertRaises(queue.LeaseLost):queue.complete(db,jid,old_token,{})
