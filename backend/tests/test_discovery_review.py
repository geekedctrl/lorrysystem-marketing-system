"""Real PostgreSQL candidate review and bounded synthetic discovery regression."""

import uuid
from datetime import timedelta
from unittest.mock import patch
from sqlalchemy import select, text
import test_native_pipeline as fixtures
from marketing_backend.db import Session
from marketing_backend.models import (
    Lead,
    DiscoveryMemory,
    Job,
    Workspace,
    Membership,
    Catalog,
    PreparationRun,
    now,
)
from marketing_backend.pipeline import fingerprint, context
from marketing_backend.discovery import (
    assess,
    excerpts,
    search_query,
    discovery_queries,
    excluded,
)
from marketing_backend.research import ProviderFailure


class DiscoveryTests(fixtures.BackendFixtures):
    drain = fixtures.NativeTests.drain

    def setUp(self):
        super().setUp()
        with Session() as db:
            workspace = db.get(Workspace, self.wid)
            workspace.automation_enabled = True
            workspace.automation = {
                "discovery_query": "Commercial transport",
                "batch_size": 3,
            }
            db.commit()
        provider = patch(
            "marketing_backend.stages.Providers", fixtures.FixtureProviders
        )
        fetcher = patch(
            "marketing_backend.stages.fetch_public",
            return_value={
                "fetch_status": "SUCCESS",
                "final_url": fixtures.URL,
                "body": "<p>" + fixtures.PAGE + "</p>",
            },
        )
        provider.start()
        fetcher.start()
        self.addCleanup(provider.stop)
        self.addCleanup(fetcher.stop)

    def candidate(self, name="Example Logistics", status="READY_FOR_REVIEW", wid=None):
        wid = wid or self.wid
        with Session() as db:
            row = DiscoveryMemory(
                workspace_id=wid,
                domain="candidate.example.com",
                outcome=status,
                context_hash=fingerprint(context(db, wid)),
                candidate=dict(
                    company_name=name,
                    website="https://candidate.example.com/",
                    source_url="https://candidate.example.com/",
                    evidence_quote=name
                    + " provides commercial transport and delivery services.",
                    prospect_type="FLEET_OPERATOR",
                    icp_code="ICP",
                    confidence=80,
                    industry="Logistics",
                    reasoning="Supported services fit the catalog customer segment.",
                    unknowns=[],
                ),
            )
            db.add(row)
            db.commit()
            return str(row.id)

    def action(self, cid, action, data=None, wid=None, headers=None):
        return self.client.post(
            f"/workspaces/{wid or self.wid}/candidates/{cid}/{action}",
            headers=headers or self.headers,
            json=data if data is not None else {},
        )

    def test_human_accept_is_atomic_idempotent_and_queues_once(self):
        cid = self.candidate()
        self.assertEqual(self.drain(), [])
        first = self.action(cid, "accept")
        self.assertEqual(first.status_code, 200, first.text)
        second = self.action(cid, "accept")
        self.assertEqual(first.json(), second.json())
        with Session() as db:
            row = db.get(DiscoveryMemory, uuid.UUID(cid))
            self.assertEqual(row.reviewed_by, self.uid)
            self.assertIsNotNone(row.reviewed_at)
            self.assertEqual(row.outcome, "ACCEPTED")
            self.assertEqual(
                len(list(db.scalars(select(Job).where(Job.kind == "RESEARCH")))), 1
            )
            self.assertEqual(len(list(db.scalars(select(PreparationRun)))), 1)
        self.assertEqual(
            self.action(cid, "reject", {"note": "Wrong segment"}).status_code, 409
        )

    def test_reject_and_retry_policies_with_no_lead_side_effect(self):
        cid = self.candidate()
        self.assertEqual(self.action(cid, "reject", {"note": "no"}).status_code, 422)
        self.assertEqual(
            self.action(
                cid, "reject", {"note": "Not our customer segment"}
            ).status_code,
            200,
        )
        self.assertEqual(self.action(cid, "accept").status_code, 409)
        self.assertEqual(self.action(cid, "retry").status_code, 409)
        self.assertEqual(self.drain(), [])
        with Session() as db:
            self.assertEqual(
                len(list(db.scalars(select(Lead)))), 1
            )  # Original fixture only.
            row = db.get(DiscoveryMemory, uuid.UUID(cid))
            self.assertTrue(excluded(row, row.context_hash))

    def test_workspace_rls_viewer_and_stale_targeting(self):
        cid = self.candidate()
        viewer = {"Authorization": "Bearer " + self.login("viewer@example.test")}
        self.assertEqual(self.action(cid, "accept", headers=viewer).status_code, 403)
        self.assertEqual(
            self.client.get(
                f"/workspaces/{self.wid}/candidates/{cid}", headers=viewer
            ).status_code,
            200,
        )
        with Session() as db:
            db.add(Membership(user_id=self.uid, workspace_id=self.other, role="ADMIN"))
            db.get(Workspace, self.wid).automation = {
                "discovery_query": "Changed targeting"
            }
            db.commit()
        self.assertEqual(self.action(cid, "accept", wid=self.other).status_code, 404)
        self.assertEqual(
            self.client.get(
                f"/workspaces/{self.other}/candidates", headers=self.headers
            ).json()["items"],
            [],
        )
        self.assertEqual(self.action(cid, "accept").status_code, 409)
        self.assertTrue(
            self.client.get(
                f"/workspaces/{self.wid}/candidates/{cid}", headers=self.headers
            ).json()["stale"]
        )
        with Session() as db:
            db.execute(text("SET LOCAL ROLE backend_api"))
            db.execute(
                text("SELECT set_config('app.workspace_id',:wid,true)"),
                {"wid": str(self.other)},
            )
            self.assertEqual(list(db.scalars(select(DiscoveryMemory))), [])

    def test_concurrent_accept_creates_one_lead_and_job(self):
        from concurrent.futures import ThreadPoolExecutor

        cid = self.candidate()
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(lambda _: self.action(cid, "accept"), range(2)))
        self.assertTrue(
            all(r.status_code == 200 for r in replies), [r.text for r in replies]
        )
        self.assertEqual(replies[0].json(), replies[1].json())
        with Session() as db:
            self.assertEqual(len(list(db.scalars(select(Job)))), 1)

    def test_retry_failed_website_queues_direct_reassessment(self):
        cid = self.candidate(status="FETCH_UNAVAILABLE")
        response = self.action(cid, "retry")
        self.assertEqual(response.status_code, 200, response.text)
        with Session() as db:
            job = db.get(Job, uuid.UUID(response.json()["job_id"]))
            self.assertEqual(job.payload["retry_domain"], "candidate.example.com")
            row = db.get(DiscoveryMemory, uuid.UUID(cid))
            self.assertFalse(excluded(row, row.context_hash))
            row.outcome, row.retry_after = "FETCH_UNAVAILABLE", now() - timedelta(
                seconds=1
            )
            self.assertFalse(excluded(row, row.context_hash))
            row.retry_after = now() + timedelta(hours=1)
            self.assertTrue(excluded(row, row.context_hash))
        with patch.object(
            fixtures.FixtureProviders,
            "search",
            side_effect=AssertionError("A targeted retry must not search Brave"),
        ), patch(
            "marketing_backend.stages.fetch_public",
            return_value={
                "fetch_status": "SUCCESS",
                "final_url": "https://candidate.example.com/",
                "body": "<p>" + fixtures.PAGE + "</p>",
            },
        ):
            self.assertEqual(self.drain(), ["DISCOVERY"])
        with Session() as db:
            self.assertEqual(
                db.get(DiscoveryMemory, uuid.UUID(cid)).outcome, "READY_FOR_REVIEW"
            )

    def test_empty_javascript_shell_reaches_browser_fallback(self):
        with Session() as db:
            db.delete(db.get(Lead, self.lid))
            db.commit()
        with patch(
            "marketing_backend.stages.fetch_public",
            return_value={
                "fetch_status": "SUCCESS",
                "final_url": fixtures.URL,
                "body": "<main></main><script src='/app.js'></script>",
            },
        ), patch(
            "marketing_backend.scraping.browser_enabled", return_value=True
        ), patch(
            "marketing_backend.scraping.render_public",
            return_value="<main><p>" + fixtures.PAGE + "</p></main>",
        ) as browser:
            result = self.client.post(
                f"/workspaces/{self.wid}/discovery",
                headers=self.headers,
                json={"idempotency_key": "javascript-shell-test"},
            )
            self.assertEqual(result.status_code, 202)
            self.assertEqual(self.drain(), ["DISCOVERY"])
            browser.assert_called_once_with(fixtures.URL)
        with Session() as db:
            self.assertEqual(
                db.scalar(select(DiscoveryMemory)).outcome, "READY_FOR_REVIEW"
            )
            self.assertEqual(list(db.scalars(select(Lead))), [])

    def test_one_bad_assessment_does_not_lose_good_company(self):
        urls = ["https://bad.example.com/", "https://good.example.com/"]
        search = lambda *args, **kwargs: [
            {"url": u, "title": "Company", "text": ""} for u in urls
        ]

        def fetch(url):
            name = "Bad Company" if "bad." in url else "Good Company"
            return {
                "fetch_status": "SUCCESS",
                "final_url": url,
                "body": "<p>"
                + name
                + ' provides commercial transport and delivery services. Its public company website describes logistics operations and freight forwarding across the country.</p><a href="https://[broken/about">About</a>',
            }

        def model(provider, operation, instructions, data):
            if "bad." in operation:
                return {"invented": True}
            return dict(
                suitable=True,
                prospect_type="FLEET_OPERATOR",
                company_name="Good Company",
                icp_code="ICP",
                confidence=85,
                official_company=True,
                excerpt_id=data["excerpts"][0]["excerpt_id"],
                industry="Logistics",
                reasoning="Official transport services fit the actual customer segment.",
                unknowns=["Buying intent unknown"],
            )

        with patch.object(
            fixtures.FixtureProviders, "search", side_effect=search
        ), patch.object(fixtures.FixtureProviders, "model", model), patch(
            "marketing_backend.stages.fetch_public", side_effect=fetch
        ):
            r = self.client.post(
                f"/workspaces/{self.wid}/discovery",
                headers=self.headers,
                json={"idempotency_key": "partial-discovery-test"},
            )
            self.assertEqual(r.status_code, 202)
            self.assertEqual(self.drain(), ["DISCOVERY"])
        page = self.client.get(
            f"/workspaces/{self.wid}/candidates", headers=self.headers
        ).json()
        self.assertEqual(page["total"], 2)
        by_domain = {r["domain"]: r for r in page["items"]}
        self.assertEqual(by_domain["good.example.com"]["status"], "READY_FOR_REVIEW")
        self.assertEqual(
            by_domain["good.example.com"]["prospect_type"], "FLEET_OPERATOR"
        )
        self.assertEqual(
            by_domain["bad.example.com"]["failure_reason"],
            "MODEL_OUTPUT_SCHEMA_INVALID",
        )
        with Session() as db:
            self.assertEqual(len(list(db.scalars(select(Lead)))), 1)
            job = db.scalar(select(Job))
            self.assertEqual(job.status, "COMPLETED")
            self.assertEqual(job.result["counts"]["candidates_ready"], 1)

    def test_invalid_assessment_gets_one_repair_attempt(self):
        url = "https://retry.example.com/"
        search = lambda *args, **kwargs: [
            {"url": url, "title": "Retry Transport", "text": ""}
        ]

        def fetch(_url):
            return {
                "fetch_status": "SUCCESS",
                "final_url": url,
                "body": "<p>Retry Transport provides commercial transport and delivery services. "
                "Its company website describes logistics operations across Malaysia.</p>",
            }

        calls = []

        def model(provider, operation, instructions, data):
            calls.append(operation)
            if operation.startswith("discovery:"):
                return {"missing": "required assessment fields"}
            return dict(
                suitable=True,
                prospect_type="LOGISTICS_PROVIDER",
                company_name="Retry Transport",
                icp_code="ICP",
                confidence=80,
                official_company=True,
                excerpt_id=data["excerpts"][0]["excerpt_id"],
                industry="Logistics",
                reasoning="Official company evidence establishes commercial transport services.",
                unknowns=["Buying intent unknown"],
            )

        with patch.object(
            fixtures.FixtureProviders, "search", side_effect=search
        ), patch.object(fixtures.FixtureProviders, "model", model), patch(
            "marketing_backend.stages.fetch_public", side_effect=fetch
        ):
            response = self.client.post(
                f"/workspaces/{self.wid}/discovery",
                headers=self.headers,
                json={"idempotency_key": "assessment-repair-test"},
            )
            self.assertEqual(response.status_code, 202)
            self.assertEqual(self.drain(), ["DISCOVERY"])

        self.assertEqual(
            calls, ["discovery:retry.example.com", "discovery-repair:retry.example.com"]
        )
        candidates = self.client.get(
            f"/workspaces/{self.wid}/candidates", headers=self.headers
        ).json()
        self.assertEqual(candidates["total"], 1)
        self.assertEqual(candidates["items"][0]["domain"], "retry.example.com")

    def test_worker_role_cannot_create_leads(self):
        with Session() as db:
            db.execute(text("SET LOCAL ROLE backend_worker"))
            self.assertFalse(
                db.scalar(
                    text("SELECT has_table_privilege(current_user,'leads','INSERT')")
                )
            )

    def test_manual_company_added_during_discovery_is_not_proposed_again(self):
        from marketing_backend import pipeline

        with Session() as db:
            job = Job(
                workspace_id=self.wid,
                kind="DISCOVERY",
                managed=True,
                idempotency_key="concurrent-company-test",
                payload={"context_hash": fingerprint(context(db, self.wid))},
            )
            db.add(job)
            db.flush()
            value = {
                "company_name": "Example Logistics",
                "website": fixtures.URL,
                "domain": "example.com",
                "source_url": fixtures.URL,
            }
            pipeline.finalize(
                db, job, {"candidates": [value], "counts": {"candidates_ready": 1}}
            )
            db.commit()
            self.assertEqual(db.scalar(select(DiscoveryMemory)).outcome, "KNOWN")
            self.assertEqual(job.result["counts"]["candidates_ready"], 0)
            self.assertEqual(len(list(db.scalars(select(PreparationRun)))), 0)

    def test_numbered_evidence_and_directory_budget(self):
        from marketing_backend.discovery import listing

        self.assertTrue(
            listing({"url": "https://ensun.io/search/transport", "title": "Directory"})
        )
        self.assertFalse(
            listing({"url": "https://operator.com/", "title": "Transport Company"})
        )
        self.assertTrue(
            listing({"url": "https://[broken", "title": "Malformed search result"})
        )
        from marketing_backend.stages import Links

        parser = Links()
        parser.feed('<a href>Broken link</a><a href="/about">About</a>')
        self.assertEqual(parser.links, ["/about"])
        sources = excerpts(
            [
                {
                    "source_url": "https://operator.com/",
                    "text": "Operator Company provides transport services. " * 200,
                }
            ]
        )
        raw = dict(
            suitable=True,
            prospect_type="FLEET_OPERATOR",
            company_name="Operator Company",
            icp_code="ICP",
            confidence=80,
            official_company=True,
            excerpt_id=sources[0]["excerpt_id"],
            industry="Transport",
            reasoning="Supported by the supplied official services.",
            unknowns=[],
        )
        candidate = assess(raw, sources, {"ICP"}, "operator.com")
        self.assertEqual(candidate["evidence_quote"], sources[0]["text"])
        self.assertEqual(candidate["prospect_type"], "FLEET_OPERATOR")
        self.assertIsNone(
            assess(
                {
                    **raw,
                    "prospect_type": "SOFTWARE_VENDOR",
                    "reasoning": "Provides a transit software platform for bus operators.",
                },
                sources,
                {"ICP"},
                "operator.com",
            )
        )
        for field, value in [
            ("excerpt_id", "invented"),
            ("company_name", "Unrelated Company"),
            ("icp_code", "FOREIGN"),
            ("official_company", False),
        ]:
            with self.assertRaises(ProviderFailure):
                assess({**raw, field: value}, sources, {"ICP"}, "operator.com")
        query = search_query(
            "Malaysian transport " * 20, {"operator.com", "bad.com OR secret"}
        )
        self.assertLessEqual(len(query), 400)
        self.assertLessEqual(len(query.split()), 50)
        self.assertNotIn("OR secret", query)
        operator_queries = discovery_queries(
            "Malaysian commercial transport",
            [
                {"kind": "ICP", "name": "Passenger Transport Operators"},
                {"kind": "PRODUCT", "name": "Fleet GPS"},
            ],
            "MY",
            {"operator.com"},
        )
        self.assertEqual(len(operator_queries), 2)
        self.assertTrue(
            all("operator" in q.lower() and "Malaysia" in q for q in operator_queries)
        )

    def test_assessment_requires_a_buyer_or_operator_type(self):
        from marketing_backend.discovery import assess

        source = {
            "excerpt_id": "P1_E1",
            "source_url": "https://optibus.com/",
            "text": "Optibus provides a software platform for public transportation operators.",
        }
        common = dict(
            suitable=True,
            company_name="Optibus",
            icp_code="PASSENGER_TRANSPORT",
            confidence=95,
            official_company=True,
            excerpt_id="P1_E1",
            industry="Public Transportation",
            reasoning="The product serves bus and passenger transport operators.",
            unknowns=[],
        )
        result = assess(
            {**common, "prospect_type": "SOFTWARE_VENDOR"},
            [source],
            {"PASSENGER_TRANSPORT"},
            "optibus.com",
        )
        self.assertIsNone(result)
