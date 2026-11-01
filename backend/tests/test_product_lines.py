"""Full Day 1 synthetic acceptance: shared companies, isolated product lines."""
import json
from uuid import UUID
from concurrent.futures import ThreadPoolExecutor
import threading
from unittest.mock import patch,Mock
from sqlalchemy import select,func,text
from test_backend import BackendFixtures
from test_native_pipeline import FixtureProviders,PAGE,URL,PERSON,SERVICE
from marketing_backend.db import Session
from marketing_backend.models import ProductLine,Catalog,Job,Lead,PreparationRun,Approval,StageArtifact,CompanyEvidence,ProviderUsage
from marketing_backend import queue
from marketing_backend.worker import execute
from marketing_backend.providers import Providers
from marketing_backend.research import ProviderFailure


class ProductLineTests(BackendFixtures):
    def setUp(self):
        super().setUp()
        self.prefix=f"/workspaces/{self.wid}/product-lines"
        self.a=self.make_line("ALPHA","Manufacturing companies managing deliveries")
        self.b=self.make_line("BETA","Commercial transport operators")
        (FixtureProviders.people,FixtureProviders.opportunity,FixtureProviders.ambiguous,
         FixtureProviders.keyed_scoring,FixtureProviders.quote_alias_scoring,FixtureProviders.invalid_contact_roles)=(True,True,False,False,False,False)
        self.patcher=patch("marketing_backend.stages.Providers",FixtureProviders)
        self.fetch=patch("marketing_backend.stages.fetch_public",return_value=dict(fetch_status="SUCCESS",final_url=URL,body="<p>"+PAGE+"</p>"))
        self.patcher.start();self.fetcher=self.fetch.start()
        self.addCleanup(self.patcher.stop);self.addCleanup(self.fetch.stop)

    def make_line(self,code,query):
        result=self.client.post(self.prefix,headers=self.headers,json=dict(code=code,name=code+" product",settings=dict(discovery_query=query)))
        self.assertEqual(result.status_code,201,result.text);lid=UUID(result.json()["id"])
        for kind in ("PRODUCT","ICP"):
            response=self.client.put(f"{self.prefix}/{lid}/catalog",headers=self.headers,json=dict(kind=kind,code=kind,
                name=code+" "+kind,description="Transport scheduling for "+code+" documented customer operations"))
            self.assertEqual(response.status_code,201,response.text)
        response=self.client.post(f"{self.prefix}/{lid}/resume",headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        return lid

    def prepare_line(self,lid,key="prepare-line-test",lead=None):
        response=self.client.post(f"{self.prefix}/{lid}/leads/{lead or self.lid}/prepare",headers=self.headers,json=dict(idempotency_key=key))
        self.assertEqual(response.status_code,202,response.text)
        return UUID(response.json()["run_id"])

    def drain(self,maximum=20):
        for _ in range(maximum):
            with Session() as db:job=queue.claim(db)
            if not job:return
            execute(job)
            with Session() as db:
                current=db.get(Job,job.id)
                self.assertNotIn(current.status,("FAILED","QUARANTINED"),(job.kind,current.failure_code))
        self.fail("Bounded synthetic pipeline did not drain")

    def test_same_key_codes_and_company_are_isolated_between_lines(self):
        ra=self.prepare_line(self.a);rb=self.prepare_line(self.b)
        with Session() as db:
            jobs=list(db.scalars(select(Job).where(Job.run_id.in_([ra,rb]))))
            self.assertEqual(len(jobs),2)
            self.assertEqual({j.lead_id for j in jobs},{self.lid})
            for job in jobs:
                expected="ALPHA" if job.product_line_id==self.a else "BETA"
                self.assertTrue(all(c["name"].startswith(expected) for c in job.payload["context"]["catalog"]))
                self.assertEqual(job.task_envelope["product_line_id"],str(job.product_line_id))
                self.assertTrue(job.task_envelope["input_hash"])
        self.drain()
        with Session() as db:
            approvals=list(db.scalars(select(Approval).where(Approval.run_id.in_([ra,rb]))))
            self.assertEqual({a.product_line_id for a in approvals},{self.a,self.b})
            self.assertTrue(all(a.status=="PENDING" for a in approvals))
            self.assertNotEqual(approvals[0].snapshot["context_hash"],approvals[1].snapshot["context_hash"])
            self.assertEqual(db.scalar(select(func.count()).select_from(Lead)),1)
            self.assertEqual(db.scalar(select(func.count()).select_from(StageArtifact)),10)
            self.assertEqual(len(list(db.scalars(select(CompanyEvidence)))),1)

    def test_legacy_catalog_does_not_include_new_product_lines(self):
        response=self.client.get(f"/workspaces/{self.wid}/catalog",headers=self.headers)
        self.assertEqual(len(response.json()),2)
        self.assertFalse(any(v["name"].startswith(("ALPHA","BETA")) for v in response.json()))
        viewer={"Authorization":"Bearer "+self.login("viewer@example.test")}
        self.assertEqual(self.client.patch(f"{self.prefix}/{self.a}",headers=viewer,json=dict(name="Changed")).status_code,403)
        self.assertEqual(self.client.get(f"/workspaces/{self.other}/product-lines/{self.a}",headers=self.headers).status_code,404)

    def test_edit_invalidates_only_its_line_and_prevents_inflight_completion(self):
        ra=self.prepare_line(self.a);rb=self.prepare_line(self.b)
        with Session() as db:claimed=queue.claim(db)
        self.assertEqual(claimed.product_line_id,self.a)
        response=self.client.patch(f"{self.prefix}/{self.a}",headers=self.headers,json=dict(settings=dict(discovery_query="Updated target segment")))
        self.assertEqual(response.status_code,200,response.text)
        handler=Mock();execute(claimed,handler)
        handler.assert_not_called()
        with Session() as db:
            self.assertEqual(db.get(PreparationRun,ra).status,"STALE")
            self.assertEqual(db.get(PreparationRun,rb).status,"PREPARING")
        self.drain()
        with Session() as db:self.assertEqual(db.get(PreparationRun,rb).status,"PENDING_APPROVAL")

    def test_line_concurrency_is_atomic_and_other_line_can_claim(self):
        self.prepare_line(self.a)
        created=self.client.post(f"/workspaces/{self.wid}/leads",headers=self.headers,json=dict(company_name="Second company",website="https://example.org/"))
        self.assertEqual(created.status_code,201,created.text)
        self.prepare_line(self.a,"second-line-a-key",UUID(created.json()["id"]))
        barrier=threading.Barrier(2)
        def claim(_):
            barrier.wait()
            with Session() as db:
                job=queue.claim(db);return job.id if job else None
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(claim,range(2)))
        self.assertEqual(sum(v is not None for v in results),1)
        self.prepare_line(self.b)
        with Session() as db:
            job=queue.claim(db)
            self.assertEqual(job.product_line_id,self.b)

    def test_pause_blocks_only_selected_line(self):
        ra=self.prepare_line(self.a);rb=self.prepare_line(self.b)
        response=self.client.post(f"{self.prefix}/{self.a}/pause",headers=self.headers)
        self.assertEqual(response.status_code,200)
        self.drain()
        with Session() as db:
            self.assertEqual(db.get(PreparationRun,ra).status,"PREPARING")
            self.assertEqual(db.get(PreparationRun,rb).status,"PENDING_APPROVAL")
        self.assertEqual(self.client.post(f"{self.prefix}/{self.a}/resume",headers=self.headers).status_code,200)
        self.drain()
        with Session() as db:self.assertEqual(db.get(PreparationRun,ra).status,"PENDING_APPROVAL")

    def test_queries_and_candidates_are_line_specific_but_company_is_shared(self):
        for lid in (self.a,self.b):
            response=self.client.post(f"{self.prefix}/{lid}/discovery",headers=self.headers,json=dict(idempotency_key="same-discovery-key"))
            self.assertEqual(response.status_code,202,response.text)
        queries=[];original=FixtureProviders.search
        def capture(provider,operation,query,**options):
            if operation.startswith("discovery"):queries.append((provider.job.product_line_id,query))
            return original(provider,operation,query,**options)
        with patch.object(FixtureProviders,"search",capture):self.drain()
        self.assertTrue(any(lid==self.a and "Manufacturing" in q for lid,q in queries))
        self.assertTrue(any(lid==self.b and "Commercial transport operators" in q for lid,q in queries))
        for lid in (self.a,self.b):
            page=self.client.get(f"/workspaces/{self.wid}/candidates?product_line_id={lid}",headers=self.headers).json()
            self.assertEqual(len(page["items"]),1)
            cid=page["items"][0]["id"]
            accepted=self.client.post(f"/workspaces/{self.wid}/candidates/{cid}/accept",headers=self.headers,json={})
            self.assertEqual(accepted.status_code,200,accepted.text)
            self.assertEqual(accepted.json()["lead_id"],str(self.lid))
        with Session() as db:self.assertEqual(db.scalar(select(func.count()).select_from(Lead)),1)

    def test_approval_for_one_line_is_not_superseded_by_another_line(self):
        ra=self.prepare_line(self.a);rb=self.prepare_line(self.b);self.drain()
        with Session() as db:aid=db.scalar(select(Approval.id).where(Approval.run_id==ra))
        response=self.client.post(f"/workspaces/{self.wid}/approvals/{aid}/decision",headers=self.headers,
            json=dict(decision="APPROVED",note="Synthetic human approval for Alpha"))
        self.assertEqual(response.status_code,200,response.text)
        self.assertFalse(response.json()["sent"])
        with Session() as db:
            self.assertEqual(db.get(PreparationRun,ra).status,"APPROVED")
            self.assertEqual(db.get(PreparationRun,rb).status,"PENDING_APPROVAL")

    def test_stale_approval_is_rejected_without_rewriting_snapshot(self):
        rid=self.prepare_line(self.a);self.drain()
        with Session() as db:
            a=db.scalar(select(Approval).where(Approval.run_id==rid));aid=a.id;original=a.snapshot
        self.client.patch(f"{self.prefix}/{self.a}",headers=self.headers,json=dict(settings=dict(qualification_score=90)))
        response=self.client.post(f"/workspaces/{self.wid}/approvals/{aid}/decision",headers=self.headers,
            json=dict(decision="APPROVED",note="This stale approval must be rejected"))
        self.assertEqual(response.status_code,409,response.text)
        with Session() as db:
            self.assertEqual(db.get(Approval,aid).snapshot,original)
            self.assertEqual(db.get(Approval,aid).status,"PENDING")

    def test_human_contact_resolution_creates_a_new_immutable_artifact(self):
        FixtureProviders.ambiguous=True
        rid=self.prepare_line(self.a);self.drain()
        with Session() as db:
            run=db.get(PreparationRun,rid);self.assertEqual(run.status,"NEEDS_REVIEW")
            contact=db.scalar(select(Job).where(Job.run_id==rid,Job.kind=="CONTACT_SEARCH"))
            original=db.scalar(select(StageArtifact).where(StageArtifact.job_id==contact.id));old_id=original.id;old_value=original.payload
        response=self.client.post(f"/workspaces/{self.wid}/preparation/{rid}/contact",headers=self.headers,json=dict(business_contact=dict(
            name="Alex Worker",role="Operations Director",email="alex@example.com",phone=None,source_url=URL,evidence_quote=PERSON)))
        self.assertEqual(response.status_code,202,response.text)
        self.drain()
        with Session() as db:
            self.assertEqual(db.get(StageArtifact,old_id).payload,old_value)
            self.assertEqual(db.get(PreparationRun,rid).status,"PENDING_APPROVAL")
            self.assertEqual(db.scalar(select(func.count()).select_from(StageArtifact).where(StageArtifact.job_id==contact.id)),2)

    def test_line_budget_and_rate_controls_preserve_global_ceiling(self):
        response=self.client.patch(f"{self.prefix}/{self.a}",headers=self.headers,json=dict(limits=dict(monthly_budget_microusd=1)))
        self.assertEqual(response.status_code,200)
        self.prepare_line(self.a)
        with Session() as db:job=queue.claim(db)
        with self.assertRaises(ProviderFailure) as error:Providers(job,Mock()).reserve("MODEL","synthetic",2)
        self.assertEqual(error.exception.code,"PRODUCT_LINE_BUDGET_EXHAUSTED")
        self.prepare_line(self.b)
        with Session() as db:other=queue.claim(db)
        uid=Providers(other,Mock()).reserve("MODEL","synthetic",2)
        with Session() as db:self.assertEqual(db.get(ProviderUsage,uid).product_line_id,self.b)
        with patch.dict("os.environ",{"PROVIDER_MONTHLY_BUDGET_USD":"0"}):
            with self.assertRaises(ProviderFailure) as error:Providers(other,Mock()).reserve("MODEL","synthetic-again",1)
        self.assertEqual(error.exception.code,"PROVIDER_BUDGET_EXHAUSTED")

    def test_provider_rate_is_enforced_before_a_second_reservation(self):
        self.client.patch(f"{self.prefix}/{self.a}",headers=self.headers,json=dict(limits=dict(provider_requests_per_minute=1)))
        self.prepare_line(self.a)
        with Session() as db:job=queue.claim(db)
        provider=Providers(job,Mock());provider.reserve("MODEL","first",0)
        with self.assertRaises(ProviderFailure) as error:provider.reserve("MODEL","second",0)
        self.assertEqual(error.exception.code,"PRODUCT_LINE_RATE_LIMITED")

    def test_database_rejects_a_job_bound_to_another_lines_run(self):
        rid=self.prepare_line(self.a)
        with Session() as db:
            with self.assertRaises(Exception):db.execute(text("UPDATE jobs SET product_line_id=:b WHERE run_id=:run"),{"b":self.b,"run":rid})
