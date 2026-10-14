import json, os, uuid
from datetime import timedelta
from unittest.mock import patch
from sqlalchemy import select, text
import httpx
from test_backend import BackendFixtures
from marketing_backend.db import Session
from marketing_backend.models import (
    Workspace,
    Catalog,
    Lead,
    Job,
    PreparationRun,
    Approval,
    ProviderUsage,
    Membership,
    DiscoveryMemory,
    now,
)
from marketing_backend import queue, pipeline
from marketing_backend.worker import execute
from marketing_backend.providers import Providers
from marketing_backend.research import ProviderFailure

URL = "https://example.com/"
SERVICE = "Example Logistics provides commercial transport and delivery services."
NEED = "Example Logistics reports delayed deliveries and manual route planning."
SIGNAL = "Example Logistics is seeking a new transport scheduling system."
PERSON = "Alex Worker is Operations Director. Contact Alex Worker at alex@example.com."
PAGE = " ".join(
    [
        SERVICE,
        NEED,
        SIGNAL,
        PERSON,
        "The company uses GPS for existing vehicle tracking.",
    ]
)


def citation(quote):
    return {"source_url": URL, "evidence_quote": quote}


class FixtureProviders:
    """Deterministic synthetic provider; stage validation and DB transitions stay real."""

    people = True
    opportunity = True
    ambiguous = False
    keyed_scoring = False
    quote_alias_scoring = False
    invalid_contact_roles = False

    def __init__(self, job, save):
        self.job, self.save, self.cache = job, save, dict(job.checkpoint)

    def ready(self, search=False):
        pass

    def remember(self, key, value):
        self.cache[key] = value
        self.save(self.cache)
        return value

    def search(self, operation, query, **options):
        if operation.startswith("discovery"):
            return [{"url": URL, "title": "Example Logistics", "text": SERVICE}]
        if self.ambiguous and operation.endswith("linkedin"):
            return [
                {
                    "url": f"https://www.linkedin.com/in/alex-{n}",
                    "title": "Alex Worker — Example Logistics",
                    "text": "Operations Director",
                }
                for n in (1, 2)
            ]
        return []

    def model(self, operation, instructions, data):
        if operation == "setup":
            return {
                "discovery_query": "Commercial transport businesses Malaysia",
                "icps": [],
            }
        if operation.startswith("discovery:"):
            return dict(
                suitable=True,
                prospect_type="FLEET_OPERATOR",
                company_name="Example Logistics",
                icp_code="ICP",
                confidence=90,
                official_company=True,
                excerpt_id=data["excerpts"][0]["excerpt_id"],
                industry="Logistics",
                reasoning="Public company services fit the transport customer segment.",
                unknowns=["Buying intent unknown"],
            )
        if operation == "research":
            facts = [
                dict(
                    category="SERVICES",
                    statement="Provides transport and delivery.",
                    kind="OBSERVED",
                    confidence=90,
                    **citation(SERVICE),
                )
            ]
            if self.opportunity:
                facts += [
                    dict(
                        category=category,
                        statement=quote,
                        kind="OBSERVED",
                        confidence=90,
                        **citation(quote),
                    )
                    for category, quote in [("PAIN_POINT", NEED), ("SIGNAL", SIGNAL)]
                ]
            people = (
                [
                    dict(
                        name="Alex Worker",
                        role=(
                            None
                            if self.invalid_contact_roles
                            else "Operations Director"
                        ),
                        email=None if self.ambiguous else "alex@example.com",
                        phone=None,
                        **citation(PERSON),
                    )
                ]
                if self.people
                else []
            )
            return {"facts": facts, "people": people, "unknowns": []}
        if operation == "scoring":
            criteria = [
                dict(
                    criterion=c,
                    points=p,
                    rationale="Supported by supplied company evidence.",
                    evidence=[citation(q)] if p else [],
                )
                for c, p, q in [
                    ("icp_fit", 40, SERVICE),
                    ("operational_need", 30, NEED),
                    ("operating_scale", 0, SERVICE),
                    ("buying_signals", 10, SIGNAL),
                    ("evidence_quality", 5, SERVICE),
                ]
            ]
            if self.keyed_scoring:
                return {
                    item["criterion"]: {
                        key: value for key, value in item.items() if key != "criterion"
                    }
                    for item in criteria
                }
            if self.quote_alias_scoring:
                for item in criteria:
                    item["evidence"] = [
                        {"source_url": e["source_url"], "quote": e["evidence_quote"]}
                        for e in item["evidence"]
                    ]
            return {
                "criteria": criteria,
                "unknowns": ["Operating scale not established"],
            }
        if operation == "matching":
            products = data["products"]
            return {
                "matches": [
                    dict(
                        product_code=c,
                        fit=85 if "transport" in p["description"].lower() else 0,
                        rationale="Compared against actual product capability.",
                        evidence=[citation(SERVICE)],
                    )
                    for c, p in products.items()
                ]
            }
        if operation == "drafting":
            return {
                "subject": "Transport scheduling discussion",
                "body": "Hello Alex, your public site describes transport and delivery services. Would it be useful to discuss scheduling alongside your existing GPS system?",
                "evidence": [citation(SERVICE)],
            }
        raise AssertionError(operation)


class NativeTests(BackendFixtures):
    def setUp(self):
        super().setUp()
        with Session() as db:
            workspace = db.get(Workspace, self.wid)
            workspace.automation_enabled = True
            workspace.automation = {
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
            db.commit()
        self.provider = patch("marketing_backend.stages.Providers", FixtureProviders)
        self.fetcher = patch(
            "marketing_backend.stages.fetch_public",
            return_value={
                "fetch_status": "SUCCESS",
                "final_url": URL,
                "body": "<p>" + PAGE + "</p>",
            },
        )
        (
            FixtureProviders.people,
            FixtureProviders.opportunity,
            FixtureProviders.ambiguous,
            FixtureProviders.keyed_scoring,
            FixtureProviders.quote_alias_scoring,
            FixtureProviders.invalid_contact_roles,
        ) = (True, True, False, False, False, False)
        self.provider.start()
        self.fetcher.start()
        self.addCleanup(self.provider.stop)
        self.addCleanup(self.fetcher.stop)

    def prepare(self, key="native-prepare-key", wid=None, lid=None):
        r = self.client.post(
            f"/workspaces/{wid or self.wid}/leads/{lid or self.lid}/prepare",
            headers=self.headers,
            json={"idempotency_key": key},
        )
        self.assertEqual(r.status_code, 202, r.text)
        return uuid.UUID(r.json()["run_id"])

    def test_prepare_inherits_icp_from_accepted_discovery(self):
        with Session() as db:
            db.add(
                Catalog(
                    workspace_id=self.wid,
                    kind="ICP",
                    code="AAA_FIRST_ALPHABETICALLY",
                    name="A different segment",
                    description="Another documented customer segment",
                    rules={},
                    active=True,
                )
            )
            db.add(
                DiscoveryMemory(
                    workspace_id=self.wid,
                    domain="its4logistics.com",
                    candidate={"icp_code": "ICP", "prospect_type": "LOGISTICS_PROVIDER"},
                    outcome="ACCEPTED",
                    accepted_lead_id=self.lid,
                )
            )
            db.flush()
            run = pipeline.start(db, db.get(Lead, self.lid), "accepted-icp-test")
            research = db.scalar(
                select(Job).where(Job.run_id == run.id, Job.kind == "RESEARCH")
            )
            self.assertEqual(research.payload["icp_code"], "ICP")

    def drain(self, maximum=12):
        completed = []
        for _ in range(maximum):
            with Session() as db:
                job = queue.claim(db)
            if not job:
                return completed
            execute(job)
            completed.append(job.kind)
        self.fail("Pipeline did not drain within its bounded stages")

    def test_complete_preparation_pending_immutable_approval(self):
        rid = self.prepare()
        self.assertEqual(rid, self.prepare())
        self.assertEqual(self.drain(), list(pipeline.STAGES))
        with Session() as db:
            run = db.get(PreparationRun, rid)
            self.assertEqual(run.status, "PENDING_APPROVAL")
            self.assertEqual(run.results["SCORING"]["score"], 85)
            approval = db.scalar(select(Approval).where(Approval.run_id == rid))
            aid = approval.id
            snapshot = approval.snapshot
            self.assertEqual(approval.status, "PENDING")
            db.execute(text("SET LOCAL ROLE backend_worker"))
            with self.assertRaises(Exception):
                db.execute(
                    text("UPDATE approvals SET status='APPROVED' WHERE id=:id"),
                    {"id": aid},
                )
        r = self.client.post(
            f"/workspaces/{self.wid}/approvals/{aid}/decision",
            headers=self.headers,
            json={
                "decision": "APPROVED",
                "note": "Reviewed synthetic content and recipient",
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["sent"])
        with Session() as db:
            self.assertEqual(db.get(Approval, aid).snapshot, snapshot)
            self.assertEqual(db.get(PreparationRun, rid).status, "APPROVED")
            with self.assertRaises(Exception):
                db.execute(
                    text("UPDATE approvals SET snapshot='{}' WHERE id=:id"), {"id": aid}
                )

    def test_keyed_model_scoring_output_is_normalized_to_rubric_contract(self):
        FixtureProviders.keyed_scoring = True
        rid = self.prepare("keyed-scoring-output")
        self.assertEqual(self.drain(), list(pipeline.STAGES))
        with Session() as db:
            run = db.get(PreparationRun, rid)
            self.assertEqual(run.status, "PENDING_APPROVAL")
            score = run.results["SCORING"]
            self.assertEqual(
                [item["criterion"] for item in score["criteria"]],
                ["icp_fit", "operational_need", "operating_scale", "buying_signals", "evidence_quality"],
            )
            self.assertEqual(score["score"], 85)
            self.assertEqual(score["unknowns"], [])

    def test_scoring_citation_quote_alias_is_normalized(self):
        FixtureProviders.quote_alias_scoring = True
        rid = self.prepare("quote-alias-scoring-output")
        self.assertEqual(self.drain(), list(pipeline.STAGES))
        with Session() as db:
            run = db.get(PreparationRun, rid)
            self.assertEqual(run.status, "PENDING_APPROVAL")
            score = run.results["SCORING"]
            self.assertEqual(score["score"], 85)
            self.assertEqual(
                score["criteria"][0]["evidence"][0]["evidence_quote"], SERVICE
            )

    def test_capability_does_not_create_opportunity(self):
        FixtureProviders.opportunity = False
        rid = self.prepare()
        self.assertEqual(self.drain(), ["RESEARCH", "CONTACT_SEARCH", "SCORING"])
        with Session() as db:
            run = db.get(PreparationRun, rid)
            self.assertEqual(run.results["SCORING"]["score"], 45)
            self.assertEqual(run.results["SCORING"]["opportunity"], 0)
            self.assertEqual(run.stop_reason, "QUALIFICATION_BELOW_POLICY")
            self.assertEqual(list(db.scalars(select(Approval))), [])

    def test_contact_gap_and_ambiguous_profile_resolution(self):
        FixtureProviders.ambiguous = True
        rid = self.prepare()
        self.assertEqual(self.drain(), ["RESEARCH", "CONTACT_SEARCH"])
        with Session() as db:
            run = db.get(PreparationRun, rid)
            self.assertEqual(run.stop_reason, "SUPPORTED_CONTACT_REQUIRED")
            self.assertEqual(
                len(run.results["CONTACT_SEARCH"]["people"][0]["profile_candidates"]), 2
            )
        wrong = self.client.post(
            f"/workspaces/{self.wid}/preparation/{rid}/contact",
            headers=self.headers,
            json={
                "person_index": 0,
                "profile_url": "https://www.linkedin.com/in/unverified",
            },
        )
        self.assertEqual(wrong.status_code, 422)
        ok = self.client.post(
            f"/workspaces/{self.wid}/preparation/{rid}/contact",
            headers=self.headers,
            json={
                "person_index": 0,
                "profile_url": "https://www.linkedin.com/in/alex-1",
            },
        )
        self.assertEqual(ok.status_code, 202, ok.text)
        self.assertEqual(self.drain(), ["SCORING", "MATCHING", "DRAFTING"])
        with Session() as db:
            run = db.get(PreparationRun, rid)
            self.assertEqual(run.results["DRAFTING"]["channel"], "LINKEDIN")

    def test_missing_people_stops_honestly(self):
        FixtureProviders.people = False
        rid = self.prepare()
        self.drain()
        with Session() as db:
            self.assertEqual(
                db.get(PreparationRun, rid).stop_reason, "SUPPORTED_CONTACT_REQUIRED"
            )
            self.assertEqual(list(db.scalars(select(Approval))), [])

    def test_unqualified_model_contacts_do_not_discard_research(self):
        FixtureProviders.invalid_contact_roles = True
        rid = self.prepare("invalid-contact-role")
        self.assertEqual(self.drain(), ["RESEARCH", "CONTACT_SEARCH"])
        with Session() as db:
            run = db.get(PreparationRun, rid)
            research = run.results["RESEARCH"]
            self.assertTrue(research["facts"])
            self.assertEqual(research["people"], [])
            self.assertTrue(
                any("contacts were omitted" in note for note in research["unknowns"])
            )
            self.assertEqual(run.stop_reason, "SUPPORTED_CONTACT_REQUIRED")

    def test_manual_source_backed_contact_resumes_existing_research(self):
        FixtureProviders.people = False
        rid = self.prepare()
        self.drain()
        r = self.client.post(
            f"/workspaces/{self.wid}/preparation/{rid}/contact",
            headers=self.headers,
            json={
                "business_contact": {
                    "name": "Alex Worker",
                    "role": "Operations Director",
                    "email": "alex@example.com",
                    "phone": None,
                    **citation(PERSON),
                }
            },
        )
        self.assertEqual(r.status_code, 202, r.text)
        self.assertEqual(self.drain(), ["SCORING", "MATCHING", "DRAFTING"])
        with Session() as db:
            self.assertEqual(db.get(PreparationRun, rid).status, "PENDING_APPROVAL")

    def test_deeper_page_checkpoint_and_unsupported_quotes(self):
        rid = self.prepare()

        def fetched(url):
            return {
                "fetch_status": "SUCCESS",
                "final_url": url,
                "body": "<p>"
                + PAGE
                + '</p><a href="/team">Team</a><a href="/contact">Contact</a><a href="http://127.0.0.1/">Internal</a>',
            }

        with patch(
            "marketing_backend.stages.fetch_public", side_effect=fetched
        ) as fetch:
            with Session() as db:
                job = queue.claim(db)
            execute(job)
            self.assertEqual(fetch.call_count, 3)
        with Session() as db:
            run = db.get(PreparationRun, rid)
            self.assertEqual(run.results["RESEARCH"]["coverage"]["pages_attempted"], 3)
            self.assertEqual(
                sum(k.startswith("page:") for k in db.get(Job, job.id).checkpoint), 3
            )

    def test_research_bounds_extra_contacts_and_drops_unsupported_facts(self):
        rid = self.prepare()

        class NoisyResearchProviders(FixtureProviders):
            def model(provider, operation, instructions, data):
                value = super(NoisyResearchProviders, provider).model(
                    operation, instructions, data
                )
                if operation == "research":
                    value["people"] = value["people"] * 6
                    value["people"][1] = {
                        **value["people"][1],
                        "evidence_quote": "This person's name and role are not sourced.",
                    }
                    value["people"][2] = {
                        **value["people"][2],
                        "email": "unverified@example.com",
                    }
                    value["facts"].append(
                        {
                            "category": "SERVICES",
                            "statement": "An unsupported service claim.",
                            "kind": "OBSERVED",
                            "confidence": 95,
                            **citation("This quote is not on the company website."),
                        }
                    )
                return value

        def fetched(url):
            return {
                "fetch_status": "SUCCESS",
                "final_url": url,
                "body": "<p>" + PAGE + "</p>",
            }

        with patch(
            "marketing_backend.stages.Providers", NoisyResearchProviders
        ), patch("marketing_backend.stages.fetch_public", side_effect=fetched):
            with Session() as db:
                job = queue.claim(db)
            execute(job)

        with Session() as db:
            run = db.get(PreparationRun, rid)
            research = run.results["RESEARCH"]
            self.assertEqual(run.status, "PREPARING")
            self.assertEqual(len(research["people"]), 4)
            self.assertIsNone(research["people"][1]["email"])
            self.assertEqual(len(research["facts"]), 3)
            self.assertTrue(
                any("omitted" in value for value in research["unknowns"])
            )
            contact_job = db.scalar(
                select(Job).where(
                    Job.run_id == rid,
                    Job.kind == "CONTACT_SEARCH",
                )
            )
            self.assertEqual(contact_job.status, "PENDING")

    def test_stale_context_cannot_save_or_approve(self):
        rid = self.prepare()
        with Session() as db:
            job = queue.claim(db)
            db.get(Workspace, self.wid).automation = {
                "discovery_query": "Changed targeting"
            }
            db.commit()
        execute(job)
        with Session() as db:
            self.assertEqual(db.get(Job, job.id).failure_code, "CONTEXT_CHANGED")
            self.assertEqual(db.get(PreparationRun, rid).status, "FAILED")
        r = self.client.post(
            f"/workspaces/{self.wid}/jobs/{job.id}/retry", headers=self.headers
        )
        self.assertEqual(r.status_code, 409)

    def test_company_identity_edit_invalidates_prepared_draft(self):
        rid = self.prepare()
        self.drain()
        with Session() as db:
            aid = db.scalar(select(Approval.id).where(Approval.run_id == rid))
            db.get(Lead, self.lid).company_name = "Changed company identity"
            db.commit()
        rows = self.client.get(
            f"/workspaces/{self.wid}/approvals", headers=self.headers
        ).json()
        self.assertTrue(rows[0]["stale"])
        response = self.client.post(
            f"/workspaces/{self.wid}/approvals/{aid}/decision",
            headers=self.headers,
            json={
                "decision": "APPROVED",
                "note": "Attempted review after identity changed",
            },
        )
        self.assertEqual(response.status_code, 409)
        with Session() as db:
            db.get(Lead, self.lid).company_name = "Example Logistics"
            db.commit()
        rid = self.prepare("fresh-native-request")
        self.drain()
        with Session() as db:
            approval = db.scalar(select(Approval).where(Approval.run_id == rid))
            aid = approval.id
        r = self.client.put(
            f"/workspaces/{self.wid}/catalog",
            headers=self.headers,
            json={
                "kind": "PRODUCT",
                "code": "PRODUCT",
                "name": "Updated offering",
                "description": "Changed transport scheduling capabilities",
            },
        )
        self.assertEqual(r.status_code, 201)
        r = self.client.post(
            f"/workspaces/{self.wid}/approvals/{aid}/decision",
            headers=self.headers,
            json={"decision": "APPROVED", "note": "Attempted review of stale inputs"},
        )
        self.assertEqual(r.status_code, 409)

    def test_pause_blocks_inflight_and_resumes_without_spending_loop(self):
        rid = self.prepare()
        with Session() as db:
            job = queue.claim(db)
        self.assertEqual(
            self.client.post(
                f"/workspaces/{self.wid}/automation/pause", headers=self.headers
            ).status_code,
            200,
        )
        execute(job)
        with Session() as db:
            self.assertEqual(db.get(Job, job.id).failure_code, "PRODUCT_PAUSED")
            self.assertIsNone(queue.claim(db))
        self.assertEqual(
            self.client.post(
                f"/workspaces/{self.wid}/automation/resume", headers=self.headers
            ).status_code,
            200,
        )
        with Session() as db:
            self.assertIsNone(queue.claim(db))
        self.assertEqual(
            self.client.post(
                f"/workspaces/{self.wid}/jobs/{job.id}/retry", headers=self.headers
            ).status_code,
            202,
        )
        self.drain()
        with Session() as db:
            self.assertEqual(db.get(PreparationRun, rid).status, "PENDING_APPROVAL")

    def test_discovery_memory_and_empty_repeat_batch(self):
        # Remove the existing fixture lead so discovery can create it atomically.
        with Session() as db:
            db.delete(db.get(Lead, self.lid))
            db.commit()
        r = self.client.post(
            f"/workspaces/{self.wid}/discovery",
            headers=self.headers,
            json={"idempotency_key": "discovery-test-key"},
        )
        self.assertEqual(r.status_code, 202, r.text)
        self.assertEqual(self.drain(), ["DISCOVERY"])
        candidates = self.client.get(
            f"/workspaces/{self.wid}/candidates", headers=self.headers
        ).json()["items"]
        self.assertEqual(candidates[0]["status"], "READY_FOR_REVIEW")
        with Session() as db:
            self.assertEqual(len(list(db.scalars(select(Lead)))), 0)
            self.assertEqual(len(list(db.scalars(select(PreparationRun)))), 0)
        accepted = self.client.post(
            f"/workspaces/{self.wid}/candidates/{candidates[0]['id']}/accept",
            headers=self.headers,
            json={},
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(self.drain(), list(pipeline.STAGES))
        r = self.client.post(
            f"/workspaces/{self.wid}/discovery",
            headers=self.headers,
            json={"idempotency_key": "discovery-second-key"},
        )
        self.assertEqual(r.status_code, 202, r.text)
        self.assertEqual(self.drain(), ["DISCOVERY"])
        with Session() as db:
            self.assertEqual(len(list(db.scalars(select(Lead)))), 1)
            self.assertEqual(len(list(db.scalars(select(DiscoveryMemory)))), 1)
            self.assertEqual(len(list(db.scalars(select(Approval)))), 1)

    def test_two_unrelated_products_isolate_matching_and_rls(self):
        with Session() as db:
            other = db.get(Workspace, self.other)
            other.automation_enabled = True
            other.automation = {"discovery_query": "Accounting business"}
            db.add(Membership(user_id=self.uid, workspace_id=self.other, role="ADMIN"))
            for kind in ("PRODUCT", "ICP"):
                db.add(
                    Catalog(
                        workspace_id=self.other,
                        kind=kind,
                        code=kind,
                        name="Accounting " + kind,
                        description="Accounting invoice automation and reconciliation",
                    )
                )
            lead = Lead(
                workspace_id=self.other, company_name="Example Logistics", website=URL
            )
            db.add(lead)
            db.commit()
            lid = lead.id
        first = self.prepare()
        second = self.prepare("accounting-preparation", self.other, lid)
        self.drain()
        with Session() as db:
            self.assertEqual(db.get(PreparationRun, first).status, "PENDING_APPROVAL")
            self.assertEqual(
                db.get(PreparationRun, second).stop_reason, "NO_SUPPORTED_PRODUCT_MATCH"
            )
            db.execute(text("SET LOCAL ROLE backend_api"))
            db.execute(
                text("SELECT set_config('app.workspace_id',:wid,true)"),
                {"wid": str(self.other)},
            )
            self.assertEqual(len(list(db.scalars(select(PreparationRun)))), 1)
            self.assertEqual(list(db.scalars(select(Approval))), [])

    def test_six_companies_across_two_catalogs_reach_pending_approval(self):
        class BatchProviders(FixtureProviders):
            def model(provider, operation, instructions, data):
                raw = super(BatchProviders, provider).model(
                    operation, instructions, data
                )
                accounting = provider.job.workspace_id == self.other
                if operation == "matching" and accounting:
                    for match in raw["matches"]:
                        match["fit"] = 85
                encoded = (
                    json.dumps(raw)
                    .replace(URL, provider.job.payload.get("website", URL))
                    .replace(
                        "Example Logistics",
                        provider.job.payload.get("company_name", "Example Logistics"),
                    )
                )
                if accounting:
                    encoded = (
                        encoded.replace(
                            "commercial transport and delivery services",
                            "invoice processing and reconciliation services",
                        )
                        .replace(
                            "delayed deliveries and manual route planning",
                            "delayed reconciliation and manual invoice processing",
                        )
                        .replace(
                            "new transport scheduling system",
                            "new accounting automation system",
                        )
                        .replace("Operations Director", "Finance Director")
                        .replace(
                            "Transport scheduling discussion",
                            "Invoice reconciliation discussion",
                        )
                        .replace(
                            "transport and delivery services",
                            "invoice processing services",
                        )
                        .replace("existing GPS system", "existing accounting system")
                    )
                return json.loads(encoded)

        companies = {}
        with Session() as db:
            db.delete(db.get(Lead, self.lid))
            other = db.get(Workspace, self.other)
            other.automation_enabled = True
            other.automation = {"discovery_query": "Accounting businesses"}
            db.add(Membership(user_id=self.uid, workspace_id=self.other, role="ADMIN"))
            for kind in ("PRODUCT", "ICP"):
                db.add(
                    Catalog(
                        workspace_id=self.other,
                        kind=kind,
                        code=kind,
                        name="Accounting " + kind,
                        description="Accounting invoice processing and reconciliation",
                    )
                )
            for wid in (self.wid, self.other):
                for n, host in enumerate(("example.com", "example.org", "example.net")):
                    lead = Lead(
                        workspace_id=wid,
                        company_name=f'Synthetic {"Accounting" if wid==self.other else "Fleet"} {n}',
                        website=f"https://{host}/",
                    )
                    db.add(lead)
                    db.flush()
                    companies[lead.id] = (wid, lead.company_name, lead.website)
            db.commit()

        def fetched(url):
            company = next(
                name
                for wid, name, site in companies.values()
                if site == url and wid == current[0]
            )
            page = PAGE.replace("Example Logistics", company)
            if current[0] == self.other:
                page = (
                    page.replace(
                        "commercial transport and delivery services",
                        "invoice processing and reconciliation services",
                    )
                    .replace(
                        "delayed deliveries and manual route planning",
                        "delayed reconciliation and manual invoice processing",
                    )
                    .replace(
                        "new transport scheduling system",
                        "new accounting automation system",
                    )
                    .replace("Operations Director", "Finance Director")
                )
            return {
                "fetch_status": "SUCCESS",
                "final_url": url,
                "body": "<p>" + page + "</p>",
            }

        for lid, (wid, name, url) in companies.items():
            current = [wid]
            rid = self.prepare("batch-" + str(lid), wid, lid)
            with patch("marketing_backend.stages.Providers", BatchProviders), patch(
                "marketing_backend.stages.fetch_public", side_effect=fetched
            ):
                self.drain()
            with Session() as db:
                self.assertEqual(db.get(PreparationRun, rid).status, "PENDING_APPROVAL")
        with Session() as db:
            approvals = list(db.scalars(select(Approval)))
            self.assertEqual(len(approvals), 6)
            self.assertTrue(all(a.status == "PENDING" for a in approvals))

    def test_atomic_transition_rolls_back_and_duplicate_completion_rejected(self):
        rid = self.prepare()
        with Session() as db:
            job = queue.claim(db)
        with patch(
            "marketing_backend.pipeline.next_job",
            side_effect=RuntimeError("synthetic transaction failure"),
        ):
            execute(job, handler=lambda *_: {"facts": []})
        with Session() as db:
            self.assertEqual(db.get(PreparationRun, rid).results, {})
            self.assertEqual(db.get(Job, job.id).status, "FAILED")
        self.assertEqual(
            self.client.post(
                f"/workspaces/{self.wid}/jobs/{job.id}/retry", headers=self.headers
            ).status_code,
            202,
        )
        self.drain()
        with Session() as db:
            with self.assertRaises(queue.LeaseLost):
                queue.complete(db, job.id, job.lease_token, {"duplicate": True})
            self.assertEqual(len(list(db.scalars(select(Approval)))), 1)

    def test_native_chain_uses_actual_restricted_worker_database_role(self):
        from contextlib import contextmanager

        rid = self.prepare()

        @contextmanager
        def restricted():
            from marketing_backend.db import engine

            with engine.connect() as connection:
                connection.execute(text("SET ROLE backend_worker"))
                connection.commit()
                try:
                    with Session(bind=connection) as db:
                        yield db
                finally:
                    connection.rollback()
                    connection.execute(text("RESET ROLE"))
                    connection.commit()

        for _ in range(5):
            with restricted() as db:
                job = queue.claim(db)
            self.assertIsNotNone(job)
            with patch("marketing_backend.worker.Session", restricted), patch(
                "marketing_backend.stages.Session", restricted
            ):
                execute(job)
        with Session() as db:
            self.assertEqual(db.get(PreparationRun, rid).status, "PENDING_APPROVAL")
            self.assertEqual(len(list(db.scalars(select(Approval)))), 1)

    def test_setup_admin_only_and_scheduler_enqueues_once(self):
        viewer = {"Authorization": "Bearer " + self.login("viewer@example.test")}
        payload = {
            "idempotency_key": "activate-test-product",
            "product_description": "Transport planning for commercial operators",
        }
        r = self.client.post(
            f"/workspaces/{self.wid}/automation/activate", headers=viewer, json=payload
        )
        self.assertEqual(r.status_code, 403)
        r = self.client.post(
            f"/workspaces/{self.wid}/automation/activate",
            headers=self.headers,
            json=payload,
        )
        self.assertEqual(r.status_code, 202, r.text)
        self.assertEqual(self.drain(), ["SETUP"])
        with Session() as db:
            pipeline.schedule(db)
            pipeline.schedule(db)
            self.assertEqual(
                len(list(db.scalars(select(Job).where(Job.kind == "DISCOVERY")))), 1
            )

    def test_retry_contact_search_reuses_research_and_is_idempotent_while_pending(self):
        class NoEmail(FixtureProviders):
            def model(provider, operation, instructions, data):
                raw = super(NoEmail, provider).model(operation, instructions, data)
                if operation == "research":
                    raw["people"][0]["email"] = None
                return raw

        rid = self.prepare()
        with patch("marketing_backend.stages.Providers", NoEmail):
            self.drain()
        for _ in range(2):
            response = self.client.post(
                f"/workspaces/{self.wid}/preparation/{rid}/retry-contact-search",
                headers=self.headers,
            )
            self.assertEqual(response.status_code, 202, response.text)

        def profiles(provider, operation, query):
            return (
                [
                    {
                        "url": "https://www.linkedin.com/in/alex-worker",
                        "title": "Alex Worker — Example Logistics",
                        "text": "Operations Director",
                    }
                ]
                if operation.endswith("linkedin")
                else []
            )

        with patch.object(FixtureProviders, "search", profiles):
            self.assertEqual(
                self.drain(), ["CONTACT_SEARCH", "SCORING", "MATCHING", "DRAFTING"]
            )
        with Session() as db:
            self.assertEqual(db.get(PreparationRun, rid).status, "PENDING_APPROVAL")

    def test_database_rejects_job_bound_to_different_lead_in_same_workspace(self):
        rid = self.prepare()
        with Session() as db:
            lead = Lead(
                workspace_id=self.wid,
                company_name="Different company",
                website="https://example.org/",
            )
            db.add(lead)
            db.flush()
            job = Job(
                workspace_id=self.wid,
                lead_id=lead.id,
                run_id=rid,
                kind="SCORING",
                managed=True,
                idempotency_key="wrong-run-lead-job",
                payload={},
            )
            db.add(job)
            with self.assertRaises(Exception):
                db.flush()

    def test_reservation_budget_and_provider_checkpoint_contract(self):
        self.provider.stop()
        self.prepare()
        with Session() as db:
            job = queue.claim(db)

        def save(value):
            with Session() as db:
                queue.checkpoint(db, job.id, job.lease_token, value)

        provider = Providers(job, save)
        response = httpx.Response(
            200,
            json={
                "choices": [
                    {"finish_reason": "stop", "message": {"content": '{"ok":true}'}}
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )
        with patch.dict(
            os.environ,
            {
                "MODEL_API_KEY": "fixture-only",
                "MODEL_INPUT_USD_PER_MILLION": "1",
                "MODEL_OUTPUT_USD_PER_MILLION": "1",
                "PROVIDER_MONTHLY_BUDGET_USD": "1",
            },
        ), patch(
            "marketing_backend.providers.httpx.post", return_value=response
        ) as request:
            self.assertEqual(
                provider.model(
                    "fixture", "Synthetic instructions", {"data": "Synthetic"}
                ),
                {"ok": True},
            )
            self.assertEqual(
                provider.model(
                    "fixture", "Synthetic instructions", {"data": "Synthetic"}
                ),
                {"ok": True},
            )
            self.assertEqual(request.call_count, 1)
            self.assertEqual(
                request.call_args.kwargs["json"]["response_format"],
                {"type": "json_object"},
            )
        with Session() as db:
            row = db.scalar(select(ProviderUsage))
            self.assertEqual(row.status, "SUCCESS")
            self.assertEqual(row.usage["prompt_tokens"], 10)
        with patch.dict(os.environ, {"PROVIDER_MONTHLY_BUDGET_USD": "0"}):
            with self.assertRaises(ProviderFailure) as error:
                provider.reserve("MODEL", "exhausted", 1)
            self.assertEqual(error.exception.code, "PROVIDER_BUDGET_EXHAUSTED")

    def test_provider_configuration_and_throttling_stop_before_extra_calls(self):
        self.provider.stop()
        rid = self.prepare()
        with Session() as db:
            job = queue.claim(db)
        with patch.dict(os.environ, {"MODEL_API_KEY": ""}), patch(
            "marketing_backend.providers.httpx.post"
        ) as model, patch("marketing_backend.stages.fetch_public") as fetch:
            execute(job)
            model.assert_not_called()
            fetch.assert_not_called()
        with Session() as db:
            self.assertEqual(
                db.get(Job, job.id).failure_code, "PROVIDER_NOT_CONFIGURED"
            )
        self.assertEqual(
            self.client.post(
                f"/workspaces/{self.wid}/jobs/{job.id}/retry", headers=self.headers
            ).status_code,
            202,
        )
        with Session() as db:
            job = queue.claim(db)

        def save(value):
            with Session() as db:
                queue.checkpoint(db, job.id, job.lease_token, value)

        provider = Providers(job, save)
        with patch.dict(
            os.environ,
            {"BRAVE_SEARCH_API_KEY": "fixture-only", "SEARCH_USD_PER_REQUEST": "0.01"},
        ), patch(
            "marketing_backend.providers.httpx.get", return_value=httpx.Response(429)
        ) as request:
            with self.assertRaises(ProviderFailure) as error:
                provider.search("rate-limited", "Synthetic company query")
            self.assertTrue(error.exception.retryable)
            self.assertEqual(request.call_count, 1)
            self.assertEqual(
                request.call_args.kwargs["headers"]["Accept"], "application/json"
            )
        with Session() as db:
            self.assertEqual(db.scalar(select(ProviderUsage)).status, "REJECTED")

    def test_failed_model_retry_discards_invalid_output_but_keeps_sources(self):
        self.prepare()
        with Session() as db:
            job = queue.claim(db)
            queue.checkpoint(
                db,
                job.id,
                job.lease_token,
                {
                    "page:fixture": {"text": "Saved public source"},
                    "model:research": {"invalid": True},
                },
            )
            queue.fail(db, job.id, job.lease_token, "UNSUPPORTED_CITATION")
        self.assertEqual(
            self.client.post(
                f"/workspaces/{self.wid}/jobs/{job.id}/retry", headers=self.headers
            ).status_code,
            202,
        )
        with Session() as db:
            self.assertIn("page:fixture", db.get(Job, job.id).checkpoint)
            self.assertNotIn("model:research", db.get(Job, job.id).checkpoint)
