import os, secrets, unittest, uuid
from datetime import timedelta
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

os.environ["SENDER_CREDENTIAL_ENCRYPTION_KEY"] = Fernet.generate_key().decode()

from marketing_backend.api import app
from marketing_backend.auth import hash_password
from marketing_backend.db import Session, engine
from marketing_backend.models import (
    Approval, Catalog, Delivery, DeliveryAttempt, DiscoveryMemory, EmailSuppression,
    Job, Lead, LoginAttempt, LoginSession, Membership, PreparationRun, ProviderUsage,
    SenderConnection, User, Workspace, now,
    ExecutorOwnership,
)
from marketing_backend.sending import HandoffError, claim_attempt, encrypt_secret, execute_attempt, recover_expired

if os.getenv("APP_ENV") != "test" or engine.url.database != "marketing_rebuild_test":
    raise RuntimeError("Tests require the dedicated marketing_rebuild_test database")


class NativeSendingTests(unittest.TestCase):
    def setUp(self):
        with Session() as db:
            for model in (DeliveryAttempt, Delivery, EmailSuppression, SenderConnection, Approval, ProviderUsage, DiscoveryMemory, Job, PreparationRun, Lead, Catalog, Membership, LoginSession, LoginAttempt, ExecutorOwnership, Workspace, User):
                db.execute(delete(model))
            self.password = secrets.token_urlsafe(20)
            actor = User(email="sender@example.test", password_hash=hash_password(self.password))
            workspace = Workspace(name="Delivery tests")
            db.add_all([actor, workspace]); db.flush()
            db.query(ExecutorOwnership).filter(ExecutorOwnership.workspace_id == workspace.id).update({ExecutorOwnership.owner: "PYTHON"}, synchronize_session=False)
            db.add(Membership(workspace_id=workspace.id, user_id=actor.id, role="ADMIN"))
            run = PreparationRun(workspace_id=workspace.id, lead_id=None, context_hash="a" * 64, snapshot={}, status="APPROVED", results={})
            # The model requires a lead FK in normal operation. Build the fixture with SQL after IDs exist below.
            lead = Lead(workspace_id=workspace.id, company_name="Example", website="https://example.test")
            db.add(lead); db.flush(); run.lead_id = lead.id; db.add(run); db.flush()
            snapshot = {"context_hash": run.context_hash, "draft": {"recipient":"buyer@example.test","subject":"Hello","body":"A reviewed message","channel":"EMAIL"}}
            approval = Approval(workspace_id=workspace.id, run_id=run.id, snapshot=snapshot, status="PENDING", decision={})
            sender = SenderConnection(workspace_id=workspace.id, name="Test", from_email="team@example.test", from_name="Team", host="smtp.example.test", port=587, security="STARTTLS", username="team@example.test", secret_ciphertext=encrypt_secret("password", workspace.id), enabled=True, verified_at=now())
            db.add_all([approval, sender]); db.commit()
            approval.status="APPROVED"; approval.decision={"actor_id":str(actor.id),"at":now().isoformat(),"note":"content approved"}; db.commit()
            self.wid,self.uid,self.approval_id,self.sender_id=workspace.id,actor.id,approval.id,sender.id
        self.client=TestClient(app)
        token=self.client.post("/auth/login",json={"email":"sender@example.test","password":self.password}).json()["token"]
        self.headers={"Authorization":"Bearer "+token}

    def create_delivery(self, key="delivery-key-0001"):
        return self.client.post(f"/workspaces/{self.wid}/deliveries",headers=self.headers,json={"approval_id":str(self.approval_id),"sender_id":str(self.sender_id),"idempotency_key":key})

    def test_separate_send_approval_idempotent_outbox_and_acceptance(self):
        first=self.create_delivery(); self.assertEqual(first.status_code,201,first.text)
        duplicate=self.create_delivery(); self.assertEqual(duplicate.json()["id"],first.json()["id"])
        self.assertEqual(first.json()["status"],"PENDING_SEND_APPROVAL")
        history=self.client.get(f"/workspaces/{self.wid}/deliveries",headers=self.headers)
        self.assertEqual(history.status_code,200); self.assertEqual(history.json()[0]["id"],first.json()["id"])
        queued=self.client.post(f"/workspaces/{self.wid}/deliveries/{first.json()['id']}/approve-send",headers=self.headers,json={"confirmed":True})
        self.assertEqual(queued.status_code,202,queued.text); self.assertEqual(queued.json()["status"],"QUEUED")
        with Session() as db:
            claimed=claim_attempt(db); self.assertIsNotNone(claimed)
        sent=[]
        with Session() as db:
            self.assertTrue(execute_attempt(db,*claimed,transport=lambda sender,password,message,recipient: sent.append((password,recipient,message["Message-ID"]))))
            delivery=db.get(Delivery,uuid.UUID(first.json()["id"])); self.assertEqual(delivery.status,"ACCEPTED")
            self.assertEqual(len(list(db.scalars(select(DeliveryAttempt).where(DeliveryAttempt.delivery_id==delivery.id)))),1)
        self.assertEqual(sent[0][0:2],("password","buyer@example.test"))

    def test_suppression_stale_context_and_uncertain_handoff_block_retry(self):
        suppressed=self.client.post(f"/workspaces/{self.wid}/email-suppressions",headers=self.headers,json={"email":"buyer@example.test","reason":"DO_NOT_CONTACT"})
        self.assertEqual(suppressed.status_code,201)
        self.assertEqual(self.client.get(f"/workspaces/{self.wid}/email-suppressions",headers=self.headers).json()[0]["email"],"buyer@example.test")
        self.assertEqual(self.create_delivery().status_code,409)
        with Session() as db:
            db.execute(delete(EmailSuppression)); db.commit()
            run=db.scalar(select(PreparationRun).where(PreparationRun.workspace_id==self.wid)); run.context_hash="b"*64; db.commit()
        self.assertEqual(self.create_delivery("delivery-key-0002").status_code,409)
        with Session() as db:
            run=db.scalar(select(PreparationRun).where(PreparationRun.workspace_id==self.wid)); run.context_hash="a"*64; db.commit()
        made=self.create_delivery("delivery-key-0003").json(); self.client.post(f"/workspaces/{self.wid}/deliveries/{made['id']}/approve-send",headers=self.headers,json={"confirmed":True})
        with Session() as db: claimed=claim_attempt(db)
        with Session() as db: execute_attempt(db,*claimed,transport=lambda *_: (_ for _ in ()).throw(HandoffError("SMTP_HANDOFF_UNCERTAIN",True)))
        retry=self.client.post(f"/workspaces/{self.wid}/deliveries/{made['id']}/retry",headers=self.headers,json={"confirmed":True})
        self.assertEqual(retry.status_code,409)

    def test_known_failure_retry_and_terminated_worker_become_uncertain(self):
        made=self.create_delivery().json(); did=made["id"]
        self.client.post(f"/workspaces/{self.wid}/deliveries/{did}/approve-send",headers=self.headers,json={"confirmed":True})
        with Session() as db: claimed=claim_attempt(db)
        with Session() as db: execute_attempt(db,*claimed,transport=lambda *_: (_ for _ in ()).throw(HandoffError("SMTP_CONNECTION_FAILED")))
        retry=self.client.post(f"/workspaces/{self.wid}/deliveries/{did}/retry",headers=self.headers,json={"confirmed":True})
        self.assertEqual(retry.status_code,202,retry.text); self.assertEqual(len(retry.json()["attempts"]),2)
        with Session() as db:
            claim_attempt(db)
            attempt=db.scalar(select(DeliveryAttempt).where(DeliveryAttempt.delivery_id==uuid.UUID(did),DeliveryAttempt.status=="SENDING")); attempt.lease_until=now()-timedelta(seconds=1); db.commit(); recover_expired(db)
            self.assertEqual(db.get(Delivery,uuid.UUID(did)).status,"UNCERTAIN"); self.assertEqual(attempt.status,"UNCERTAIN")


if __name__ == "__main__": unittest.main()
