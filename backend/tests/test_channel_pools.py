"""Approved social/message outbox acceptance with fake adapters only."""
import os
import tempfile
from datetime import timedelta
from uuid import UUID
from unittest.mock import Mock,patch
from sqlalchemy import select,func
from test_backend import BackendFixtures
import test_worker_pools as helpers
from marketing_backend.db import Session
from marketing_backend.models import PreparationRun,Approval,Delivery,DeliveryAttempt,DeliveryEvent,now
from marketing_backend.pipeline import context,fingerprint
from marketing_backend.sending import claim_attempt,execute_attempt,recover_expired


class ChannelPoolTests(BackendFixtures):
    def approved(self,channel,code="SOCIAL"):
        lid=helpers.WorkerPoolTests.line(self,code)
        draft=dict(channel=channel,recipient="https://www.linkedin.com/in/synthetic-person" if channel=="LINKEDIN" else "synthetic-messaging-recipient",
            subject="Synthetic reviewed asset",body="A synthetic message for approval and routing tests only.",asset_type="SOCIAL_TEXT")
        with Session() as db:
            snapshot=context(db,self.wid,self.lid,lid)
            run=PreparationRun(workspace_id=self.wid,product_line_id=lid,lead_id=self.lid,snapshot=snapshot,
                context_hash=fingerprint(snapshot),status="PENDING_APPROVAL",results={"DRAFTING":draft})
            db.add(run);db.flush()
            approval=Approval(workspace_id=self.wid,product_line_id=lid,run_id=run.id,
                snapshot=dict(context_hash=run.context_hash,inputs=snapshot,results=run.results,draft=draft))
            db.add(approval);db.commit();aid=approval.id
        response=self.client.post(f"/workspaces/{self.wid}/approvals/{aid}/decision",headers=self.headers,
            json=dict(decision="APPROVED",note="Explicit synthetic human review"))
        self.assertEqual(response.status_code,200,response.text)
        return aid,lid

    def delivery(self,aid,key="synthetic-channel-delivery"):
        response=self.client.post(f"/workspaces/{self.wid}/channel-deliveries",headers=self.headers,
            json=dict(approval_id=str(aid),idempotency_key=key))
        self.assertEqual(response.status_code,201,response.text)
        return UUID(response.json()["id"])

    def authorize(self,did):
        response=self.client.post(f"/workspaces/{self.wid}/deliveries/{did}/approve-send",headers=self.headers,json=dict(confirmed=True))
        self.assertEqual(response.status_code,202,response.text)

    def test_channel_pools_require_separate_human_authorization_and_never_cross_claim(self):
        social,_=self.approved("LINKEDIN");message,_=self.approved("MESSAGING","MESSAGE")
        social_id=self.delivery(social);message_id=self.delivery(message,"synthetic-message-delivery")
        with Session() as db:self.assertIsNone(claim_attempt(db,pool="SOCIAL"))
        self.authorize(social_id);self.authorize(message_id)
        with Session() as db:
            self.assertIsNone(claim_attempt(db,pool="EMAIL"))
            social_task=claim_attempt(db,pool="SOCIAL")
            self.assertEqual(db.get(DeliveryAttempt,social_task[0]).delivery_id,social_id)
            message_task=claim_attempt(db,pool="MESSAGING")
            self.assertEqual(db.get(DeliveryAttempt,message_task[0]).delivery_id,message_id)
        with patch.dict(os.environ,{"APP_ENV":"test","DELIVERY_ADAPTER_MODE":"synthetic"}):
            for pool,task,did in (("SOCIAL",social_task,social_id),("MESSAGING",message_task,message_id)):
                with Session() as db:
                    self.assertTrue(execute_attempt(db,*task,pool=pool))
                    self.assertEqual(db.get(Delivery,did).status,"ACCEPTED")
                    self.assertFalse(execute_attempt(db,*task,pool=pool))
        response=self.client.get(f"/workspaces/{self.wid}/deliveries/{social_id}/events",headers=self.headers)
        self.assertEqual([r["event"] for r in response.json()],["CLAIM","COMPLETION"])
        self.assertTrue(all(r["pool"]=="SOCIAL" for r in response.json()))
        self.assertNotIn("recipient",response.text);self.assertNotIn("body",response.text)

    def test_separate_restricted_channel_processes_use_synthetic_adapters(self):
        a,_=self.approved("LINKEDIN");b,_=self.approved("MESSAGING","PROCESS_MESSAGE")
        ids=[self.delivery(a),self.delivery(b,"separate-message-process")]
        for did in ids:self.authorize(did)
        with tempfile.TemporaryDirectory() as folder:
            processes=[helpers.WorkerPoolTests.child(self,pool,folder,once=True) for pool in ("SOCIAL","MESSAGING")]
            try:
                for process in processes:self.assertEqual(process.wait(timeout=25),0)
            finally:
                for process in processes:
                    if process.poll() is None:process.terminate();process.wait(timeout=10)
        with Session() as db:
            self.assertTrue(all(db.get(Delivery,did).status=="ACCEPTED" for did in ids))
            self.assertEqual({e.pool for e in db.scalars(select(DeliveryEvent))},{"SOCIAL","MESSAGING"})

    def test_wrong_pool_cannot_execute_claimed_channel(self):
        aid,_=self.approved("LINKEDIN");did=self.delivery(aid);self.authorize(did)
        with Session() as db:task=claim_attempt(db,pool="SOCIAL")
        adapter=Mock()
        with Session() as db:self.assertFalse(execute_attempt(db,*task,pool="MESSAGING",adapter=adapter))
        adapter.handoff.assert_not_called()

    def test_context_change_blocks_handoff_without_rewriting_approved_content(self):
        aid,lid=self.approved("LINKEDIN");did=self.delivery(aid);self.authorize(did)
        with Session() as db:task=claim_attempt(db,pool="SOCIAL");original=db.get(Delivery,did).snapshot.copy()
        result=self.client.patch(f"/workspaces/{self.wid}/product-lines/{lid}",headers=self.headers,json=dict(settings=dict(discovery_query="Changed synthetic customer segment")))
        self.assertEqual(result.status_code,200,result.text)
        adapter=Mock()
        with Session() as db:
            self.assertTrue(execute_attempt(db,*task,pool="SOCIAL",adapter=adapter))
            self.assertEqual(db.get(DeliveryAttempt,task[0]).failure_code,"STALE_APPROVAL_CONTEXT")
            self.assertEqual(db.get(Delivery,did).snapshot,original)
        adapter.handoff.assert_not_called()

    def test_expired_channel_handoff_stays_uncertain_and_cannot_be_retried(self):
        aid,_=self.approved("LINKEDIN");did=self.delivery(aid);self.authorize(did)
        with Session() as db:
            task=claim_attempt(db,pool="SOCIAL")
            db.get(DeliveryAttempt,task[0]).lease_until=now()-timedelta(seconds=1);db.commit();recover_expired(db)
            self.assertEqual(db.get(Delivery,did).status,"UNCERTAIN")
            self.assertFalse(execute_attempt(db,*task,pool="SOCIAL",adapter=Mock()))
        response=self.client.post(f"/workspaces/{self.wid}/deliveries/{did}/retry",headers=self.headers,json=dict(confirmed=True))
        self.assertEqual(response.status_code,409)

    def test_missing_live_adapter_fails_closed_and_idempotency_keeps_one_delivery(self):
        aid,_=self.approved("LINKEDIN");did=self.delivery(aid)
        self.assertEqual(self.delivery(aid),did);self.authorize(did)
        with Session() as db:task=claim_attempt(db,pool="SOCIAL")
        with patch.dict(os.environ,{"DELIVERY_ADAPTER_MODE":"disabled"}):
            with Session() as db:
                self.assertTrue(execute_attempt(db,*task,pool="SOCIAL"))
                self.assertEqual(db.get(DeliveryAttempt,task[0]).failure_code,"CHANNEL_NOT_CONFIGURED")
                self.assertEqual(db.scalar(select(func.count()).select_from(Delivery)),1)
