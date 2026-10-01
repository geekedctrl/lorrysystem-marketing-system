#!/usr/bin/env python3
"""
LorrySystem Lead Candidate API validator for migration 008.

Run inside the marketing-api container with PYTHONPATH=/app.
The script uses the API for behavior tests and the application's own
SQLAlchemy session only for integrity verification and cleanup.

No API key value is printed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, inspect, select, text

from app.db.session import SessionLocal, engine
from app.models.catalog import ICPProfile
from app.models.companies import Company, Contact
from app.models.discovery import LeadCandidate, LeadCandidateSource
from app.models.leads import Lead
from app.models.marketing import Event


EXPECTED_ALEMBIC_HEAD = "008"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"


class Validator:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.pass_count = 0
        self.fail_count = 0
        self.skip_count = 0
        self.stage = "PRECHECK"
        self.stage_counts: dict[str, dict[str, int]] = defaultdict(
            lambda: {"PASS": 0, "FAIL": 0, "SKIP": 0}
        )

        self.candidate_ids: set[UUID] = set()
        self.company_ids: set[UUID] = set()
        self.lead_ids: set[UUID] = set()
        self.tag = uuid4().hex[:12]

        self.icp_id: UUID | None = None

    # ========================================================
    # Result helpers
    # ========================================================

    def set_stage(self, stage: str) -> None:
        self.stage = stage

    def pass_(self, name: str, detail: str = "") -> None:
        self.pass_count += 1
        self.stage_counts[self.stage]["PASS"] += 1
        suffix = f" — {detail}" if detail else ""
        print(f"[PASS] [{self.stage}] {name}{suffix}")

    def fail(self, name: str, detail: str = "") -> None:
        self.fail_count += 1
        self.stage_counts[self.stage]["FAIL"] += 1
        suffix = f" — {detail}" if detail else ""
        print(f"[FAIL] [{self.stage}] {name}{suffix}")

    def skip(self, name: str, detail: str = "") -> None:
        self.skip_count += 1
        self.stage_counts[self.stage]["SKIP"] += 1
        suffix = f" — {detail}" if detail else ""
        print(f"[SKIP] [{self.stage}] {name}{suffix}")

    def assert_true(
        self,
        name: str,
        condition: bool,
        detail: str = "",
    ) -> bool:
        if condition:
            self.pass_(name, detail)
            return True

        self.fail(name, detail)
        return False

    def assert_http(
        self,
        name: str,
        code: int,
        expected: int | tuple[int, ...],
        payload: Any = None,
    ) -> bool:
        expected_codes = (
            expected
            if isinstance(expected, tuple)
            else (expected,)
        )

        return self.assert_true(
            name,
            code in expected_codes,
            (
                f"HTTP {code}, expected {expected_codes}; "
                f"response={self._short(payload)}"
            ),
        )

    @staticmethod
    def _short(value: Any, limit: int = 700) -> str:
        rendered = repr(value)
        if len(rendered) > limit:
            return rendered[:limit] + "...<truncated>"
        return rendered

    # ========================================================
    # HTTP
    # ========================================================

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        authenticated: bool = True,
    ) -> tuple[int, Any]:
        data = None
        headers: dict[str, str] = {}

        if authenticated:
            headers["X-API-Key"] = self.api_key

        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers=headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(
                req,
                timeout=20,
            ) as response:
                raw = response.read().decode("utf-8")
                payload = json.loads(raw) if raw else None
                return response.status, payload

        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            try:
                payload = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                payload = raw
            return exc.code, payload

        except Exception as exc:
            return 0, {"error": repr(exc)}

    def get(self, path: str, **kwargs) -> tuple[int, Any]:
        return self.request("GET", path, **kwargs)

    def post(
        self,
        path: str,
        body: dict[str, Any] | None = None,
        **kwargs,
    ) -> tuple[int, Any]:
        return self.request("POST", path, body, **kwargs)

    def patch(
        self,
        path: str,
        body: dict[str, Any] | None = None,
        **kwargs,
    ) -> tuple[int, Any]:
        return self.request("PATCH", path, body, **kwargs)

    # ========================================================
    # Payload builders
    # ========================================================

    def source(
        self,
        suffix: str,
        *,
        source_type: str = "COMPANY_WEBSITE",
    ) -> dict[str, Any]:
        return {
            "source_type": source_type,
            "url": f"https://sources-{self.tag}.example/{suffix}",
            "title": f"Candidate validator source {suffix}",
            "source_query": "haulage company Selangor",
            "summary": "Public business evidence for candidate validation.",
            "evidence": "Operates commercial fleet and logistics services.",
        }

    def candidate_payload(
        self,
        suffix: str,
        *,
        confidence: float,
        domain: str | None = None,
        company_name: str | None = None,
        website_url: str | None = None,
        email: str | None = None,
        contact_name: str | None = None,
        source: dict[str, Any] | None = None,
        icp_id: UUID | None = None,
    ) -> dict[str, Any]:
        actual_domain = (
            domain
            or f"candidate-{suffix}-{self.tag}.example"
        )
        actual_website = (
            website_url
            if website_url is not None
            else f"https://{actual_domain}"
        )

        return {
            "company_name": (
                company_name
                or f"Candidate Validator {suffix} {self.tag}"
            ),
            "website_url": actual_website,
            "domain": actual_domain,
            "industry": "Logistics",
            "country_code": "MY",
            "state": "Selangor",
            "city": "Shah Alam",
            "contact_name": contact_name,
            "job_title": "Fleet Manager",
            "email": email,
            "phone": None,
            "linkedin_url": None,
            "suggested_icp_profile_id": str(
                icp_id or self.icp_id
            ),
            "icp_confidence": confidence,
            "icp_reasoning": (
                "Public evidence identifies commercial logistics "
                "and fleet operations."
            ),
            "fleet_clues": [
                "commercial vehicle fleet",
                "haulage operations",
            ],
            "buying_signals": [
                "fleet expansion",
            ],
            "source_summary": (
                "Candidate API validator evidence."
            ),
            "source": (
                source
                or self.source(
                    f"{suffix}-initial"
                )
            ),
        }

    # ========================================================
    # DB helpers
    # ========================================================

    def load_icp(self) -> bool:
        with SessionLocal() as db:
            icp = db.scalar(
                select(ICPProfile).where(
                    ICPProfile.code
                    == "LOGISTICS_HAULAGE",
                    ICPProfile.active.is_(True),
                )
            )

            if icp is None:
                self.fail(
                    "Active LOGISTICS_HAULAGE ICP exists",
                    "No active ICP row found.",
                )
                return False

            self.icp_id = icp.id

        self.pass_(
            "Active LOGISTICS_HAULAGE ICP exists",
            str(self.icp_id),
        )
        return True

    def db_company_by_domain(
        self,
        domain: str,
    ) -> Company | None:
        with SessionLocal() as db:
            return db.scalar(
                select(Company).where(
                    Company.domain == domain
                )
            )

    def db_candidate(
        self,
        candidate_id: UUID,
    ) -> LeadCandidate | None:
        with SessionLocal() as db:
            return db.get(
                LeadCandidate,
                candidate_id,
            )

    def db_events(
        self,
        entity_id: UUID,
    ) -> list[str]:
        with SessionLocal() as db:
            return list(
                db.scalars(
                    select(Event.event_type)
                    .where(Event.entity_id == entity_id)
                    .order_by(Event.created_at.asc())
                ).all()
            )

    # ========================================================
    # Precheck / database integrity
    # ========================================================

    def precheck(self) -> None:
        self.set_stage("PRECHECK")

        code, payload = self.get(
            "/openapi.json",
            authenticated=False,
        )
        self.assert_http(
            "OpenAPI reachable",
            code,
            200,
            payload,
        )

        expected_routes = {
            "/api/candidates": {"get", "post"},
            "/api/candidates/{candidate_id}": {
                "get",
                "patch",
            },
            "/api/candidates/{candidate_id}/sources": {
                "post",
            },
            "/api/candidates/{candidate_id}/accept": {
                "post",
            },
            "/api/candidates/{candidate_id}/reject": {
                "post",
            },
        }

        if code == 200 and isinstance(payload, dict):
            paths = payload.get("paths", {})
            for route, methods in expected_routes.items():
                actual = set(paths.get(route, {}).keys())
                self.assert_true(
                    f"Route methods: {route}",
                    actual == methods,
                    (
                        f"expected={sorted(methods)}, "
                        f"actual={sorted(actual)}"
                    ),
                )

        code, payload = self.get(
            "/api/candidates",
            authenticated=False,
        )
        self.assert_http(
            "Candidate API rejects missing key",
            code,
            401,
            payload,
        )

        code, payload = self.get(
            "/api/candidates?limit=1",
        )
        self.assert_http(
            "Candidate API accepts configured key",
            code,
            200,
            payload,
        )

        self.load_icp()

    def database_checks(self) -> None:
        self.set_stage("DATABASE")

        inspector = inspect(engine)
        tables = set(inspector.get_table_names())

        self.assert_true(
            "Table exists: lead_candidates",
            "lead_candidates" in tables,
        )
        self.assert_true(
            "Table exists: lead_candidate_sources",
            "lead_candidate_sources" in tables,
        )

        with SessionLocal() as db:
            version = db.scalar(
                text(
                    "SELECT version_num "
                    "FROM alembic_version"
                )
            )

            self.assert_true(
                "Alembic head is 008",
                version == EXPECTED_ALEMBIC_HEAD,
                f"version={version}",
            )

            constraints = set(
                db.scalars(
                    text(
                        """
                        SELECT conname
                        FROM pg_constraint
                        WHERE conrelid IN (
                            'lead_candidates'::regclass,
                            'lead_candidate_sources'::regclass
                        )
                        """
                    )
                ).all()
            )

            for name in (
                "ck_lead_candidates_status",
                "ck_lead_candidates_icp_confidence_range",
                "ck_lead_candidate_sources_type",
                "uq_lead_candidate_sources_candidate_url",
            ):
                self.assert_true(
                    f"Constraint exists: {name}",
                    name in constraints,
                )

            indexes = dict(
                db.execute(
                    text(
                        """
                        SELECT indexname, indexdef
                        FROM pg_indexes
                        WHERE schemaname = 'public'
                          AND tablename = 'lead_candidates'
                        """
                    )
                ).all()
            )

            for name in (
                "idx_lead_candidates_status",
                "idx_lead_candidates_created_at",
                "idx_lead_candidates_normalized_name",
                "idx_lead_candidates_active_domain_unique",
                "idx_lead_candidates_active_website_unique",
            ):
                self.assert_true(
                    f"Index exists: {name}",
                    name in indexes,
                )

            domain_def = indexes.get(
                "idx_lead_candidates_active_domain_unique",
                "",
            )
            self.assert_true(
                "Active-domain candidate index is unique + partial",
                (
                    "UNIQUE INDEX" in domain_def
                    and "WHERE" in domain_def
                    and "READY_FOR_REVIEW" in domain_def
                    and "NEEDS_REVIEW" in domain_def
                ),
                domain_def,
            )

    # ========================================================
    # Schema / threshold tests
    # ========================================================

    def threshold_and_schema_tests(self) -> None:
        self.set_stage("THRESHOLDS")

        # SEARCH_RESULT may be captured as discovery evidence,
        # but it cannot be the only evidence used to create a candidate.
        payload = self.candidate_payload(
            "search-only",
            confidence=0.90,
            source=self.source(
                "search-only",
                source_type="SEARCH_RESULT",
            ),
        )

        code, response = self.post(
            "/api/candidates",
            payload,
        )
        self.assert_http(
            "SEARCH_RESULT-only candidate rejected",
            code,
            422,
            response,
        )

        payload = self.candidate_payload(
            "bad-confidence",
            confidence=1.20,
        )
        code, response = self.post(
            "/api/candidates",
            payload,
        )
        self.assert_http(
            "Confidence above 1.0 rejected",
            code,
            422,
            response,
        )

        payload = self.candidate_payload(
            "bad-source-type",
            confidence=0.90,
        )
        payload["source"]["source_type"] = "SOCIAL_PRIVATE"

        code, response = self.post(
            "/api/candidates",
            payload,
        )
        self.assert_http(
            "Unsupported source type rejected",
            code,
            422,
            response,
        )

        payload = self.candidate_payload(
            "bad-icp",
            confidence=0.90,
            icp_id=uuid4(),
        )
        code, response = self.post(
            "/api/candidates",
            payload,
        )
        self.assert_http(
            "Unknown ICP rejected",
            code,
            404,
            response,
        )

        # Medium confidence candidate.
        payload = self.candidate_payload(
            "medium",
            confidence=0.65,
        )
        code, response = self.post(
            "/api/candidates",
            payload,
        )

        if self.assert_http(
            "Medium-confidence candidate created",
            code,
            201,
            response,
        ):
            candidate = response.get("candidate") or {}
            candidate_id = UUID(candidate["id"])
            self.candidate_ids.add(candidate_id)

            self.assert_true(
                "Medium confidence -> NEEDS_REVIEW",
                candidate.get("status")
                == "NEEDS_REVIEW",
                str(candidate.get("status")),
            )

            code2, rejected = self.post(
                f"/api/candidates/{candidate_id}/reject",
                {
                    "reviewed_by": "candidate-validator",
                    "review_notes": (
                        "Medium confidence rejection test."
                    ),
                },
            )

            if self.assert_http(
                "Reviewable candidate can be rejected",
                code2,
                200,
                rejected,
            ):
                self.assert_true(
                    "Rejected candidate status",
                    rejected.get("status") == "REJECTED",
                    str(rejected.get("status")),
                )

        # Weak confidence candidate is recorded as rejected discovery.
        payload = self.candidate_payload(
            "weak",
            confidence=0.30,
        )
        code, response = self.post(
            "/api/candidates",
            payload,
        )

        if self.assert_http(
            "Weak-confidence discovery recorded",
            code,
            201,
            response,
        ):
            candidate = response.get("candidate") or {}
            candidate_id = UUID(candidate["id"])
            self.candidate_ids.add(candidate_id)

            self.assert_true(
                "Weak confidence -> REJECTED",
                candidate.get("status") == "REJECTED",
                str(candidate.get("status")),
            )

            code2, attempt = self.post(
                f"/api/candidates/{candidate_id}/accept",
                {
                    "reviewed_by": "candidate-validator",
                    "priority": "MEDIUM",
                },
            )

            self.assert_http(
                "Rejected weak candidate cannot be accepted",
                code2,
                409,
                attempt,
            )

    # ========================================================
    # Main candidate lifecycle
    # ========================================================

    def main_candidate_flow(self) -> None:
        self.set_stage("CANDIDATE_FLOW")

        email = f"candidate-{self.tag}@example.com"
        domain = f"strong-{self.tag}.example"

        payload = self.candidate_payload(
            "strong",
            confidence=0.91,
            domain=domain,
            website_url=f"https://{domain}/",
            email=email,
            # Intentionally no name: migration 007 behavior.
            contact_name=None,
        )

        code, response = self.post(
            "/api/candidates",
            payload,
        )

        if not self.assert_http(
            "Strong candidate created",
            code,
            201,
            response,
        ):
            return

        self.assert_true(
            "Strong candidate outcome NEW_CANDIDATE",
            response.get("outcome") == "NEW_CANDIDATE",
            str(response.get("outcome")),
        )

        candidate = response.get("candidate") or {}
        candidate_id = UUID(candidate["id"])
        self.candidate_ids.add(candidate_id)

        self.assert_true(
            "Strong confidence -> READY_FOR_REVIEW",
            candidate.get("status") == "READY_FOR_REVIEW",
            str(candidate.get("status")),
        )
        self.assert_true(
            "Candidate domain normalized",
            candidate.get("domain") == domain,
            str(candidate.get("domain")),
        )
        self.assert_true(
            "Candidate website normalized",
            candidate.get("normalized_website")
            == f"https://{domain}",
            str(candidate.get("normalized_website")),
        )

        code, detail = self.get(
            f"/api/candidates/{candidate_id}"
        )

        if self.assert_http(
            "Candidate detail readable",
            code,
            200,
            detail,
        ):
            sources = detail.get("sources") or []
            self.assert_true(
                "Initial source retained",
                len(sources) == 1,
                f"source_count={len(sources)}",
            )

        # Duplicate candidate should enrich the existing candidate.
        duplicate_payload = self.candidate_payload(
            "strong-second",
            confidence=0.86,
            domain=domain,
            company_name=payload["company_name"],
            website_url=f"https://{domain}",
            source=self.source(
                "strong-directory",
                source_type="PUBLIC_DIRECTORY",
            ),
        )

        code, duplicate_response = self.post(
            "/api/candidates",
            duplicate_payload,
        )

        if self.assert_http(
            "Duplicate candidate request handled",
            code,
            200,
            duplicate_response,
        ):
            self.assert_true(
                "Duplicate outcome EXISTING_CANDIDATE",
                duplicate_response.get("outcome")
                == "EXISTING_CANDIDATE",
                str(duplicate_response.get("outcome")),
            )
            merged = (
                duplicate_response.get("candidate")
                or {}
            )
            self.assert_true(
                "Duplicate merged into same candidate",
                merged.get("id") == str(candidate_id),
                f"id={merged.get('id')}",
            )

        # Add third source explicitly.
        news_source = self.source(
            "strong-news",
            source_type="NEWS",
        )
        code, source_response = self.post(
            f"/api/candidates/{candidate_id}/sources",
            news_source,
        )

        self.assert_http(
            "Additional source added",
            code,
            201,
            source_response,
        )

        code, duplicate_source = self.post(
            f"/api/candidates/{candidate_id}/sources",
            news_source,
        )

        self.assert_http(
            "Duplicate source rejected",
            code,
            409,
            duplicate_source,
        )

        # Detail should now contain three sources.
        code, detail = self.get(
            f"/api/candidates/{candidate_id}"
        )
        if self.assert_http(
            "Candidate detail after enrichment",
            code,
            200,
            detail,
        ):
            sources = detail.get("sources") or []
            self.assert_true(
                "Source history preserved",
                len(sources) == 3,
                f"source_count={len(sources)}",
            )

        # Edit candidate.
        code, updated = self.patch(
            f"/api/candidates/{candidate_id}",
            {
                "city": "Port Klang",
                "source_summary": (
                    "Updated during candidate API validation."
                ),
            },
        )

        if self.assert_http(
            "Candidate edit succeeds",
            code,
            200,
            updated,
        ):
            self.assert_true(
                "Edited city persisted",
                updated.get("city") == "Port Klang",
                str(updated.get("city")),
            )

        # Pagination/list filter while the candidate is still reviewable.
        code, listing = self.get(
            "/api/candidates"
            "?status=READY_FOR_REVIEW&limit=100&offset=0"
        )
        if self.assert_http(
            "Candidate list/filter works",
            code,
            200,
            listing,
        ):
            ids = {
                item.get("id")
                for item in listing
                if isinstance(item, dict)
            }
            self.assert_true(
                "Reviewable candidate appears in filtered list",
                str(candidate_id) in ids,
                f"count={len(listing)}",
            )

        # Accept. This must atomically create Company, nameless Contact,
        # DISCOVERED Lead, and mark candidate ACCEPTED.
        code, accepted = self.post(
            f"/api/candidates/{candidate_id}/accept",
            {
                "reviewed_by": "candidate-validator",
                "priority": "HIGH",
                "review_notes": (
                    "Accepted by candidate validator."
                ),
            },
        )

        if not self.assert_http(
            "Candidate accept succeeds",
            code,
            200,
            accepted,
        ):
            return

        self.assert_true(
            "Accept outcome ACCEPTED",
            accepted.get("outcome") == "ACCEPTED",
            str(accepted.get("outcome")),
        )

        accepted_candidate = (
            accepted.get("candidate") or {}
        )
        lead_id = UUID(accepted["lead_id"])
        self.lead_ids.add(lead_id)

        self.assert_true(
            "Candidate transitioned to ACCEPTED",
            accepted_candidate.get("status")
            == "ACCEPTED",
            str(accepted_candidate.get("status")),
        )
        self.assert_true(
            "Candidate stores accepted lead",
            accepted_candidate.get("accepted_lead_id")
            == str(lead_id),
            str(
                accepted_candidate.get(
                    "accepted_lead_id"
                )
            ),
        )

        company_id_text = accepted_candidate.get(
            "existing_company_id"
        )
        if company_id_text:
            company_id = UUID(company_id_text)
            self.company_ids.add(company_id)
        else:
            self.fail(
                "Accepted candidate linked to company",
                "existing_company_id is null",
            )
            return

        code, lead = self.get(
            f"/api/leads/{lead_id}"
        )

        if self.assert_http(
            "Accepted Lead readable",
            code,
            200,
            lead,
        ):
            self.assert_true(
                "Accepted Lead starts DISCOVERED",
                lead.get("status") == "DISCOVERED",
                str(lead.get("status")),
            )
            self.assert_true(
                "Accepted Lead priority preserved",
                lead.get("priority") == "HIGH",
                str(lead.get("priority")),
            )
            self.assert_true(
                "Accepted Lead uses candidate ICP",
                lead.get("icp_profile_id")
                == str(self.icp_id),
                str(lead.get("icp_profile_id")),
            )

            contact_id = lead.get(
                "primary_contact_id"
            )

            self.assert_true(
                "Meaningful contact created",
                contact_id is not None,
                str(contact_id),
            )

            if contact_id:
                code2, contact = self.get(
                    f"/api/contacts/{contact_id}"
                )
                if self.assert_http(
                    "Accepted contact readable",
                    code2,
                    200,
                    contact,
                ):
                    self.assert_true(
                        "Contact without name accepted",
                        contact.get("full_name") is None,
                        str(contact.get("full_name")),
                    )
                    self.assert_true(
                        "Contact email preserved",
                        contact.get("email") == email,
                        str(contact.get("email")),
                    )

        code, company = self.get(
            f"/api/companies/{company_id}"
        )

        if self.assert_http(
            "Accepted company readable",
            code,
            200,
            company,
        ):
            self.assert_true(
                "Discovery-created company source type",
                company.get("source_type")
                == "AI_DISCOVERY",
                str(company.get("source_type")),
            )

        # Terminal candidate cannot be accepted again.
        code, second_accept = self.post(
            f"/api/candidates/{candidate_id}/accept",
            {
                "reviewed_by": "candidate-validator",
                "priority": "HIGH",
            },
        )
        self.assert_http(
            "Accepted candidate cannot be accepted twice",
            code,
            409,
            second_accept,
        )

        # Event traceability.
        candidate_events = set(
            self.db_events(candidate_id)
        )
        for event_type in (
            "lead_candidate_created",
            "lead_candidate_source_added",
            "lead_candidate_updated",
            "lead_candidate_accepted",
        ):
            self.assert_true(
                f"Candidate event exists: {event_type}",
                event_type in candidate_events,
                repr(sorted(candidate_events)),
            )

        lead_events = set(
            self.db_events(lead_id)
        )
        self.assert_true(
            "Lead discovered event exists",
            "lead_discovered" in lead_events,
            repr(sorted(lead_events)),
        )

    # ========================================================
    # Existing company / active lead / race duplicate
    # ========================================================

    def company_and_duplicate_tests(self) -> None:
        self.set_stage("DEDUP")

        # ----------------------------------------------------
        # Existing company without active Lead
        # ----------------------------------------------------
        domain = f"existing-company-{self.tag}.example"

        code, company = self.post(
            "/api/companies",
            {
                "name": (
                    f"Existing Candidate Company {self.tag}"
                ),
                "website_url": f"https://{domain}",
                "domain": domain,
                "industry": "Logistics",
                "country_code": "MY",
                "state": "Selangor",
                "city": "Klang",
                "source_type": "VALIDATOR",
            },
        )

        if self.assert_http(
            "Existing-company fixture created",
            code,
            201,
            company,
        ):
            company_id = UUID(company["id"])
            self.company_ids.add(company_id)

            payload = self.candidate_payload(
                "existing-company",
                confidence=0.82,
                domain=domain,
                company_name=company["name"],
                website_url=f"https://{domain}",
            )

            code2, result = self.post(
                "/api/candidates",
                payload,
            )

            if self.assert_http(
                "Candidate can reference existing company",
                code2,
                201,
                result,
            ):
                self.assert_true(
                    "Outcome EXISTING_COMPANY",
                    result.get("outcome")
                    == "EXISTING_COMPANY",
                    str(result.get("outcome")),
                )

                candidate = result.get("candidate") or {}
                candidate_id = UUID(candidate["id"])
                self.candidate_ids.add(candidate_id)

                self.assert_true(
                    "existing_company_id linked",
                    candidate.get(
                        "existing_company_id"
                    )
                    == str(company_id),
                    str(
                        candidate.get(
                            "existing_company_id"
                        )
                    ),
                )

                code3, rejected = self.post(
                    f"/api/candidates/{candidate_id}/reject",
                    {
                        "reviewed_by": (
                            "candidate-validator"
                        ),
                        "review_notes": (
                            "Existing-company reject test."
                        ),
                    },
                )
                self.assert_http(
                    "Existing-company candidate reject",
                    code3,
                    200,
                    rejected,
                )

        # ----------------------------------------------------
        # Existing active Lead: no candidate should be created
        # ----------------------------------------------------
        active_domain = (
            f"existing-active-{self.tag}.example"
        )

        code, company = self.post(
            "/api/companies",
            {
                "name": (
                    f"Existing Active Lead Company {self.tag}"
                ),
                "website_url": (
                    f"https://{active_domain}"
                ),
                "domain": active_domain,
                "industry": "Logistics",
                "country_code": "MY",
                "source_type": "VALIDATOR",
            },
        )

        if self.assert_http(
            "Active-lead company fixture created",
            code,
            201,
            company,
        ):
            company_id = UUID(company["id"])
            self.company_ids.add(company_id)

            code2, lead = self.post(
                "/api/leads",
                {
                    "company_id": str(company_id),
                    "icp_profile_id": str(self.icp_id),
                    "priority": "MEDIUM",
                },
            )

            if self.assert_http(
                "Active-lead fixture created",
                code2,
                201,
                lead,
            ):
                lead_id = UUID(lead["id"])
                self.lead_ids.add(lead_id)

                payload = self.candidate_payload(
                    "existing-active",
                    confidence=0.90,
                    domain=active_domain,
                    company_name=company["name"],
                    website_url=(
                        f"https://{active_domain}"
                    ),
                )

                code3, result = self.post(
                    "/api/candidates",
                    payload,
                )

                if self.assert_http(
                    "Existing active Lead short-circuits candidate",
                    code3,
                    200,
                    result,
                ):
                    self.assert_true(
                        "Outcome EXISTING_ACTIVE_LEAD",
                        result.get("outcome")
                        == "EXISTING_ACTIVE_LEAD",
                        str(result.get("outcome")),
                    )
                    self.assert_true(
                        "No candidate created for active Lead",
                        result.get("candidate") is None,
                        repr(result.get("candidate")),
                    )
                    self.assert_true(
                        "Existing Lead ID returned",
                        result.get("existing_lead_id")
                        == str(lead_id),
                        str(
                            result.get(
                                "existing_lead_id"
                            )
                        ),
                    )

        # ----------------------------------------------------
        # Lead created after candidate, before review:
        # accept should mark candidate DUPLICATE.
        # ----------------------------------------------------
        race_domain = f"race-{self.tag}.example"

        code, company = self.post(
            "/api/companies",
            {
                "name": (
                    f"Candidate Race Company {self.tag}"
                ),
                "website_url": f"https://{race_domain}",
                "domain": race_domain,
                "industry": "Logistics",
                "country_code": "MY",
                "source_type": "VALIDATOR",
            },
        )

        if self.assert_http(
            "Race company fixture created",
            code,
            201,
            company,
        ):
            company_id = UUID(company["id"])
            self.company_ids.add(company_id)

            payload = self.candidate_payload(
                "race",
                confidence=0.90,
                domain=race_domain,
                company_name=company["name"],
                website_url=f"https://{race_domain}",
            )

            code2, result = self.post(
                "/api/candidates",
                payload,
            )

            if self.assert_http(
                "Race candidate created first",
                code2,
                201,
                result,
            ):
                candidate = result.get("candidate") or {}
                candidate_id = UUID(candidate["id"])
                self.candidate_ids.add(candidate_id)

                code3, lead = self.post(
                    "/api/leads",
                    {
                        "company_id": str(company_id),
                        "icp_profile_id": (
                            str(self.icp_id)
                        ),
                        "priority": "MEDIUM",
                    },
                )

                if self.assert_http(
                    "Lead created after candidate",
                    code3,
                    201,
                    lead,
                ):
                    lead_id = UUID(lead["id"])
                    self.lead_ids.add(lead_id)

                    code4, accepted = self.post(
                        f"/api/candidates/{candidate_id}/accept",
                        {
                            "reviewed_by": (
                                "candidate-validator"
                            ),
                            "priority": "MEDIUM",
                        },
                    )

                    if self.assert_http(
                        "Accept handles newly-created duplicate Lead",
                        code4,
                        200,
                        accepted,
                    ):
                        self.assert_true(
                            "Accept outcome DUPLICATE",
                            accepted.get("outcome")
                            == "DUPLICATE",
                            str(
                                accepted.get(
                                    "outcome"
                                )
                            ),
                        )
                        candidate_result = (
                            accepted.get(
                                "candidate"
                            )
                            or {}
                        )
                        self.assert_true(
                            "Candidate status DUPLICATE",
                            candidate_result.get(
                                "status"
                            )
                            == "DUPLICATE",
                            str(
                                candidate_result.get(
                                    "status"
                                )
                            ),
                        )
                        self.assert_true(
                            "Duplicate Lead linked",
                            candidate_result.get(
                                "duplicate_lead_id"
                            )
                            == str(lead_id),
                            str(
                                candidate_result.get(
                                    "duplicate_lead_id"
                                )
                            ),
                        )

    # ========================================================
    # Atomic rollback test
    # ========================================================

    def atomicity_test(self) -> None:
        self.set_stage("ATOMICITY")

        owner_domain = (
            f"contact-owner-{self.tag}.example"
        )
        conflict_email = (
            f"shared-contact-{self.tag}@example.com"
        )

        code, owner = self.post(
            "/api/companies",
            {
                "name": (
                    f"Contact Owner {self.tag}"
                ),
                "website_url": (
                    f"https://{owner_domain}"
                ),
                "domain": owner_domain,
                "industry": "Logistics",
                "country_code": "MY",
                "source_type": "VALIDATOR",
            },
        )

        if not self.assert_http(
            "Atomicity owner company created",
            code,
            201,
            owner,
        ):
            return

        owner_id = UUID(owner["id"])
        self.company_ids.add(owner_id)

        code, contact = self.post(
            "/api/contacts",
            {
                "company_id": str(owner_id),
                "full_name": "Conflict Owner",
                "email": conflict_email,
                "is_primary": True,
            },
        )

        if not self.assert_http(
            "Atomicity conflicting contact created",
            code,
            201,
            contact,
        ):
            return

        candidate_domain = (
            f"atomic-target-{self.tag}.example"
        )

        payload = self.candidate_payload(
            "atomic",
            confidence=0.90,
            domain=candidate_domain,
            website_url=f"https://{candidate_domain}",
            email=conflict_email,
            contact_name=None,
        )

        code, result = self.post(
            "/api/candidates",
            payload,
        )

        if not self.assert_http(
            "Atomicity candidate created",
            code,
            201,
            result,
        ):
            return

        candidate = result.get("candidate") or {}
        candidate_id = UUID(candidate["id"])
        self.candidate_ids.add(candidate_id)

        code, accepted = self.post(
            f"/api/candidates/{candidate_id}/accept",
            {
                "reviewed_by": "candidate-validator",
                "priority": "MEDIUM",
            },
        )

        self.assert_http(
            "Cross-company email conflict blocks acceptance",
            code,
            409,
            accepted,
        )

        # The candidate should remain reviewable.
        code2, detail = self.get(
            f"/api/candidates/{candidate_id}"
        )

        if self.assert_http(
            "Candidate survives failed atomic acceptance",
            code2,
            200,
            detail,
        ):
            self.assert_true(
                "Failed acceptance leaves status reviewable",
                detail.get("status")
                == "READY_FOR_REVIEW",
                str(detail.get("status")),
            )
            self.assert_true(
                "Failed acceptance did not set accepted_lead_id",
                detail.get("accepted_lead_id")
                is None,
                str(
                    detail.get(
                        "accepted_lead_id"
                    )
                ),
            )

        with SessionLocal() as db:
            leaked_company = db.scalar(
                select(Company).where(
                    Company.domain == candidate_domain
                )
            )

            self.assert_true(
                "Failed acceptance rolled back Company creation",
                leaked_company is None,
                (
                    f"leaked_company_id={leaked_company.id}"
                    if leaked_company
                    else "none"
                ),
            )

            candidate_row = db.get(
                LeadCandidate,
                candidate_id,
            )

            leaked_leads = []
            if candidate_row is not None:
                # A new company never committed, so no Lead should
                # reference a company created during the failed flow.
                leaked_leads = list(
                    db.scalars(
                        select(Lead).where(
                            Lead.id
                            == candidate_row.accepted_lead_id
                        )
                    ).all()
                ) if candidate_row.accepted_lead_id else []

            self.assert_true(
                "Failed acceptance created no Lead",
                not leaked_leads,
                repr(
                    [
                        str(lead.id)
                        for lead in leaked_leads
                    ]
                ),
            )

    # ========================================================
    # Pagination sanity
    # ========================================================

    def pagination_test(self) -> None:
        self.set_stage("PAGINATION")

        code0, page0 = self.get(
            "/api/candidates?limit=1&offset=0"
        )
        code1, page1 = self.get(
            "/api/candidates?limit=1&offset=1"
        )

        if (
            self.assert_http(
                "Candidate pagination offset=0",
                code0,
                200,
                page0,
            )
            and self.assert_http(
                "Candidate pagination offset=1",
                code1,
                200,
                page1,
            )
        ):
            if page0 and page1:
                self.assert_true(
                    "Candidate offsets return different rows",
                    page0[0].get("id")
                    != page1[0].get("id"),
                    (
                        f"page0={page0[0].get('id')}, "
                        f"page1={page1[0].get('id')}"
                    ),
                )
            else:
                self.skip(
                    "Candidate offsets return different rows",
                    "Fewer than two rows available at pagination check.",
                )

    # ========================================================
    # Cleanup
    # ========================================================

    def cleanup(self) -> None:
        self.set_stage("CLEANUP")

        try:
            with SessionLocal() as db:
                entity_ids = (
                    set(self.candidate_ids)
                    | set(self.lead_ids)
                )

                if entity_ids:
                    db.execute(
                        delete(Event).where(
                            Event.entity_id.in_(
                                entity_ids
                            )
                        )
                    )

                if self.candidate_ids:
                    db.execute(
                        delete(
                            LeadCandidateSource
                        ).where(
                            LeadCandidateSource.candidate_id.in_(
                                self.candidate_ids
                            )
                        )
                    )
                    db.execute(
                        delete(
                            LeadCandidate
                        ).where(
                            LeadCandidate.id.in_(
                                self.candidate_ids
                            )
                        )
                    )

                if self.lead_ids:
                    db.execute(
                        delete(Lead).where(
                            Lead.id.in_(
                                self.lead_ids
                            )
                        )
                    )

                if self.company_ids:
                    db.execute(
                        delete(Contact).where(
                            Contact.company_id.in_(
                                self.company_ids
                            )
                        )
                    )
                    db.execute(
                        delete(Company).where(
                            Company.id.in_(
                                self.company_ids
                            )
                        )
                    )

                db.commit()

            self.pass_(
                "Validator fixtures cleaned up",
                (
                    f"candidates={len(self.candidate_ids)}, "
                    f"leads={len(self.lead_ids)}, "
                    f"companies={len(self.company_ids)}"
                ),
            )

        except Exception as exc:
            self.fail(
                "Validator fixtures cleaned up",
                repr(exc),
            )

    # ========================================================
    # Run / summary
    # ========================================================

    def run(self) -> int:
        print("=" * 76)
        print("LorrySystem Lead Candidate API Validator — Migration 008")
        print("=" * 76)
        print(f"Base URL: {self.base_url}")
        print(f"Expected Alembic head: {EXPECTED_ALEMBIC_HEAD}")
        print(f"Run tag: {self.tag}")
        print()

        try:
            self.precheck()

            if self.icp_id is None:
                self.fail(
                    "Cannot continue without active ICP",
                    "Stopping behavioral tests.",
                )
            else:
                self.database_checks()
                self.threshold_and_schema_tests()
                self.main_candidate_flow()
                self.company_and_duplicate_tests()
                self.atomicity_test()
                self.pagination_test()

        finally:
            self.cleanup()

        print()
        print("=" * 76)
        print("LorrySystem Lead Candidate API Validation Summary")
        print("=" * 76)
        print(f"PASS: {self.pass_count}")
        print(f"FAIL: {self.fail_count}")
        print(f"SKIP: {self.skip_count}")
        print()
        print("Stage summary:")

        for stage, counts in self.stage_counts.items():
            state = (
                "PASSED"
                if counts["FAIL"] == 0
                else "FAILED"
            )
            print(
                f"  {stage:<16} {state:<7} "
                f"(PASS {counts['PASS']}, "
                f"FAIL {counts['FAIL']}, "
                f"SKIP {counts['SKIP']})"
            )

        print()
        result = (
            "PASSED"
            if self.fail_count == 0
            else "FAILED"
        )
        print(f"RESULT: {result}")

        return 0 if self.fail_count == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
    )
    args = parser.parse_args()

    api_key = (
        os.getenv("MARKETING_API_KEY")
        or os.getenv("API_KEY")
        or os.getenv("LORRYSYSTEM_API_KEY")
    )

    if not api_key:
        print(
            "ERROR: No Marketing API key found in "
            "MARKETING_API_KEY, API_KEY, or "
            "LORRYSYSTEM_API_KEY.",
            file=sys.stderr,
        )
        return 2

    validator = Validator(
        base_url=args.base_url,
        api_key=api_key,
    )

    return validator.run()


if __name__ == "__main__":
    raise SystemExit(main())
