#!/usr/bin/env python3
"""
LorrySystem Research API MVP1 validation suite.

Run inside the Marketing API container, for example:

    python /app/scripts/validate_research_api.py

Optional:

    python /app/scripts/validate_research_api.py \
        --lead-id dcb7d435-cf8c-4202-868f-3666dc53f8ac

What it validates:
- Required Research endpoints are registered in OpenAPI.
- Research database lifecycle schema is present.
- Nonexistent lead/research handling.
- Research run creation and history preservation.
- DISCOVERED -> RESEARCHING behavior when applicable.
- PENDING -> RUNNING -> COMPLETED.
- PENDING -> RUNNING -> PARTIAL.
- PENDING -> RUNNING -> FAILED.
- Invalid transitions return 409.
- Confidence validation returns 422.
- Multiple research sources are stored and returned.
- Research completion does not auto-qualify the lead.
- Research lifecycle events are written to PostgreSQL.

NOTE:
This is an integration test. It creates three new research runs on the
selected lead and intentionally leaves them in the database so research
history remains auditable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

try:
    import psycopg
except ImportError:
    psycopg = None


ACTIVE_LEAD_STATUSES = {
    "DISCOVERED",
    "RESEARCHING",
    "QUALIFIED",
    "READY_FOR_OUTREACH",
    "CONTACTED",
    "REPLIED",
}

EXPECTED_RESEARCH_ROUTES = {
    "/api/leads/{lead_id}/research": {"get", "post"},
    "/api/research/{research_id}": {"get"},
    "/api/research/{research_id}/start": {"patch"},
    "/api/research/{research_id}/sources": {"post"},
    "/api/research/{research_id}/complete": {"patch"},
    "/api/research/{research_id}/partial": {"patch"},
    "/api/research/{research_id}/fail": {"patch"},
}


@dataclass
class Result:
    name: str
    status: str
    detail: str = ""


class Validator:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.results: list[Result] = []
        self.created_research_ids: list[str] = []
        self.initial_lead_status: str | None = None
        self.lead_id: str | None = None

    def pass_(self, name: str, detail: str = "") -> None:
        self.results.append(Result(name, "PASS", detail))
        print(f"[PASS] {name}" + (f" — {detail}" if detail else ""))

    def fail(self, name: str, detail: str = "") -> None:
        self.results.append(Result(name, "FAIL", detail))
        print(f"[FAIL] {name}" + (f" — {detail}" if detail else ""))

    def skip(self, name: str, detail: str = "") -> None:
        self.results.append(Result(name, "SKIP", detail))
        print(f"[SKIP] {name}" + (f" — {detail}" if detail else ""))

    def assert_true(self, name: str, condition: bool, detail: str = "") -> bool:
        if condition:
            self.pass_(name, detail)
            return True
        self.fail(name, detail)
        return False

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        data = None
        headers = {}


        api_key = (
            os.getenv("MARKETING_API_KEY")
            or os.getenv("API_KEY")
            or os.getenv("LORRYSYSTEM_API_KEY")
        )

        if api_key:
            headers["X-API-Key"] = api_key
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as response:
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

    def get(self, path: str) -> tuple[int, Any]:
        return self.request("GET", path)

    def post(self, path: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
        return self.request("POST", path, body)

    def patch(self, path: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
        return self.request("PATCH", path, body)

    def check_openapi(self) -> None:
        code, payload = self.get("/openapi.json")

        if not self.assert_true(
            "OpenAPI reachable",
            code == 200 and isinstance(payload, dict),
            f"HTTP {code}",
        ):
            return

        paths = payload.get("paths", {})

        for path, expected_methods in EXPECTED_RESEARCH_ROUTES.items():
            actual_methods = {
                key.lower()
                for key in paths.get(path, {}).keys()
                if key.lower()
                in {"get", "post", "put", "patch", "delete", "options", "head"}
            }
            self.assert_true(
                f"Route registered: {path}",
                expected_methods.issubset(actual_methods),
                f"expected={sorted(expected_methods)}, actual={sorted(actual_methods)}",
            )

    def db_connect(self):
        if psycopg is None:
            raise RuntimeError("psycopg is not installed.")

        required = [
            "POSTGRES_DB",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "POSTGRES_HOST",
            "POSTGRES_PORT",
        ]

        missing = [name for name in required if not os.getenv(name)]
        if missing:
            raise RuntimeError(
                "Missing DB environment variables: " + ", ".join(missing)
            )

        return psycopg.connect(
            dbname=os.environ["POSTGRES_DB"],
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            host=os.environ["POSTGRES_HOST"],
            port=os.environ["POSTGRES_PORT"],
        )

    def check_db_schema(self) -> None:
        try:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT column_name, is_nullable, column_default
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'lead_research'
                        """
                    )
                    columns = {
                        row[0]: {
                            "nullable": row[1],
                            "default": row[2],
                        }
                        for row in cur.fetchall()
                    }

                    self.assert_true(
                        "DB column started_at exists",
                        "started_at" in columns,
                    )
                    self.assert_true(
                        "DB column completed_at exists",
                        "completed_at" in columns,
                    )
                    self.assert_true(
                        "researched_at is nullable",
                        columns.get("researched_at", {}).get("nullable") == "YES",
                        str(columns.get("researched_at")),
                    )

                    default = str(
                        columns.get("research_status", {}).get("default", "")
                    )
                    self.assert_true(
                        "research_status default is PENDING",
                        "PENDING" in default,
                        default,
                    )

                    cur.execute(
                        """
                        SELECT conname
                        FROM pg_constraint c
                        JOIN pg_class t ON t.oid = c.conrelid
                        JOIN pg_namespace n ON n.oid = t.relnamespace
                        WHERE n.nspname = 'public'
                          AND t.relname = 'lead_research'
                        """
                    )
                    constraints = {row[0] for row in cur.fetchall()}

                    self.assert_true(
                        "Research confidence DB constraint exists",
                        "ck_lead_research_confidence_range" in constraints,
                    )
                    self.assert_true(
                        "Research status DB constraint exists",
                        "ck_lead_research_status" in constraints,
                    )

                    cur.execute(
                        """
                        SELECT indexname
                        FROM pg_indexes
                        WHERE schemaname = 'public'
                          AND tablename = 'lead_research'
                        """
                    )
                    indexes = {row[0] for row in cur.fetchall()}

                    self.assert_true(
                        "Research lead_id index exists",
                        "idx_lead_research_lead_id" in indexes,
                    )
                    self.assert_true(
                        "Research status index exists",
                        "idx_lead_research_status" in indexes,
                    )
        except Exception as exc:
            self.fail("Database schema checks", repr(exc))

    def choose_lead(self, explicit_lead_id: str | None) -> dict[str, Any] | None:
        if explicit_lead_id:
            code, lead = self.get(f"/api/leads/{explicit_lead_id}")
            if code != 200:
                self.fail(
                    "Selected lead exists",
                    f"HTTP {code}: {lead}",
                )
                return None
            if lead.get("status") not in ACTIVE_LEAD_STATUSES:
                self.fail(
                    "Selected lead is researchable",
                    f"status={lead.get('status')}",
                )
                return None

            self.pass_(
                "Selected lead exists",
                f"{lead['id']} ({lead['status']})",
            )
            return lead

        code, leads = self.get("/api/leads")
        if code != 200 or not isinstance(leads, list):
            self.fail("List leads", f"HTTP {code}: {leads}")
            return None

        discovered = next(
            (lead for lead in leads if lead.get("status") == "DISCOVERED"),
            None,
        )
        if discovered:
            self.pass_(
                "Auto-selected DISCOVERED lead",
                discovered["id"],
            )
            return discovered

        researchable = next(
            (
                lead
                for lead in leads
                if lead.get("status") in ACTIVE_LEAD_STATUSES
            ),
            None,
        )
        if researchable:
            self.pass_(
                "Auto-selected researchable lead",
                f"{researchable['id']} ({researchable['status']})",
            )
            return researchable

        self.fail(
            "Find researchable lead",
            "No lead in an active lifecycle status was found.",
        )
        return None

    @staticmethod
    def completion_payload(confidence: int = 84) -> dict[str, Any]:
        return {
            "summary": "Automated Research API validation result.",
            "pain_points": [
                "fleet visibility",
                "driver safety",
            ],
            "buying_signals": [
                "commercial logistics operations",
            ],
            "company_facts": {
                "country": "MY",
                "industry": "logistics",
                "validation_run": True,
            },
            "confidence": confidence,
            "model_provider": "TEST",
            "model_name": "research-api-validator",
            "raw_output": {
                "validation": True,
            },
        }

    def assert_http(
        self,
        name: str,
        actual: int,
        expected: int,
        payload: Any,
    ) -> bool:
        return self.assert_true(
            name,
            actual == expected,
            f"HTTP {actual}, expected {expected}; response={payload}",
        )

    def create_run(self, label: str) -> dict[str, Any] | None:
        assert self.lead_id is not None

        code, run = self.post(
            f"/api/leads/{self.lead_id}/research"
        )

        if not self.assert_http(
            f"{label}: create research run",
            code,
            201,
            run,
        ):
            return None

        self.created_research_ids.append(run["id"])

        self.assert_true(
            f"{label}: initial status is PENDING",
            run.get("research_status") == "PENDING",
            str(run.get("research_status")),
        )
        self.assert_true(
            f"{label}: started_at initially null",
            run.get("started_at") is None,
        )
        self.assert_true(
            f"{label}: completed_at initially null",
            run.get("completed_at") is None,
        )

        return run

    def start_run(self, label: str, research_id: str) -> dict[str, Any] | None:
        code, run = self.patch(
            f"/api/research/{research_id}/start"
        )

        if not self.assert_http(
            f"{label}: PENDING -> RUNNING",
            code,
            200,
            run,
        ):
            return None

        self.assert_true(
            f"{label}: RUNNING status persisted",
            run.get("research_status") == "RUNNING",
            str(run.get("research_status")),
        )
        self.assert_true(
            f"{label}: started_at populated",
            bool(run.get("started_at")),
            str(run.get("started_at")),
        )
        self.assert_true(
            f"{label}: completed_at still null while RUNNING",
            run.get("completed_at") is None,
        )

        return run

    def check_not_found_cases(self) -> None:
        fake_lead = str(uuid.uuid4())
        code, payload = self.post(
            f"/api/leads/{fake_lead}/research"
        )
        self.assert_http(
            "Nonexistent lead research request rejected",
            code,
            404,
            payload,
        )

        fake_research = str(uuid.uuid4())
        code, payload = self.get(
            f"/api/research/{fake_research}"
        )
        self.assert_http(
            "Nonexistent research lookup rejected",
            code,
            404,
            payload,
        )

    def check_lead_after_first_creation(self) -> None:
        assert self.lead_id is not None

        code, lead = self.get(
            f"/api/leads/{self.lead_id}"
        )

        if not self.assert_http(
            "Lead readable after research creation",
            code,
            200,
            lead,
        ):
            return

        expected = (
            "RESEARCHING"
            if self.initial_lead_status == "DISCOVERED"
            else self.initial_lead_status
        )

        self.assert_true(
            "Lead lifecycle integration is correct",
            lead.get("status") == expected,
            f"initial={self.initial_lead_status}, current={lead.get('status')}",
        )

    def run_completed_path(self) -> str | None:
        run = self.create_run("COMPLETED path")
        if not run:
            return None

        research_id = run["id"]

        # PENDING -> COMPLETED must be rejected.
        code, payload = self.patch(
            f"/api/research/{research_id}/complete",
            self.completion_payload(),
        )
        self.assert_http(
            "COMPLETED path: PENDING -> COMPLETED rejected",
            code,
            409,
            payload,
        )

        self.check_lead_after_first_creation()

        running = self.start_run(
            "COMPLETED path",
            research_id,
        )
        if not running:
            return research_id

        # RUNNING -> RUNNING must be rejected.
        code, payload = self.patch(
            f"/api/research/{research_id}/start"
        )
        self.assert_http(
            "COMPLETED path: duplicate start rejected",
            code,
            409,
            payload,
        )

        # Source validation.
        code, payload = self.post(
            f"/api/research/{research_id}/sources",
            {
                "source_type": "WEBSITE",
                "url": "https://example.com/validator-invalid",
                "title": "Invalid confidence test",
                "confidence": 101,
            },
        )
        self.assert_http(
            "Source confidence >100 rejected",
            code,
            422,
            payload,
        )

        token = uuid.uuid4().hex[:10]

        sources = [
            {
                "source_type": "WEBSITE",
                "url": f"https://example.com/research-validation/{token}/website",
                "title": "Validation Company Website",
                "evidence": "Validation evidence from a company website.",
                "confidence": 90,
            },
            {
                "source_type": "DIRECTORY",
                "url": f"https://example.com/research-validation/{token}/directory",
                "title": "Validation Business Directory",
                "evidence": "Validation evidence from a business directory.",
                "confidence": 80,
            },
        ]

        source_ids: list[str] = []

        for number, source in enumerate(sources, start=1):
            code, payload = self.post(
                f"/api/research/{research_id}/sources",
                source,
            )
            if self.assert_http(
                f"Create research source {number}",
                code,
                201,
                payload,
            ):
                source_ids.append(payload["id"])
                self.assert_true(
                    f"Source {number} linked to correct research run",
                    payload.get("research_id") == research_id,
                    str(payload.get("research_id")),
                )

        code, detail = self.get(
            f"/api/research/{research_id}"
        )
        if self.assert_http(
            "Research detail retrieval",
            code,
            200,
            detail,
        ):
            returned_source_ids = {
                source["id"]
                for source in detail.get("sources", [])
            }
            self.assert_true(
                "Research detail returns both created sources",
                set(source_ids).issubset(returned_source_ids)
                and len(source_ids) == 2,
                f"expected={source_ids}, actual={sorted(returned_source_ids)}",
            )

        # Completion confidence validation while still RUNNING.
        for confidence in (101, -1):
            code, payload = self.patch(
                f"/api/research/{research_id}/complete",
                self.completion_payload(confidence),
            )
            self.assert_http(
                f"Complete confidence {confidence} rejected",
                code,
                422,
                payload,
            )

        code, completed = self.patch(
            f"/api/research/{research_id}/complete",
            self.completion_payload(84),
        )
        if self.assert_http(
            "RUNNING -> COMPLETED",
            code,
            200,
            completed,
        ):
            self.assert_true(
                "COMPLETED status persisted",
                completed.get("research_status") == "COMPLETED",
                str(completed.get("research_status")),
            )
            self.assert_true(
                "COMPLETED confidence persisted",
                completed.get("confidence") == 84,
                str(completed.get("confidence")),
            )
            self.assert_true(
                "COMPLETED completed_at populated",
                bool(completed.get("completed_at")),
                str(completed.get("completed_at")),
            )

        code, payload = self.patch(
            f"/api/research/{research_id}/complete",
            self.completion_payload(50),
        )
        self.assert_http(
            "COMPLETED -> COMPLETED rejected",
            code,
            409,
            payload,
        )

        code, payload = self.patch(
            f"/api/research/{research_id}/fail",
            {"reason": "Invalid failure after completion."},
        )
        self.assert_http(
            "COMPLETED -> FAILED rejected",
            code,
            409,
            payload,
        )

        # Research completion must not qualify the lead.
        code, lead = self.get(
            f"/api/leads/{self.lead_id}"
        )
        if self.assert_http(
            "Lead readable after research completion",
            code,
            200,
            lead,
        ):
            expected = (
                "RESEARCHING"
                if self.initial_lead_status == "DISCOVERED"
                else self.initial_lead_status
            )
            self.assert_true(
                "Research completion does not auto-qualify lead",
                lead.get("status") == expected
                and lead.get("status") != "QUALIFIED"
                if expected != "QUALIFIED"
                else lead.get("status") == expected,
                f"lead_status={lead.get('status')}",
            )

        return research_id

    def run_partial_path(self) -> str | None:
        run = self.create_run("PARTIAL path")
        if not run:
            return None

        research_id = run["id"]

        if not self.start_run(
            "PARTIAL path",
            research_id,
        ):
            return research_id

        payload = {
            "summary": (
                "Some useful information was found, "
                "but important details remain unverified."
            ),
            "pain_points": [
                "limited fleet visibility",
            ],
            "buying_signals": [],
            "company_facts": {
                "country": "MY",
                "industry": "logistics",
                "validation_run": True,
            },
            "confidence": 60,
            "model_provider": "TEST",
            "model_name": "research-api-validator",
        }

        code, partial = self.patch(
            f"/api/research/{research_id}/partial",
            payload,
        )
        if self.assert_http(
            "RUNNING -> PARTIAL",
            code,
            200,
            partial,
        ):
            self.assert_true(
                "PARTIAL status persisted",
                partial.get("research_status") == "PARTIAL",
                str(partial.get("research_status")),
            )
            self.assert_true(
                "PARTIAL confidence persisted",
                partial.get("confidence") == 60,
                str(partial.get("confidence")),
            )
            self.assert_true(
                "PARTIAL completed_at populated",
                bool(partial.get("completed_at")),
                str(partial.get("completed_at")),
            )

        return research_id

    def run_failed_path(self) -> str | None:
        run = self.create_run("FAILED path")
        if not run:
            return None

        research_id = run["id"]

        code, payload = self.patch(
            f"/api/research/{research_id}/fail",
            {"reason": "Failure before start should be rejected."},
        )
        self.assert_http(
            "FAILED path: PENDING -> FAILED rejected",
            code,
            409,
            payload,
        )

        if not self.start_run(
            "FAILED path",
            research_id,
        ):
            return research_id

        code, payload = self.patch(
            f"/api/research/{research_id}/fail",
            {"reason": ""},
        )
        self.assert_http(
            "Blank failure reason rejected",
            code,
            422,
            payload,
        )

        code, failed = self.patch(
            f"/api/research/{research_id}/fail",
            {
                "reason": (
                    "Unable to access enough reliable "
                    "company information."
                )
            },
        )
        if self.assert_http(
            "RUNNING -> FAILED",
            code,
            200,
            failed,
        ):
            self.assert_true(
                "FAILED status persisted",
                failed.get("research_status") == "FAILED",
                str(failed.get("research_status")),
            )
            self.assert_true(
                "FAILED completed_at populated",
                bool(failed.get("completed_at")),
                str(failed.get("completed_at")),
            )

        return research_id

    def check_history(
        self,
        completed_id: str | None,
        partial_id: str | None,
        failed_id: str | None,
    ) -> None:
        assert self.lead_id is not None

        code, history = self.get(
            f"/api/leads/{self.lead_id}/research"
        )

        if not self.assert_http(
            "Research history retrieval",
            code,
            200,
            history,
        ):
            return

        if not isinstance(history, list):
            self.fail(
                "Research history response is a list",
                repr(history),
            )
            return

        self.pass_(
            "Research history response is a list",
            f"{len(history)} total run(s)",
        )

        expected = [
            research_id
            for research_id in (
                completed_id,
                partial_id,
                failed_id,
            )
            if research_id
        ]

        actual_ids = [
            row.get("id")
            for row in history
        ]

        self.assert_true(
            "All validation research runs preserved",
            set(expected).issubset(set(actual_ids)),
            f"expected={expected}",
        )

        # Our runs were created in COMPLETED, PARTIAL, FAILED order,
        # so newest-first should show FAILED before PARTIAL before COMPLETED.
        ordered_newest = [
            research_id
            for research_id in (
                failed_id,
                partial_id,
                completed_id,
            )
            if research_id
        ]

        filtered = [
            research_id
            for research_id in actual_ids
            if research_id in set(ordered_newest)
        ]

        self.assert_true(
            "Research history is newest first",
            filtered == ordered_newest,
            f"expected={ordered_newest}, actual={filtered}",
        )

    def event_types_for(self, research_id: str) -> list[str]:
        with self.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT event_type
                    FROM events
                    WHERE entity_id = %s::uuid
                    ORDER BY created_at
                    """,
                    (research_id,),
                )
                return [row[0] for row in cur.fetchall()]

    def check_events(
        self,
        completed_id: str | None,
        partial_id: str | None,
        failed_id: str | None,
    ) -> None:
        try:
            if completed_id:
                events = self.event_types_for(completed_id)
                self.assert_true(
                    "COMPLETED run events written",
                    events.count("research_requested") >= 1
                    and events.count("research_started") >= 1
                    and events.count("research_source_added") >= 2
                    and events.count("research_completed") >= 1,
                    str(events),
                )

            if partial_id:
                events = self.event_types_for(partial_id)
                self.assert_true(
                    "PARTIAL run events written",
                    events.count("research_requested") >= 1
                    and events.count("research_started") >= 1
                    and events.count("research_partial") >= 1,
                    str(events),
                )

            if failed_id:
                events = self.event_types_for(failed_id)
                self.assert_true(
                    "FAILED run events written",
                    events.count("research_requested") >= 1
                    and events.count("research_started") >= 1
                    and events.count("research_failed") >= 1,
                    str(events),
                )

            if self.initial_lead_status == "DISCOVERED" and self.lead_id:
                with self.db_connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            SELECT COUNT(*)
                            FROM events
                            WHERE entity_id = %s::uuid
                              AND event_type = 'lead_status_changed'
                              AND metadata ->> 'previous_status' = 'DISCOVERED'
                              AND metadata ->> 'new_status' = 'RESEARCHING'
                            """,
                            (self.lead_id,),
                        )
                        count = cur.fetchone()[0]

                self.assert_true(
                    "DISCOVERED -> RESEARCHING lead event written",
                    count >= 1,
                    f"matching_events={count}",
                )
            else:
                self.skip(
                    "DISCOVERED -> RESEARCHING lead event check",
                    (
                        "Selected lead did not begin in DISCOVERED; "
                        f"initial={self.initial_lead_status}"
                    ),
                )
        except Exception as exc:
            self.fail("Research event checks", repr(exc))

    def summary(self) -> int:
        passes = sum(1 for result in self.results if result.status == "PASS")
        failures = sum(1 for result in self.results if result.status == "FAIL")
        skips = sum(1 for result in self.results if result.status == "SKIP")

        print("\n" + "=" * 72)
        print("LorrySystem Research API Validation Summary")
        print("=" * 72)
        print(f"PASS: {passes}")
        print(f"FAIL: {failures}")
        print(f"SKIP: {skips}")

        if self.created_research_ids:
            print("\nCreated research runs:")
            for research_id in self.created_research_ids:
                print(f"  - {research_id}")

        if failures:
            print("\nRESULT: FAILED")
            return 1

        print("\nRESULT: PASSED")
        return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the LorrySystem Research API MVP1."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Marketing API base URL.",
    )
    parser.add_argument(
        "--lead-id",
        default=None,
        help=(
            "Existing active lead UUID to use. "
            "If omitted, a DISCOVERED lead is preferred, "
            "otherwise the first active lead is used."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    validator = Validator(args.base_url)

    print("=" * 72)
    print("LorrySystem Research API MVP1 Validation")
    print("=" * 72)
    print(f"Base URL: {validator.base_url}\n")

    validator.check_openapi()
    validator.check_db_schema()
    validator.check_not_found_cases()

    lead = validator.choose_lead(args.lead_id)
    if not lead:
        return validator.summary()

    validator.lead_id = lead["id"]
    validator.initial_lead_status = lead["status"]

    print(
        f"\nUsing lead: {validator.lead_id} "
        f"(initial status: {validator.initial_lead_status})\n"
    )

    completed_id = validator.run_completed_path()
    partial_id = validator.run_partial_path()
    failed_id = validator.run_failed_path()

    validator.check_history(
        completed_id,
        partial_id,
        failed_id,
    )
    validator.check_events(
        completed_id,
        partial_id,
        failed_id,
    )

    return validator.summary()


if __name__ == "__main__":
    sys.exit(main())
#!/usr/bin/env python3
"""
LorrySystem Research API MVP1 validation suite.

Run inside the Marketing API container, for example:

    python /app/scripts/validate_research_api.py

Optional:

    python /app/scripts/validate_research_api.py \
        --lead-id dcb7d435-cf8c-4202-868f-3666dc53f8ac

What it validates:
- Required Research endpoints are registered in OpenAPI.
- Research database lifecycle schema is present.
- Nonexistent lead/research handling.
- Research run creation and history preservation.
- DISCOVERED -> RESEARCHING behavior when applicable.
- PENDING -> RUNNING -> COMPLETED.
- PENDING -> RUNNING -> PARTIAL.
- PENDING -> RUNNING -> FAILED.
- Invalid transitions return 409.
- Confidence validation returns 422.
- Multiple research sources are stored and returned.
- Research completion does not auto-qualify the lead.
- Research lifecycle events are written to PostgreSQL.

NOTE:
This is an integration test. It creates three new research runs on the
selected lead and intentionally leaves them in the database so research
history remains auditable.
"""

