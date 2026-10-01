#!/usr/bin/env python3
"""
LorrySystem Dashboard — Discovered Leads regression validator.

Designed to run inside the marketing-api container because that container:
- can reach the Dashboard over lorrysystem-api-net,
- can call the Marketing API locally,
- can clean up only the temporary validation fixtures afterward.

This does NOT give the Dashboard PostgreSQL access.
"""

from __future__ import annotations

import argparse
import html
import http.cookiejar
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models.catalog import ICPProfile
from app.models.companies import Company, Contact
from app.models.discovery import LeadCandidate, LeadCandidateSource
from app.models.leads import Lead
from app.models.marketing import Event


DEFAULT_DASHBOARD_URL = "http://lorrysystem-dashboard:8080"
DEFAULT_API_URL = "http://127.0.0.1:8000"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req,
        fp,
        code,
        msg,
        headers,
        newurl,
    ):
        return None


class Validator:
    def __init__(
        self,
        dashboard_url: str,
        api_url: str,
        api_key: str,
    ) -> None:
        self.dashboard_url = dashboard_url.rstrip("/")
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key

        self.pass_count = 0
        self.fail_count = 0
        self.skip_count = 0
        self.stage = "PRECHECK"
        self.stage_counts: dict[str, dict[str, int]] = defaultdict(
            lambda: {"PASS": 0, "FAIL": 0, "SKIP": 0}
        )

        self.tag = uuid4().hex[:12]
        self.icp_id: UUID | None = None

        self.candidate_ids: set[UUID] = set()
        self.company_ids: set[UUID] = set()
        self.lead_ids: set[UUID] = set()

        self.cookie_jar = http.cookiejar.CookieJar()
        self.browser = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(
                self.cookie_jar
            ),
            NoRedirect(),
        )

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
        detail: str = "",
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
                f"HTTP {code}, expected {expected_codes}"
                + (f"; {detail}" if detail else "")
            ),
        )

    # ========================================================
    # HTTP helpers
    # ========================================================

    @staticmethod
    def _decode_body(raw: bytes) -> str:
        return raw.decode("utf-8", errors="replace")

    def browser_request(
        self,
        method: str,
        path: str,
        *,
        form: dict[str, Any] | None = None,
    ) -> tuple[int, str, dict[str, str]]:
        data = None
        headers = {}

        if form is not None:
            data = urllib.parse.urlencode(
                {
                    key: "" if value is None else str(value)
                    for key, value in form.items()
                }
            ).encode("utf-8")
            headers["Content-Type"] = (
                "application/x-www-form-urlencoded"
            )

        req = urllib.request.Request(
            self.dashboard_url + path,
            data=data,
            headers=headers,
            method=method,
        )

        try:
            with self.browser.open(
                req,
                timeout=20,
            ) as response:
                return (
                    response.status,
                    self._decode_body(response.read()),
                    dict(response.headers.items()),
                )

        except urllib.error.HTTPError as exc:
            return (
                exc.code,
                self._decode_body(exc.read()),
                dict(exc.headers.items()),
            )

        except Exception as exc:
            return (
                0,
                repr(exc),
                {},
            )

    def api_request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        data = None
        headers = {
            "X-API-Key": self.api_key,
        }

        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(
            self.api_url + path,
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

    @staticmethod
    def csrf_from(page: str) -> str | None:
        match = re.search(
            r'name=["\']csrf["\']\s+value=["\']([^"\']+)["\']',
            page,
        )
        return html.unescape(match.group(1)) if match else None

    @staticmethod
    def location_header(headers: dict[str, str]) -> str:
        return (
            headers.get("Location")
            or headers.get("location")
            or ""
        )

    # ========================================================
    # Fixture builders
    # ========================================================

    def load_icp(self) -> bool:
        with SessionLocal() as db:
            icp = db.scalar(
                select(ICPProfile).where(
                    ICPProfile.code == "LOGISTICS_HAULAGE",
                    ICPProfile.active.is_(True),
                )
            )

            if icp is None:
                self.fail(
                    "Active Logistics / Haulage ICP exists",
                    "No active LOGISTICS_HAULAGE row.",
                )
                return False

            self.icp_id = icp.id

        self.pass_(
            "Active Logistics / Haulage ICP exists",
            str(self.icp_id),
        )
        return True

    def candidate_payload(
        self,
        suffix: str,
        *,
        company_name: str | None = None,
        domain: str | None = None,
        confidence: float = 0.91,
        email: str | None = None,
    ) -> dict[str, Any]:
        actual_domain = (
            domain
            or f"dashboard-{suffix}-{self.tag}.example"
        )

        return {
            "company_name": (
                company_name
                or f"Dashboard Candidate {suffix} {self.tag}"
            ),
            "website_url": f"https://{actual_domain}",
            "domain": actual_domain,
            "industry": "Logistics",
            "country_code": "MY",
            "state": "Selangor",
            "city": "Shah Alam",
            "contact_name": None,
            "job_title": "Fleet Manager",
            "email": email,
            "phone": None,
            "linkedin_url": None,
            "suggested_icp_profile_id": str(self.icp_id),
            "icp_confidence": confidence,
            "icp_reasoning": (
                "Public company evidence indicates commercial "
                "haulage and fleet operations."
            ),
            "fleet_clues": [
                "Commercial vehicle fleet",
                "Container haulage",
            ],
            "buying_signals": [
                "Fleet expansion",
            ],
            "source_summary": (
                "Dashboard discovery regression fixture."
            ),
            "source": {
                "source_type": "COMPANY_WEBSITE",
                "url": (
                    f"https://source-{self.tag}.example/{suffix}"
                ),
                "title": (
                    f"Dashboard validator evidence {suffix}"
                ),
                "source_query": (
                    "haulage company Selangor"
                ),
                "summary": (
                    "Public website describes logistics operations."
                ),
                "evidence": (
                    "Operates a commercial fleet serving "
                    "haulage customers."
                ),
            },
        }

    def create_candidate(
        self,
        suffix: str,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        code, payload = self.api_request(
            "POST",
            "/api/candidates",
            self.candidate_payload(
                suffix,
                **kwargs,
            ),
        )

        if code != 201 or not isinstance(payload, dict):
            self.fail(
                f"Fixture candidate created: {suffix}",
                f"HTTP {code}; response={payload!r}",
            )
            return None

        candidate = payload.get("candidate")
        if not isinstance(candidate, dict):
            self.fail(
                f"Fixture candidate payload returned: {suffix}",
                repr(payload),
            )
            return None

        candidate_id = UUID(candidate["id"])
        self.candidate_ids.add(candidate_id)

        self.pass_(
            f"Fixture candidate created: {suffix}",
            str(candidate_id),
        )
        return candidate

    # ========================================================
    # Precheck
    # ========================================================

    def precheck(self) -> None:
        self.set_stage("PRECHECK")

        code, page, _ = self.browser_request(
            "GET",
            "/health",
        )
        self.assert_http(
            "Dashboard health reachable",
            code,
            200,
        )
        self.assert_true(
            "Dashboard health identifies service",
            "lorrysystem-dashboard" in page,
        )

        code, page, _ = self.browser_request(
            "GET",
            "/discovered-leads",
        )
        self.assert_http(
            "Discovered Leads queue loads",
            code,
            200,
        )
        self.assert_true(
            "Discovered Leads heading rendered",
            "Discovered Leads" in page,
        )
        self.assert_true(
            "Sidebar contains Discovered Leads",
            'href="/discovered-leads"' in page,
        )

        self.load_icp()

    # ========================================================
    # Queue, detail, edit, CSRF, reject
    # ========================================================

    def review_flow(self) -> None:
        self.set_stage("REVIEW_FLOW")

        company_name = (
            f"Dashboard Review Fixture {self.tag}"
        )

        candidate = self.create_candidate(
            "review",
            company_name=company_name,
        )
        if candidate is None:
            return

        candidate_id = UUID(candidate["id"])

        code, queue, _ = self.browser_request(
            "GET",
            "/discovered-leads?status=REVIEWABLE",
        )

        if self.assert_http(
            "Review queue loads with fixture",
            code,
            200,
        ):
            self.assert_true(
                "Fixture company appears in queue",
                company_name in queue,
            )
            self.assert_true(
                "Queue renders confidence",
                "91%" in queue,
            )
            self.assert_true(
                "Queue links fixture detail",
                (
                    f"/discovered-leads/{candidate_id}"
                    in queue
                ),
            )

        code, detail, _ = self.browser_request(
            "GET",
            f"/discovered-leads/{candidate_id}",
        )

        if not self.assert_http(
            "Candidate detail loads",
            code,
            200,
        ):
            return

        self.assert_true(
            "Detail renders company name",
            company_name in detail,
        )
        self.assert_true(
            "Detail renders ICP reasoning",
            "commercial haulage and fleet operations"
            in detail,
        )
        self.assert_true(
            "Detail renders fleet clue",
            "Container haulage" in detail,
        )
        self.assert_true(
            "Detail renders buying signal",
            "Fleet expansion" in detail,
        )
        self.assert_true(
            "Detail renders source evidence",
            "Operates a commercial fleet" in detail,
        )

        csrf = self.csrf_from(detail)
        if not self.assert_true(
            "Candidate detail contains CSRF token",
            bool(csrf),
        ):
            return

        # Wrong token must be rejected by the Dashboard/BFF.
        code, _, headers = self.browser_request(
            "POST",
            f"/discovered-leads/{candidate_id}/edit",
            form={
                "csrf": "wrong-token",
                "company_name": company_name,
                "website_url": candidate.get("website_url") or "",
                "domain": candidate.get("domain") or "",
                "industry": "Logistics",
                "country_code": "MY",
                "state": "Selangor",
                "city": "Shah Alam",
                "contact_name": "",
                "job_title": "Fleet Manager",
                "email": "",
                "phone": "",
                "linkedin_url": "",
                "suggested_icp_profile_id": str(self.icp_id),
                "icp_confidence": "0.91",
                "icp_reasoning": (
                    "Public company evidence indicates "
                    "commercial haulage and fleet operations."
                ),
                "fleet_clues": (
                    "Commercial vehicle fleet\nContainer haulage"
                ),
                "buying_signals": "Fleet expansion",
                "source_summary": (
                    "Dashboard discovery regression fixture."
                ),
            },
        )

        if self.assert_http(
            "Invalid CSRF blocked",
            code,
            303,
        ):
            self.assert_true(
                "Invalid CSRF redirects with error",
                "error=csrf"
                in self.location_header(headers),
                self.location_header(headers),
            )

        # Valid edit.
        code, _, headers = self.browser_request(
            "POST",
            f"/discovered-leads/{candidate_id}/edit",
            form={
                "csrf": csrf,
                "company_name": company_name,
                "website_url": candidate.get("website_url") or "",
                "domain": candidate.get("domain") or "",
                "industry": "Logistics",
                "country_code": "MY",
                "state": "Selangor",
                "city": "Port Klang",
                "contact_name": "",
                "job_title": "Fleet Manager",
                "email": "",
                "phone": "",
                "linkedin_url": "",
                "suggested_icp_profile_id": str(self.icp_id),
                "icp_confidence": "0.91",
                "icp_reasoning": (
                    "Public company evidence indicates "
                    "commercial haulage and fleet operations."
                ),
                "fleet_clues": (
                    "Commercial vehicle fleet\nContainer haulage"
                ),
                "buying_signals": "Fleet expansion",
                "source_summary": (
                    "Edited through Dashboard regression."
                ),
            },
        )

        if self.assert_http(
            "Candidate edit redirects",
            code,
            303,
        ):
            self.assert_true(
                "Edit redirect marks success",
                "updated=1"
                in self.location_header(headers),
                self.location_header(headers),
            )

        code, edited, _ = self.browser_request(
            "GET",
            f"/discovered-leads/{candidate_id}",
        )

        if self.assert_http(
            "Edited candidate detail reloads",
            code,
            200,
        ):
            self.assert_true(
                "Edited city rendered",
                "Port Klang" in edited,
            )
            self.assert_true(
                "Edited summary rendered",
                "Edited through Dashboard regression."
                in edited,
            )

        csrf = self.csrf_from(edited) or csrf

        # Reject requires human reason and must leave the review queue.
        code, _, headers = self.browser_request(
            "POST",
            f"/discovered-leads/{candidate_id}/reject",
            form={
                "csrf": csrf,
                "review_notes": (
                    "Dashboard regression rejection."
                ),
            },
        )

        if self.assert_http(
            "Candidate rejection redirects",
            code,
            303,
        ):
            self.assert_true(
                "Reject redirect marks decision",
                "decision=rejected"
                in self.location_header(headers),
                self.location_header(headers),
            )

        code, api_candidate = self.api_request(
            "GET",
            f"/api/candidates/{candidate_id}",
        )
        if self.assert_http(
            "Rejected candidate readable from API",
            code,
            200,
        ):
            self.assert_true(
                "Dashboard rejection persisted",
                api_candidate.get("status") == "REJECTED",
                str(api_candidate.get("status")),
            )
            self.assert_true(
                "Reviewer identity persisted",
                bool(api_candidate.get("reviewed_by")),
                str(api_candidate.get("reviewed_by")),
            )

    # ========================================================
    # Accept -> Lead
    # ========================================================

    def accept_flow(self) -> None:
        self.set_stage("ACCEPT_FLOW")

        company_name = (
            f"Dashboard Accept Fixture {self.tag}"
        )
        email = (
            f"dashboard-accept-{self.tag}@example.com"
        )

        candidate = self.create_candidate(
            "accept",
            company_name=company_name,
            email=email,
        )
        if candidate is None:
            return

        candidate_id = UUID(candidate["id"])

        code, detail, _ = self.browser_request(
            "GET",
            f"/discovered-leads/{candidate_id}",
        )
        if not self.assert_http(
            "Accept candidate detail loads",
            code,
            200,
        ):
            return

        csrf = self.csrf_from(detail)
        if not self.assert_true(
            "Accept form has CSRF token",
            bool(csrf),
        ):
            return

        code, _, headers = self.browser_request(
            "POST",
            f"/discovered-leads/{candidate_id}/accept",
            form={
                "csrf": csrf,
                "priority": "HIGH",
                "icp_profile_id": str(self.icp_id),
                "review_notes": (
                    "Dashboard regression accepted."
                ),
            },
        )

        if not self.assert_http(
            "Accept as Lead redirects",
            code,
            303,
        ):
            return

        location = self.location_header(headers)
        match = re.search(
            r"^/leads/([0-9a-fA-F-]{36})\?created=1$",
            location,
        )

        if not self.assert_true(
            "Accepted candidate redirects to new Lead",
            bool(match),
            location,
        ):
            return

        lead_id = UUID(match.group(1))
        self.lead_ids.add(lead_id)

        code, lead = self.api_request(
            "GET",
            f"/api/leads/{lead_id}",
        )
        if self.assert_http(
            "Accepted Lead readable from API",
            code,
            200,
        ):
            self.assert_true(
                "Accepted Lead starts DISCOVERED",
                lead.get("status") == "DISCOVERED",
                str(lead.get("status")),
            )
            self.assert_true(
                "Dashboard priority preserved",
                lead.get("priority") == "HIGH",
                str(lead.get("priority")),
            )
            self.company_ids.add(
                UUID(lead["company_id"])
            )

        code, candidate_after = self.api_request(
            "GET",
            f"/api/candidates/{candidate_id}",
        )
        if self.assert_http(
            "Accepted candidate readable from API",
            code,
            200,
        ):
            self.assert_true(
                "Candidate status ACCEPTED",
                candidate_after.get("status")
                == "ACCEPTED",
                str(candidate_after.get("status")),
            )
            self.assert_true(
                "Candidate links accepted Lead",
                candidate_after.get("accepted_lead_id")
                == str(lead_id),
                str(
                    candidate_after.get(
                        "accepted_lead_id"
                    )
                ),
            )

        code, lead_page, _ = self.browser_request(
            "GET",
            location,
        )
        if self.assert_http(
            "Redirected Lead detail loads",
            code,
            200,
        ):
            self.assert_true(
                "Lead page renders company",
                company_name in lead_page,
            )

    # ========================================================
    # Accept-time duplicate redirect
    # ========================================================

    def duplicate_flow(self) -> None:
        self.set_stage("DUPLICATE_FLOW")

        domain = (
            f"dashboard-duplicate-{self.tag}.example"
        )
        company_name = (
            f"Dashboard Duplicate Fixture {self.tag}"
        )

        code, company = self.api_request(
            "POST",
            "/api/companies",
            {
                "name": company_name,
                "website_url": f"https://{domain}",
                "domain": domain,
                "industry": "Logistics",
                "country_code": "MY",
                "state": "Selangor",
                "city": "Klang",
                "source_type": "DASHBOARD_VALIDATOR",
            },
        )

        if not self.assert_http(
            "Duplicate fixture company created",
            code,
            201,
        ):
            return

        company_id = UUID(company["id"])
        self.company_ids.add(company_id)

        candidate = self.create_candidate(
            "duplicate",
            company_name=company_name,
            domain=domain,
        )
        if candidate is None:
            return

        candidate_id = UUID(candidate["id"])

        code, lead = self.api_request(
            "POST",
            "/api/leads",
            {
                "company_id": str(company_id),
                "icp_profile_id": str(self.icp_id),
                "priority": "MEDIUM",
            },
        )

        if not self.assert_http(
            "Duplicate fixture Lead created after candidate",
            code,
            201,
        ):
            return

        existing_lead_id = UUID(lead["id"])
        self.lead_ids.add(existing_lead_id)

        code, detail, _ = self.browser_request(
            "GET",
            f"/discovered-leads/{candidate_id}",
        )
        if not self.assert_http(
            "Duplicate candidate detail loads",
            code,
            200,
        ):
            return

        csrf = self.csrf_from(detail)
        if not self.assert_true(
            "Duplicate accept form has CSRF",
            bool(csrf),
        ):
            return

        code, _, headers = self.browser_request(
            "POST",
            f"/discovered-leads/{candidate_id}/accept",
            form={
                "csrf": csrf,
                "priority": "MEDIUM",
                "icp_profile_id": str(self.icp_id),
                "review_notes": (
                    "Dashboard duplicate regression."
                ),
            },
        )

        if not self.assert_http(
            "Duplicate acceptance redirects",
            code,
            303,
        ):
            return

        location = self.location_header(headers)

        self.assert_true(
            "Duplicate redirects to existing Lead",
            location == f"/leads/{existing_lead_id}",
            location,
        )

        code, candidate_after = self.api_request(
            "GET",
            f"/api/candidates/{candidate_id}",
        )
        if self.assert_http(
            "Duplicate candidate readable",
            code,
            200,
        ):
            self.assert_true(
                "Candidate marked DUPLICATE",
                candidate_after.get("status")
                == "DUPLICATE",
                str(candidate_after.get("status")),
            )
            self.assert_true(
                "Candidate links duplicate Lead",
                candidate_after.get("duplicate_lead_id")
                == str(existing_lead_id),
                str(
                    candidate_after.get(
                        "duplicate_lead_id"
                    )
                ),
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
                "Dashboard validator fixtures cleaned up",
                (
                    f"candidates={len(self.candidate_ids)}, "
                    f"leads={len(self.lead_ids)}, "
                    f"companies={len(self.company_ids)}"
                ),
            )

        except Exception as exc:
            self.fail(
                "Dashboard validator fixtures cleaned up",
                repr(exc),
            )

    # ========================================================
    # Run
    # ========================================================

    def run(self) -> int:
        print("=" * 76)
        print("LorrySystem Dashboard — Discovered Leads Validator")
        print("=" * 76)
        print(f"Dashboard URL: {self.dashboard_url}")
        print(f"Marketing API URL: {self.api_url}")
        print(f"Run tag: {self.tag}")
        print()

        try:
            self.precheck()

            if self.icp_id is None:
                self.fail(
                    "Cannot continue without active ICP"
                )
            else:
                self.review_flow()
                self.accept_flow()
                self.duplicate_flow()

        finally:
            self.cleanup()

        print()
        print("=" * 76)
        print("Discovered Leads Dashboard Validation Summary")
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
        "--dashboard-url",
        default=DEFAULT_DASHBOARD_URL,
    )
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
    )
    args = parser.parse_args()

    api_key = (
        os.getenv("MARKETING_API_KEY")
        or os.getenv("API_KEY")
        or os.getenv("LORRYSYSTEM_API_KEY")
    )

    if not api_key:
        print(
            "ERROR: Marketing API key is not available.",
            file=sys.stderr,
        )
        return 2

    return Validator(
        dashboard_url=args.dashboard_url,
        api_url=args.api_url,
        api_key=api_key,
    ).run()


if __name__ == "__main__":
    raise SystemExit(main())
