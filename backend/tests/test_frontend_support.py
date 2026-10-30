"""Real PostgreSQL coverage of additive frontend contracts and revision/lifecycle guards."""

import copy
import uuid
from unittest.mock import patch
from sqlalchemy import select
from test_backend import BackendFixtures
import test_native_pipeline as fixtures

FixtureProviders, PAGE, URL = fixtures.FixtureProviders, fixtures.PAGE, fixtures.URL
from marketing_backend.db import Session
from marketing_backend.models import (
    Catalog,
    Workspace,
    Lead,
    Approval,
    PreparationRun,
    User,
    Membership,
)
from marketing_backend.auth import hash_password


class FrontendSupportTests(BackendFixtures):
    prepare, drain = fixtures.NativeTests.prepare, fixtures.NativeTests.drain

    def setUp(self):
        super().setUp()
        with Session() as db:
            db.get(Workspace, self.wid).automation_enabled = True
            db.get(Workspace, self.wid).automation = {
                "discovery_query": "Commercial transport",
                "batch_size": 3,
            }
            product = db.scalar(
                select(Catalog).where(
                    Catalog.workspace_id == self.wid, Catalog.kind == "PRODUCT"
                )
            )
            product.description = (
                "Transport scheduling for commercial transport operators"
            )
            reviewer = User(
                email="reviewer@example.test",
                password_hash=hash_password(self.password),
            )
            db.add(reviewer)
            db.flush()
            db.add(
                Membership(workspace_id=self.wid, user_id=reviewer.id, role="REVIEWER")
            )
            db.commit()
        (
            FixtureProviders.people,
            FixtureProviders.opportunity,
            FixtureProviders.ambiguous,
        ) = (True, True, False)
        providers = patch("marketing_backend.stages.Providers", FixtureProviders)
        fetch = patch(
            "marketing_backend.stages.fetch_public",
            return_value={
                "fetch_status": "SUCCESS",
                "final_url": URL,
                "body": "<p>" + PAGE + "</p>",
            },
        )
        providers.start()
        fetch.start()
        self.addCleanup(providers.stop)
        self.addCleanup(fetch.stop)
        self.prefix = f"/workspaces/{self.wid}"

    def pending(self):
        rid = self.prepare()
        self.drain()
        response = self.client.get(self.prefix + "/approvals", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()[0]

    def request_changes(self, approval):
        response = self.client.post(
            self.prefix + f'/approvals/{approval["id"]}/decision',
            headers=self.headers,
            json={
                "decision": "CHANGES_REQUESTED",
                "note": "Please shorten the opening and keep existing GPS context",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)

    def revision_body(self, approval):
        draft = approval["snapshot"]["draft"]
        return {
            "expected_version": approval["version"],
            "idempotency_key": "review-revision-key",
            "subject": "A scheduling conversation",
            "body": draft["body"] + " Happy to share the documented capabilities.",
            "evidence": draft["evidence"],
            "note": "Shortened the opening while retaining evidence",
        }

    def test_typed_user_capabilities_and_revocation(self):
        result = self.client.get("/auth/me", headers=self.headers)
        self.assertTrue(result.json()["capabilities"]["create_workspace"])
        self.assertIn("expires_at", result.json())
        viewer = {"Authorization": "Bearer " + self.login("viewer@example.test")}
        self.assertFalse(
            self.client.get("/auth/me", headers=viewer).json()["capabilities"][
                "create_workspace"
            ]
        )
        schema = self.client.get("/openapi.json").json()
        for name in (
            "LeadPage",
            "StageResults",
            "Operations",
            "ApprovalResponse",
            "CurrentUser",
        ):
            self.assertIn(name, schema["components"]["schemas"])
        self.assertNotIn(
            "lease_token", str(schema["components"]["schemas"]["JobResponse"])
        )
        self.client.post("/auth/logout", headers=viewer)
        self.assertEqual(self.client.get("/auth/me", headers=viewer).status_code, 401)

    def test_detail_and_keyset_pages_beyond_capped_list(self):
        with Session() as db:
            for index in range(115):
                db.add(
                    Lead(
                        workspace_id=self.wid,
                        company_name=f"Paged Company {index:03}",
                        website=f"https://company-{index}.example.com",
                    )
                )
            db.commit()
        seen, cursor, total = [], None, None
        for _ in range(8):
            params = {"limit": 17}
            if cursor:
                params["cursor"] = cursor
            response = self.client.get(
                self.prefix + "/leads/page", headers=self.headers, params=params
            )
            self.assertEqual(response.status_code, 200, response.text)
            value = response.json()
            total = value["total"]
            seen.extend(item["id"] for item in value["items"])
            cursor = value["next_cursor"]
            if not cursor:
                break
        self.assertEqual(total, 116)
        self.assertEqual(len(set(seen)), 116)
        self.assertEqual(len(seen), 116)
        self.assertEqual(
            self.client.get(
                self.prefix + f"/leads/{self.lid}", headers=self.headers
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                f"/workspaces/{self.other}/leads/{self.lid}", headers=self.headers
            ).status_code,
            404,
        )
        filtered = self.client.get(
            self.prefix + "/leads/page",
            headers=self.headers,
            params={"q": "Company 00", "limit": 1},
        ).json()
        self.assertEqual(filtered["total"], 10)
        self.assertEqual(
            self.client.get(
                self.prefix + "/leads/page",
                headers=self.headers,
                params={"q": "Different", "cursor": filtered["next_cursor"]},
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.get(
                self.prefix + "/leads/page",
                headers=self.headers,
                params={"cursor": "not-a-cursor"},
            ).status_code,
            422,
        )

    def test_immutable_revision_idempotency_conflicts_and_separate_reviewer(self):
        parent = self.pending()
        self.request_changes(parent)
        body = self.revision_body(parent)
        path = self.prefix + f'/approvals/{parent["id"]}/revision'
        response = self.client.post(path, headers=self.headers, json=body)
        self.assertEqual(response.status_code, 201, response.text)
        fresh = response.json()
        self.assertFalse(fresh["sent"])
        self.assertEqual(fresh["version"], 2)
        self.assertEqual(
            self.client.post(path, headers=self.headers, json=body).json(), fresh
        )
        changed = {**body, "body": body["body"] + " Changed."}
        self.assertEqual(
            self.client.post(path, headers=self.headers, json=changed).status_code, 409
        )
        changed["idempotency_key"] = "another-revision-key"
        self.assertEqual(
            self.client.post(path, headers=self.headers, json=changed).status_code, 409
        )
        decision = {
            "decision": "APPROVED",
            "note": "Reviewed the new snapshot and recipient",
        }
        decision_path = self.prefix + f'/approvals/{fresh["approval_id"]}/decision'
        self.assertEqual(
            self.client.post(
                decision_path, headers=self.headers, json=decision
            ).status_code,
            403,
        )
        reviewer = {"Authorization": "Bearer " + self.login("reviewer@example.test")}
        self.assertFalse(
            self.client.post(decision_path, headers=reviewer, json=decision).json()[
                "sent"
            ]
        )
        with Session() as db:
            old = db.get(Approval, uuid.UUID(parent["id"]))
            self.assertEqual(old.snapshot, parent["snapshot"])
            self.assertEqual(old.status, "CHANGES_REQUESTED")
            new = db.get(Approval, uuid.UUID(fresh["approval_id"]))
            self.assertEqual(
                new.snapshot["revision"]["reviewer_note"], old.decision["note"]
            )

    def test_revision_rejects_uncited_content_versions_roles_and_stale_context(self):
        parent = self.pending()
        self.request_changes(parent)
        path = self.prefix + f'/approvals/{parent["id"]}/revision'
        body = self.revision_body(parent)
        self.assertEqual(
            self.client.post(
                path, headers=self.headers, json={**body, "expected_version": 9}
            ).status_code,
            409,
        )
        bad = copy.deepcopy(body)
        bad["evidence"][0]["evidence_quote"] = "Not present in the saved source"
        self.assertEqual(
            self.client.post(path, headers=self.headers, json=bad).status_code, 422
        )
        viewer = {"Authorization": "Bearer " + self.login("viewer@example.test")}
        self.assertEqual(
            self.client.post(path, headers=viewer, json=body).status_code, 403
        )
        with Session() as db:
            db.get(Lead, self.lid).company_name = "Changed Company Identity"
            db.commit()
        self.assertEqual(
            self.client.post(path, headers=self.headers, json=body).status_code, 409
        )

    def test_catalog_deactivation_preserves_history_and_reactivation_remains_stale(
        self,
    ):
        approval = self.pending()
        catalog = self.client.get(self.prefix + "/catalog", headers=self.headers).json()
        item = next(c for c in catalog if c["kind"] == "PRODUCT")
        path = self.prefix + f'/catalog/{item["id"]}'
        self.assertEqual(
            self.client.patch(
                path, headers=self.headers, json={"active": False}
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.patch(
                path, headers=self.headers, json={"active": False}
            ).status_code,
            200,
        )
        self.assertTrue(
            self.client.get(self.prefix + "/approvals", headers=self.headers).json()[0][
                "stale"
            ]
        )
        inactive = self.client.get(
            self.prefix + "/catalog/all", headers=self.headers
        ).json()
        self.assertFalse(next(c for c in inactive if c["id"] == item["id"])["active"])
        self.assertFalse(
            self.client.get(self.prefix + "/operations", headers=self.headers).json()[
                "enabled"
            ]
        )
        self.assertEqual(
            self.client.post(
                self.prefix + "/automation/resume", headers=self.headers
            ).status_code,
            409,
        )
        self.client.patch(path, headers=self.headers, json={"active": True})
        self.assertEqual(
            self.client.post(
                self.prefix + "/automation/resume", headers=self.headers
            ).status_code,
            200,
        )
        self.assertIsNotNone(
            self.client.get(self.prefix + "/operations", headers=self.headers).json()[
                "next_discovery_at"
            ]
        )
        self.assertTrue(
            self.client.get(self.prefix + "/approvals", headers=self.headers).json()[0][
                "stale"
            ]
        )
        with Session() as db:
            self.assertEqual(
                db.get(Approval, uuid.UUID(approval["id"])).snapshot,
                approval["snapshot"],
            )
            self.assertEqual(db.get(Catalog, uuid.UUID(item["id"])).context_version, 3)

    def test_setup_noop_upsert_is_safe_while_work_is_pending(self):
        self.prepare()
        item = self.client.get(self.prefix + "/catalog", headers=self.headers).json()[0]
        data = {k: item[k] for k in ("kind", "code", "name", "description", "rules")}
        self.assertEqual(
            self.client.put(
                self.prefix + "/catalog", headers=self.headers, json=data
            ).status_code,
            201,
        )
        data["description"] += " A real change."
        self.assertEqual(
            self.client.put(
                self.prefix + "/catalog", headers=self.headers, json=data
            ).status_code,
            409,
        )
        self.client.post(self.prefix + "/automation/pause", headers=self.headers)
        self.assertEqual(
            self.client.put(
                self.prefix + "/catalog", headers=self.headers, json=data
            ).status_code,
            201,
        )
        run = self.client.get(
            self.prefix + f"/leads/{self.lid}", headers=self.headers
        ).json()["current_preparation"]
        self.assertEqual(run["status"], "FAILED")
        self.assertEqual(run["stop_reason"], "CATALOG_CHANGED")

    def test_independent_scheduler_enqueues_due_discovery(self):
        from marketing_backend.models import now, Job
        from marketing_backend.runner import scheduler_tick
        with Session() as db:
            db.get(Workspace, self.wid).next_discovery_at = now()
            db.commit()
        scheduler_tick()
        with Session() as db:
            job = db.scalar(select(Job).where(Job.kind == "DISCOVERY"))
            self.assertEqual(job.status, "PENDING")
