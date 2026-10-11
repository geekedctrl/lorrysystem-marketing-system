import os, unittest, secrets, uuid, threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch
import httpx
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text
from marketing_backend.db import Session, engine
from marketing_backend.models import (
    User,
    LoginSession,
    LoginAttempt,
    Workspace,
    Membership,
    Catalog,
    Lead,
    Job,
    now,
)
from marketing_backend.auth import hash_password
from marketing_backend.api import app
from marketing_backend import queue
from marketing_backend.worker import execute
from marketing_backend.research import validate_brief, ProviderFailure

if os.getenv("APP_ENV") != "test" or engine.url.database != "marketing_rebuild_test":
    raise RuntimeError("Tests require the dedicated marketing_rebuild_test database")


class BackendTests(unittest.TestCase):
    def setUp(self):
        with Session() as db:
            for model in (
                Job,
                Lead,
                Catalog,
                Membership,
                LoginSession,
                LoginAttempt,
                Workspace,
                User,
            ):
                db.execute(delete(model))
            self.password = secrets.token_urlsafe(20)
            a = User(
                email="admin@example.test",
                password_hash=hash_password(self.password),
                platform_admin=True,
            )
            b = User(
                email="viewer@example.test", password_hash=hash_password(self.password)
            )
            w = Workspace(name="Fleet")
            other = Workspace(name="Accounting")
            db.add_all([a, b, w, other])
            db.flush()
            self.uid, self.wid, self.other = a.id, w.id, other.id
            db.add_all(
                [
                    Membership(user_id=a.id, workspace_id=w.id, role="ADMIN"),
                    Membership(user_id=b.id, workspace_id=w.id, role="VIEWER"),
                ]
            )
            db.commit()
        self.client = TestClient(app)
        self.token = self.login("admin@example.test")
        self.headers = {"Authorization": "Bearer " + self.token}
        for kind in ("PRODUCT", "ICP"):
            r = self.client.put(
                f"/workspaces/{self.wid}/catalog",
                headers=self.headers,
                json={
                    "kind": kind,
                    "code": kind,
                    "name": kind + " name",
                    "description": "A documented offering or relevant customer segment",
                },
            )
            self.assertEqual(r.status_code, 201)
        r = self.client.post(
            f"/workspaces/{self.wid}/leads",
            headers=self.headers,
            json={
                "company_name": "Example Logistics",
                "website": "https://example.com/",
            },
        )
        self.assertEqual(r.status_code, 201)
        self.lid = uuid.UUID(r.json()["id"])

    def login(self, email):
        r = self.client.post(
            "/auth/login", json={"email": email, "password": self.password}
        )
        self.assertEqual(r.status_code, 200)
        return r.json()["token"]

    def enqueue(self, key="test-research-key"):
        r = self.client.post(
            f"/workspaces/{self.wid}/leads/{self.lid}/research",
            headers=self.headers,
            json={"idempotency_key": key},
        )
        self.assertEqual(r.status_code, 202, r.text)
        return uuid.UUID(r.json()["id"])

    def test_database_isolation_and_worker_permissions(self):
        self.enqueue()
        with Session() as db:
            db.execute(text("SET LOCAL ROLE backend_api"))
            self.assertEqual(list(db.scalars(select(Lead))), [])
            db.execute(
                text("SELECT set_config('app.workspace_id',:wid,true)"),
                {"wid": str(self.wid)},
            )
            self.assertEqual(len(list(db.scalars(select(Lead)))), 1)
            db.execute(
                text("SELECT set_config('app.workspace_id',:wid,true)"),
                {"wid": str(self.other)},
            )
            self.assertEqual(list(db.scalars(select(Lead))), [])
        with Session() as db:
            db.execute(text("SET LOCAL ROLE backend_worker"))
            self.assertEqual(len(list(db.scalars(select(Job)))), 1)
            with self.assertRaises(Exception):
                db.execute(select(User))

    def test_auth_workspace_and_roles(self):
        self.assertEqual(self.client.get("/workspaces").status_code, 401)
        self.assertEqual(
            self.client.get(
                f"/workspaces/{self.other}/catalog", headers=self.headers
            ).status_code,
            404,
        )
        viewer = {"Authorization": "Bearer " + self.login("viewer@example.test")}
        self.assertEqual(
            self.client.get(
                f"/workspaces/{self.wid}/catalog", headers=viewer
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                f"/workspaces/{self.wid}/leads/{self.lid}/research",
                headers=viewer,
                json={"idempotency_key": "viewer-request"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post("/auth/logout", headers=self.headers).status_code, 204
        )
        self.assertEqual(
            self.client.get("/workspaces", headers=self.headers).status_code, 401
        )

    def test_idempotency_snapshot_and_foreign_job(self):
        jid = self.enqueue()
        self.assertEqual(jid, self.enqueue())
        self.assertEqual(
            self.client.get(
                f"/workspaces/{self.other}/jobs/{jid}", headers=self.headers
            ).status_code,
            404,
        )
        with Session() as db:
            job = db.get(Job, jid)
            self.assertEqual(len(job.payload["context"]), 2)
        response = self.client.post(
            f"/workspaces/{self.wid}/leads/{self.lid}/research",
            headers=self.headers,
            json={"idempotency_key": "different-key"},
        )
        self.assertEqual(response.status_code, 409)

    def test_deactivated_workspace_rejects_inflight_result(self):
        jid = self.enqueue()
        with Session() as db:
            job = queue.claim(db)
            token = job.lease_token
            db.get(Workspace, self.wid).active = False
            db.commit()
        with Session() as db:
            with self.assertRaises(queue.LeaseLost):
                queue.complete(db, jid, token, {"stale": True})

    def test_concurrent_claims_only_one_owner(self):
        jid = self.enqueue()
        barrier = threading.Barrier(2)

        def claim():
            barrier.wait()
            with Session() as db:
                job = queue.claim(db)
                return job.id if job else None

        with ThreadPoolExecutor(2) as workers:
            values = list(workers.map(lambda _: claim(), range(2)))
        self.assertEqual(values.count(jid), 1)
        self.assertEqual(values.count(None), 1)

    def test_expired_lease_no_stale_write_and_bounded_attempts(self):
        jid = self.enqueue()
        with Session() as db:
            job = queue.claim(db)
            token = job.lease_token
            job.lease_until = now() - timedelta(seconds=1)
            job.attempts = 3
            db.commit()
        with Session() as db:
            with self.assertRaises(queue.LeaseLost):
                queue.complete(db, jid, token, {"stale": True})
        with Session() as db:
            self.assertIsNone(queue.claim(db))
            self.assertEqual(db.get(Job, jid).status, "FAILED")
        r = self.client.post(
            f"/workspaces/{self.wid}/jobs/{jid}/retry", headers=self.headers
        )
        self.assertEqual(r.status_code, 202)
        self.assertEqual(
            self.client.post(
                f"/workspaces/{self.wid}/jobs/{jid}/retry", headers=self.headers
            ).status_code,
            409,
        )

    def test_checkpoint_survives_retry_and_reviews_instead_of_sending(self):
        jid = self.enqueue()
        with Session() as db:
            job = queue.claim(db)
        with Session() as db:
            queue.checkpoint(
                db, jid, job.lease_token, {"page": {"text": "Saved evidence"}}
            )
            queue.fail(db, jid, job.lease_token, "MODEL_TEMPORARILY_UNAVAILABLE", True)
            pending = db.get(Job, jid)
            pending.available_at = now()
            db.commit()
        with Session() as db:
            job = queue.claim(db)
        self.assertEqual(job.checkpoint["page"]["text"], "Saved evidence")
        execute(
            job,
            handler=lambda job, save: {
                "facts": [],
                "unknowns": ["Contact not verified"],
            },
        )
        with Session() as db:
            done = db.get(Job, jid)
            self.assertEqual(done.status, "NEEDS_REVIEW")
            self.assertIsNone(done.lease_token)

    def test_native_research_worker_validates_real_provider_contract(self):
        jid = self.enqueue()
        with Session() as db:
            job = queue.claim(db)
        quote = "Example Logistics provides commercial transport and delivery services."
        fact = {
            "category": "SERVICES",
            "statement": "The company provides delivery services.",
            "evidence_quote": quote,
            "confidence": 90,
            "kind": "OBSERVED",
        }
        response = httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": __import__("json").dumps(
                                {"facts": [fact], "unknowns": ["Fleet size unknown"]}
                            )
                        },
                    }
                ]
            },
        )
        with patch.dict(os.environ, {"MODEL_API_KEY": "fixture-only"}), patch(
            "marketing_backend.research.fetch_public",
            return_value={
                "fetch_status": "SUCCESS",
                "final_url": "https://example.com/",
                "body": "<html><p>"
                + quote
                + "</p><p>"
                + ("Public company context " * 10)
                + "</p></html>",
            },
        ) as fetch, patch(
            "marketing_backend.research.httpx.post", return_value=response
        ) as model:
            execute(job)
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(model.call_count, 1)
        with Session() as db:
            done = db.get(Job, jid)
            self.assertEqual(done.status, "NEEDS_REVIEW")
            self.assertEqual(
                done.result["facts"][0]["source_url"], "https://example.com/"
            )

    def test_missing_provider_stops_without_spending(self):
        jid = self.enqueue()
        with Session() as db:
            job = queue.claim(db)
        with patch.dict(os.environ, {"MODEL_API_KEY": ""}), patch(
            "marketing_backend.research.fetch_public"
        ) as fetch:
            execute(job)
            fetch.assert_not_called()
        with Session() as db:
            self.assertEqual(db.get(Job, jid).failure_code, "PROVIDER_NOT_CONFIGURED")

    def test_sources_and_citations_fail_closed(self):
        response = self.client.post(
            f"/workspaces/{self.wid}/leads",
            headers=self.headers,
            json={"company_name": "Internal", "website": "http://127.0.0.1/"},
        )
        self.assertEqual(response.status_code, 422)
        fact = {
            "category": "COMPANY",
            "statement": "An unsupported company statement.",
            "evidence_quote": "Invented quotation",
            "confidence": 100,
            "kind": "OBSERVED",
        }
        with self.assertRaises(ProviderFailure):
            validate_brief(
                {"facts": [fact], "unknowns": []},
                "The public source does not contain that statement.",
            )


if __name__ == "__main__":
    unittest.main()
