#!/usr/bin/env python3
"""
LorrySystem Approval API MVP1 validation suite.

Typical run inside the Marketing API container:

    python /tmp/validate_approval_api.py \
        --lead-id dcb7d435-cf8c-4202-868f-3666dc53f8ac

The validator creates three Marketing Actions and exercises:

    submit -> approve
    submit -> reject
    submit -> request changes -> edit -> resubmit -> approve

It intentionally leaves no PENDING approval requests behind.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

try:
    import psycopg
except ImportError:
    psycopg = None


EXPECTED_ROUTES = {
    "/api/actions/{action_id}/submit": {"post"},
    "/api/approvals": {"get"},
    "/api/approvals/{approval_id}": {"get"},
    "/api/actions/{action_id}/approvals": {"get"},
    "/api/approvals/{approval_id}/approve": {"patch"},
    "/api/approvals/{approval_id}/reject": {"patch"},
    "/api/approvals/{approval_id}/request-changes": {"patch"},
}

REQUIRED_CONSTRAINTS = {
    "ck_approval_requests_status",
}

REQUIRED_INDEXES = {
    "idx_approval_requests_status",
    "idx_approval_requests_action",
    "idx_approval_requests_requested_at",
    "idx_approval_requests_one_pending",
}

TERMINAL_LEAD_STATUSES = {
    "CONVERTED",
    "DISQUALIFIED",
    "LOST",
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

        self.lead_id: str | None = None
        self.initial_lead_status: str | None = None
        self.initial_lead_score: int | None = None

        self.product_match_snapshot: list[tuple] = []

        self.created_action_ids: list[str] = []
        self.created_approval_ids: list[str] = []

    # ========================================================
    # Result helpers
    # ========================================================

    def pass_(self, name: str, detail: str = "") -> None:
        self.results.append(Result(name, "PASS", detail))
        print(
            f"[PASS] {name}"
            + (f" — {detail}" if detail else "")
        )

    def fail(self, name: str, detail: str = "") -> None:
        self.results.append(Result(name, "FAIL", detail))
        print(
            f"[FAIL] {name}"
            + (f" — {detail}" if detail else "")
        )

    def skip(self, name: str, detail: str = "") -> None:
        self.results.append(Result(name, "SKIP", detail))
        print(
            f"[SKIP] {name}"
            + (f" — {detail}" if detail else "")
        )

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
        actual: int,
        expected: int | tuple[int, ...],
        payload: Any,
    ) -> bool:
        expected_values = (
            (expected,)
            if isinstance(expected, int)
            else expected
        )

        return self.assert_true(
            name,
            actual in expected_values,
            (
                f"HTTP {actual}, "
                f"expected {expected_values}; "
                f"response={payload}"
            ),
        )

    # ========================================================
    # HTTP helpers
    # ========================================================

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        data = None
        headers: dict[str, str] = {}


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

        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=15,
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

    def get(self, path: str) -> tuple[int, Any]:
        return self.request("GET", path)

    def post(
        self,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        return self.request("POST", path, body)

    def patch(
        self,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        return self.request("PATCH", path, body)

    # ========================================================
    # DB helpers
    # ========================================================

    def db_connect(self):
        if psycopg is None:
            raise RuntimeError(
                "psycopg is not installed."
            )

        required = [
            "POSTGRES_DB",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "POSTGRES_HOST",
            "POSTGRES_PORT",
        ]

        missing = [
            key
            for key in required
            if not os.getenv(key)
        ]

        if missing:
            raise RuntimeError(
                "Missing DB environment variables: "
                + ", ".join(missing)
            )

        return psycopg.connect(
            dbname=os.environ["POSTGRES_DB"],
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            host=os.environ["POSTGRES_HOST"],
            port=os.environ["POSTGRES_PORT"],
        )

    # ========================================================
    # OpenAPI / DB schema
    # ========================================================

    def check_openapi(self) -> None:
        code, payload = self.get("/openapi.json")

        if not self.assert_true(
            "OpenAPI reachable",
            code == 200 and isinstance(payload, dict),
            f"HTTP {code}",
        ):
            return

        paths = payload.get("paths", {})

        for path, expected_methods in EXPECTED_ROUTES.items():
            actual_methods = {
                method.lower()
                for method in paths.get(path, {})
                if method.lower()
                in {
                    "get",
                    "post",
                    "put",
                    "patch",
                    "delete",
                    "options",
                    "head",
                }
            }

            self.assert_true(
                f"Route registered: {path}",
                expected_methods.issubset(actual_methods),
                (
                    f"expected={sorted(expected_methods)}, "
                    f"actual={sorted(actual_methods)}"
                ),
            )

    def check_database_schema(self) -> None:
        try:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT version_num FROM alembic_version"
                    )
                    row = cur.fetchone()
                    version = row[0] if row else None

                    self.assert_true(
                        "Alembic head is 008",
                        version == "008",
                        f"version={version}",
                    )

                    cur.execute(
                        """
                        SELECT
                            column_name,
                            is_nullable,
                            column_default
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'approval_requests'
                        """
                    )

                    columns = {
                        row[0]: {
                            "nullable": row[1],
                            "default": row[2],
                        }
                        for row in cur.fetchall()
                    }

                    required_columns = {
                        "id",
                        "marketing_action_id",
                        "status",
                        "requested_at",
                        "decided_by",
                        "decided_at",
                        "reviewer_notes",
                        "content_snapshot",
                        "created_at",
                        "updated_at",
                    }

                    self.assert_true(
                        "approval_requests columns present",
                        required_columns.issubset(
                            columns.keys()
                        ),
                        str(sorted(columns.keys())),
                    )

                    self.assert_true(
                        "marketing_action_id is NOT NULL",
                        columns.get(
                            "marketing_action_id",
                            {},
                        ).get("nullable")
                        == "NO",
                    )

                    self.assert_true(
                        "status is NOT NULL",
                        columns.get(
                            "status",
                            {},
                        ).get("nullable")
                        == "NO",
                    )

                    self.assert_true(
                        "content_snapshot is NOT NULL",
                        columns.get(
                            "content_snapshot",
                            {},
                        ).get("nullable")
                        == "NO",
                    )

                    self.assert_true(
                        "status DB default is PENDING",
                        "PENDING"
                        in str(
                            columns.get(
                                "status",
                                {},
                            ).get("default")
                        ),
                        str(
                            columns.get(
                                "status",
                                {},
                            ).get("default")
                        ),
                    )

                    cur.execute(
                        """
                        SELECT conname
                        FROM pg_constraint c
                        JOIN pg_class t
                          ON t.oid = c.conrelid
                        JOIN pg_namespace n
                          ON n.oid = t.relnamespace
                        WHERE n.nspname = 'public'
                          AND t.relname = 'approval_requests'
                        """
                    )

                    constraints = {
                        row[0]
                        for row in cur.fetchall()
                    }

                    for name in sorted(
                        REQUIRED_CONSTRAINTS
                    ):
                        self.assert_true(
                            f"Constraint exists: {name}",
                            name in constraints,
                            str(sorted(constraints)),
                        )

                    cur.execute(
                        """
                        SELECT indexname, indexdef
                        FROM pg_indexes
                        WHERE schemaname = 'public'
                          AND tablename = 'approval_requests'
                        """
                    )

                    indexes = {
                        row[0]: row[1]
                        for row in cur.fetchall()
                    }

                    for name in sorted(
                        REQUIRED_INDEXES
                    ):
                        self.assert_true(
                            f"Index exists: {name}",
                            name in indexes,
                            indexes.get(name, ""),
                        )

                    pending_index = indexes.get(
                        "idx_approval_requests_one_pending",
                        "",
                    )

                    self.assert_true(
                        "one-PENDING index is UNIQUE",
                        "UNIQUE INDEX"
                        in pending_index.upper(),
                        pending_index,
                    )

                    self.assert_true(
                        "one-PENDING index has partial predicate",
                        (
                            "WHERE"
                            in pending_index.upper()
                            and "PENDING"
                            in pending_index.upper()
                        ),
                        pending_index,
                    )

        except Exception as exc:
            self.fail(
                "Database schema checks",
                repr(exc),
            )

    # ========================================================
    # Lead fixture / safety snapshots
    # ========================================================

    def choose_lead(
        self,
        explicit_lead_id: str | None,
    ) -> dict[str, Any] | None:
        if explicit_lead_id:
            code, lead = self.get(
                f"/api/leads/{explicit_lead_id}"
            )

            if not self.assert_http(
                "Selected lead exists",
                code,
                200,
                lead,
            ):
                return None

            return lead

        code, leads = self.get("/api/leads")

        if code != 200 or not isinstance(leads, list):
            self.fail(
                "List leads",
                f"HTTP {code}: {leads}",
            )
            return None

        for lead in leads:
            if (
                lead.get("status")
                not in TERMINAL_LEAD_STATUSES
                and lead.get("current_score")
                is not None
            ):
                m_code, matches = self.get(
                    f"/api/leads/{lead['id']}/product-matches"
                )

                if (
                    m_code == 200
                    and isinstance(matches, list)
                    and matches
                ):
                    self.pass_(
                        "Auto-selected Approval-eligible lead",
                        (
                            f"{lead['id']} "
                            f"(status={lead['status']}, "
                            f"score={lead['current_score']})"
                        ),
                    )
                    return lead

        self.fail(
            "Find Approval-eligible lead",
            (
                "No non-terminal scored lead "
                "with a ProductMatch was found."
            ),
        )
        return None

    def validate_lead(
        self,
        lead: dict[str, Any],
    ) -> bool:
        self.lead_id = lead["id"]
        self.initial_lead_status = lead["status"]
        self.initial_lead_score = lead.get(
            "current_score"
        )

        scored = self.assert_true(
            "Selected lead has current score",
            self.initial_lead_score is not None,
            f"current_score={self.initial_lead_score}",
        )

        non_terminal = self.assert_true(
            "Selected lead is non-terminal",
            self.initial_lead_status
            not in TERMINAL_LEAD_STATUSES,
            f"status={self.initial_lead_status}",
        )

        code, matches = self.get(
            f"/api/leads/{self.lead_id}/product-matches"
        )

        self.assert_http(
            "ProductMatch prerequisite endpoint",
            code,
            200,
            matches,
        )

        has_match = (
            code == 200
            and isinstance(matches, list)
            and len(matches) >= 1
        )

        self.assert_true(
            "Selected lead has ProductMatch",
            has_match,
            (
                f"count="
                f"{len(matches) if isinstance(matches, list) else 'n/a'}"
            ),
        )

        return (
            scored
            and non_terminal
            and has_match
        )

    def snapshot_product_matches(self) -> None:
        assert self.lead_id is not None

        try:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            id::text,
                            product_id::text,
                            fit_score,
                            rationale,
                            created_at,
                            updated_at
                        FROM product_matches
                        WHERE lead_id = %s::uuid
                        ORDER BY id
                        """,
                        (self.lead_id,),
                    )

                    self.product_match_snapshot = (
                        cur.fetchall()
                    )

                    self.pass_(
                        "ProductMatch baseline captured",
                        (
                            f"count="
                            f"{len(self.product_match_snapshot)}"
                        ),
                    )

        except Exception as exc:
            self.fail(
                "Capture ProductMatch baseline",
                repr(exc),
            )

    # ========================================================
    # Negative endpoint / schema validation
    # ========================================================

    def check_not_found_cases(self) -> None:
        fake_action = str(uuid.uuid4())
        fake_approval = str(uuid.uuid4())

        code, payload = self.post(
            f"/api/actions/{fake_action}/submit"
        )
        self.assert_http(
            "Unknown action submit -> 404",
            code,
            404,
            payload,
        )

        code, payload = self.get(
            f"/api/approvals/{fake_approval}"
        )
        self.assert_http(
            "Unknown approval detail -> 404",
            code,
            404,
            payload,
        )

        for suffix, body, name in [
            (
                "approve",
                {"decided_by": "validator"},
                "Unknown approval approve -> 404",
            ),
            (
                "reject",
                {
                    "decided_by": "validator",
                    "reviewer_notes": "Reject test",
                },
                "Unknown approval reject -> 404",
            ),
            (
                "request-changes",
                {
                    "decided_by": "validator",
                    "reviewer_notes": "Change test",
                },
                "Unknown approval request-changes -> 404",
            ),
        ]:
            code, payload = self.patch(
                (
                    f"/api/approvals/"
                    f"{fake_approval}/{suffix}"
                ),
                body,
            )

            self.assert_http(
                name,
                code,
                404,
                payload,
            )

        code, payload = self.get(
            (
                "/api/approvals?"
                + urllib.parse.urlencode(
                    {"status": "WHATEVER"}
                )
            )
        )

        self.assert_http(
            "Invalid approval status filter -> 422",
            code,
            422,
            payload,
        )

    # ========================================================
    # Marketing Action creation
    # ========================================================

    def create_linkedin_draft(
        self,
        label: str,
        content: str,
    ) -> dict[str, Any] | None:
        assert self.lead_id is not None

        payload = {
            "channel": "LINKEDIN",
            "action_type": "POST",
            "content": content,
            "created_by": (
                "approval-api-validator"
            ),
        }

        code, action = self.post(
            f"/api/leads/{self.lead_id}/actions",
            payload,
        )

        if not self.assert_http(
            f"Create {label} DRAFT action",
            code,
            201,
            action,
        ):
            return None

        self.created_action_ids.append(
            action["id"]
        )

        self.assert_true(
            f"{label} action starts DRAFT",
            action.get("status") == "DRAFT",
            str(action.get("status")),
        )

        return action

    # ========================================================
    # Submission / snapshot
    # ========================================================

    def expected_snapshot(
        self,
        action: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "marketing_action_id": action["id"],
            "lead_id": action["lead_id"],
            "contact_id": action["contact_id"],
            "channel": action["channel"],
            "action_type": action["action_type"],
            "subject": action["subject"],
            "content": action["content"],
            "scheduled_at": action["scheduled_at"],
            "created_by": action["created_by"],
        }

    def submit(
        self,
        action: dict[str, Any],
        label: str,
    ) -> dict[str, Any] | None:
        code, approval = self.post(
            f"/api/actions/{action['id']}/submit"
        )

        if not self.assert_http(
            f"Submit {label} for approval",
            code,
            201,
            approval,
        ):
            return None

        self.created_approval_ids.append(
            approval["id"]
        )

        self.assert_true(
            f"{label} approval status = PENDING",
            approval.get("status") == "PENDING",
            str(approval.get("status")),
        )

        self.assert_true(
            (
                f"{label} MarketingAction status "
                "= PENDING_APPROVAL"
            ),
            approval.get(
                "marketing_action_status"
            )
            == "PENDING_APPROVAL",
            str(
                approval.get(
                    "marketing_action_status"
                )
            ),
        )

        self.assert_true(
            f"{label} approval action reference correct",
            approval.get("marketing_action_id")
            == action["id"],
            str(approval.get("marketing_action_id")),
        )

        expected = self.expected_snapshot(
            action
        )

        self.assert_true(
            f"{label} content snapshot exact",
            approval.get("content_snapshot")
            == expected,
            (
                f"expected={expected}; "
                f"actual="
                f"{approval.get('content_snapshot')}"
            ),
        )

        self.assert_true(
            f"{label} requested_at present",
            bool(approval.get("requested_at")),
            str(approval.get("requested_at")),
        )

        return approval

    def check_duplicate_submit(
        self,
        action_id: str,
    ) -> None:
        code, payload = self.post(
            f"/api/actions/{action_id}/submit"
        )

        self.assert_http(
            "Duplicate submit while pending rejected",
            code,
            409,
            payload,
        )

    def check_pending_action_locked(
        self,
        action_id: str,
    ) -> None:
        code, payload = self.patch(
            f"/api/actions/{action_id}",
            {
                "content": (
                    "This edit must fail while "
                    "approval is pending."
                )
            },
        )

        self.assert_http(
            "PENDING_APPROVAL action cannot be edited",
            code,
            409,
            payload,
        )

        code, payload = self.patch(
            f"/api/actions/{action_id}/cancel"
        )

        self.assert_http(
            "PENDING_APPROVAL action cannot be cancelled",
            code,
            409,
            payload,
        )

    # ========================================================
    # Approval reads / lists
    # ========================================================

    def check_approval_detail(
        self,
        approval: dict[str, Any],
    ) -> None:
        code, detail = self.get(
            f"/api/approvals/{approval['id']}"
        )

        if not self.assert_http(
            "Approval detail retrieval",
            code,
            200,
            detail,
        ):
            return

        self.assert_true(
            "Approval detail ID matches",
            detail.get("id")
            == approval.get("id"),
            str(detail.get("id")),
        )

        self.assert_true(
            "Approval detail snapshot matches",
            detail.get("content_snapshot")
            == approval.get("content_snapshot"),
            str(detail.get("content_snapshot")),
        )

    def check_pending_list(
        self,
        approval_ids: list[str],
    ) -> None:
        code, approvals = self.get(
            "/api/approvals?status=PENDING"
        )

        if not self.assert_http(
            "Pending approval list retrieval",
            code,
            200,
            approvals,
        ):
            return

        if not isinstance(approvals, list):
            self.fail(
                "Pending approval list is a list",
                repr(approvals),
            )
            return

        self.pass_(
            "Pending approval list is a list",
            f"count={len(approvals)}",
        )

        returned = {
            item.get("id")
            for item in approvals
        }

        self.assert_true(
            "All validation pending approvals are listed",
            set(approval_ids).issubset(
                returned
            ),
            str(sorted(returned)),
        )

        self.assert_true(
            "PENDING filter returns only PENDING rows",
            all(
                item.get("status") == "PENDING"
                for item in approvals
            ),
            str(
                [
                    item.get("status")
                    for item in approvals
                ]
            ),
        )

    def check_action_history(
        self,
        action_id: str,
        expected_ids: list[str],
    ) -> list[dict[str, Any]] | None:
        code, history = self.get(
            f"/api/actions/{action_id}/approvals"
        )

        if not self.assert_http(
            "Action approval history retrieval",
            code,
            200,
            history,
        ):
            return None

        if not isinstance(history, list):
            self.fail(
                "Action approval history is a list",
                repr(history),
            )
            return None

        self.pass_(
            "Action approval history is a list",
            f"count={len(history)}",
        )

        ids = [
            item.get("id")
            for item in history
        ]

        self.assert_true(
            "Expected approval history rows preserved",
            all(
                approval_id in ids
                for approval_id in expected_ids
            ),
            str(ids),
        )

        if len(expected_ids) >= 2:
            newest = expected_ids[-1]
            oldest = expected_ids[0]

            if (
                newest in ids
                and oldest in ids
            ):
                self.assert_true(
                    "Approval history is newest first",
                    ids.index(newest)
                    < ids.index(oldest),
                    str(ids),
                )

        return history

    # ========================================================
    # Decision payload validation
    # ========================================================

    def check_decision_payload_validation(
        self,
        approval_id: str,
    ) -> None:
        cases = [
            (
                "Approve blank decided_by rejected",
                "approve",
                {"decided_by": "   "},
            ),
            (
                "Reject missing notes rejected",
                "reject",
                {"decided_by": "validator"},
            ),
            (
                "Reject blank notes rejected",
                "reject",
                {
                    "decided_by": "validator",
                    "reviewer_notes": "   ",
                },
            ),
            (
                "Request changes missing notes rejected",
                "request-changes",
                {"decided_by": "validator"},
            ),
            (
                "Request changes blank notes rejected",
                "request-changes",
                {
                    "decided_by": "validator",
                    "reviewer_notes": "   ",
                },
            ),
        ]

        for name, suffix, body in cases:
            code, payload = self.patch(
                (
                    f"/api/approvals/"
                    f"{approval_id}/{suffix}"
                ),
                body,
            )

            self.assert_http(
                name,
                code,
                422,
                payload,
            )

    # ========================================================
    # Decision flows
    # ========================================================

    def approve_flow(
        self,
        approval: dict[str, Any],
        action: dict[str, Any],
    ) -> dict[str, Any] | None:
        code, decided = self.patch(
            (
                f"/api/approvals/"
                f"{approval['id']}/approve"
            ),
            {
                "decided_by": "validator",
                "reviewer_notes": (
                    "Approved by automated validator."
                ),
            },
        )

        if not self.assert_http(
            "Approve PENDING approval succeeds",
            code,
            200,
            decided,
        ):
            return None

        self.assert_true(
            "Approval transitioned to APPROVED",
            decided.get("status") == "APPROVED",
            str(decided.get("status")),
        )

        self.assert_true(
            "MarketingAction transitioned to APPROVED",
            decided.get("marketing_action_status")
            == "APPROVED",
            str(
                decided.get(
                    "marketing_action_status"
                )
            ),
        )

        self.assert_true(
            "Approve decided_by stored",
            decided.get("decided_by")
            == "validator",
            str(decided.get("decided_by")),
        )

        self.assert_true(
            "Approve decided_at stored",
            bool(decided.get("decided_at")),
            str(decided.get("decided_at")),
        )

        self.assert_true(
            "Approved snapshot preserved",
            decided.get("content_snapshot")
            == approval.get("content_snapshot"),
            str(decided.get("content_snapshot")),
        )

        code, payload = self.patch(
            (
                f"/api/approvals/"
                f"{approval['id']}/approve"
            ),
            {"decided_by": "validator"},
        )

        self.assert_http(
            "Approve non-PENDING approval rejected",
            code,
            409,
            payload,
        )

        code, payload = self.patch(
            f"/api/actions/{action['id']}",
            {"content": "Must not edit approved content."},
        )

        self.assert_http(
            "APPROVED MarketingAction is not editable",
            code,
            409,
            payload,
        )

        code, payload = self.patch(
            f"/api/actions/{action['id']}/cancel"
        )

        self.assert_http(
            "APPROVED MarketingAction cannot be cancelled",
            code,
            409,
            payload,
        )

        return decided

    def reject_flow(
        self,
        approval: dict[str, Any],
    ) -> dict[str, Any] | None:
        code, decided = self.patch(
            (
                f"/api/approvals/"
                f"{approval['id']}/reject"
            ),
            {
                "decided_by": "validator",
                "reviewer_notes": (
                    "Rejected by automated validator."
                ),
            },
        )

        if not self.assert_http(
            "Reject PENDING approval succeeds",
            code,
            200,
            decided,
        ):
            return None

        self.assert_true(
            "Approval transitioned to REJECTED",
            decided.get("status") == "REJECTED",
            str(decided.get("status")),
        )

        self.assert_true(
            "MarketingAction transitioned to REJECTED",
            decided.get("marketing_action_status")
            == "REJECTED",
            str(
                decided.get(
                    "marketing_action_status"
                )
            ),
        )

        self.assert_true(
            "Reject reviewer notes stored",
            decided.get("reviewer_notes")
            == "Rejected by automated validator.",
            str(decided.get("reviewer_notes")),
        )

        code, payload = self.patch(
            (
                f"/api/approvals/"
                f"{approval['id']}/reject"
            ),
            {
                "decided_by": "validator",
                "reviewer_notes": "Again",
            },
        )

        self.assert_http(
            "Reject non-PENDING approval rejected",
            code,
            409,
            payload,
        )

        return decided

    def request_changes_flow(
        self,
        approval: dict[str, Any],
    ) -> dict[str, Any] | None:
        code, decided = self.patch(
            (
                f"/api/approvals/"
                f"{approval['id']}/request-changes"
            ),
            {
                "decided_by": "validator",
                "reviewer_notes": (
                    "Please revise the validation content."
                ),
            },
        )

        if not self.assert_http(
            "Request Changes succeeds",
            code,
            200,
            decided,
        ):
            return None

        self.assert_true(
            "Approval transitioned to CHANGES_REQUESTED",
            decided.get("status")
            == "CHANGES_REQUESTED",
            str(decided.get("status")),
        )

        self.assert_true(
            "MarketingAction returned to DRAFT",
            decided.get("marketing_action_status")
            == "DRAFT",
            str(
                decided.get(
                    "marketing_action_status"
                )
            ),
        )

        code, payload = self.patch(
            (
                f"/api/approvals/"
                f"{approval['id']}/request-changes"
            ),
            {
                "decided_by": "validator",
                "reviewer_notes": "Again",
            },
        )

        self.assert_http(
            "Request Changes on non-PENDING rejected",
            code,
            409,
            payload,
        )

        return decided

    # ========================================================
    # Changes / resubmission flow
    # ========================================================

    def edit_after_changes(
        self,
        action_id: str,
    ) -> dict[str, Any] | None:
        new_content = (
            "Revised approval validation content "
            "after requested changes."
        )

        code, updated = self.patch(
            f"/api/actions/{action_id}",
            {"content": new_content},
        )

        if not self.assert_http(
            "DRAFT editable after changes requested",
            code,
            200,
            updated,
        ):
            return None

        self.assert_true(
            "Revised content persisted",
            updated.get("content")
            == new_content,
            str(updated.get("content")),
        )

        self.assert_true(
            "Action remains DRAFT after edit",
            updated.get("status") == "DRAFT",
            str(updated.get("status")),
        )

        return updated

    def check_resubmission(
        self,
        updated_action: dict[str, Any],
        old_approval: dict[str, Any],
    ) -> dict[str, Any] | None:
        old_snapshot = dict(
            old_approval["content_snapshot"]
        )

        new_approval = self.submit(
            updated_action,
            "resubmitted changed action",
        )

        if not new_approval:
            return None

        self.assert_true(
            "Resubmission creates NEW ApprovalRequest",
            new_approval["id"]
            != old_approval["id"],
            (
                f"old={old_approval['id']}, "
                f"new={new_approval['id']}"
            ),
        )

        self.assert_true(
            "New snapshot contains revised content",
            new_approval["content_snapshot"].get(
                "content"
            )
            == updated_action["content"],
            str(
                new_approval.get(
                    "content_snapshot"
                )
            ),
        )

        self.assert_true(
            "New snapshot differs from old snapshot",
            new_approval["content_snapshot"]
            != old_snapshot,
            (
                f"old={old_snapshot}; "
                f"new="
                f"{new_approval['content_snapshot']}"
            ),
        )

        code, old_detail = self.get(
            f"/api/approvals/{old_approval['id']}"
        )

        if self.assert_http(
            "Old approval still retrievable after resubmit",
            code,
            200,
            old_detail,
        ):
            self.assert_true(
                "Old ApprovalRequest remains CHANGES_REQUESTED",
                old_detail.get("status")
                == "CHANGES_REQUESTED",
                str(old_detail.get("status")),
            )

            self.assert_true(
                "Old content snapshot is immutable",
                old_detail.get("content_snapshot")
                == old_snapshot,
                (
                    f"expected={old_snapshot}; "
                    f"actual="
                    f"{old_detail.get('content_snapshot')}"
                ),
            )

        history = self.check_action_history(
            updated_action["id"],
            [
                old_approval["id"],
                new_approval["id"],
            ],
        )

        if history is not None:
            self.assert_true(
                "Resubmission history contains two approvals",
                len(
                    [
                        item
                        for item in history
                        if item.get("id")
                        in {
                            old_approval["id"],
                            new_approval["id"],
                        }
                    ]
                )
                == 2,
                str(
                    [
                        item.get("id")
                        for item in history
                    ]
                ),
            )

        return new_approval

    # ========================================================
    # Cross-module safety
    # ========================================================

    def check_lead_unchanged(self) -> None:
        assert self.lead_id is not None

        code, lead = self.get(
            f"/api/leads/{self.lead_id}"
        )

        if not self.assert_http(
            "Lead readable after Approval lifecycle",
            code,
            200,
            lead,
        ):
            return

        self.assert_true(
            "Approval does not mutate lead status",
            lead.get("status")
            == self.initial_lead_status,
            (
                f"initial={self.initial_lead_status}; "
                f"current={lead.get('status')}"
            ),
        )

        self.assert_true(
            "Approval does not mutate lead current_score",
            lead.get("current_score")
            == self.initial_lead_score,
            (
                f"initial={self.initial_lead_score}; "
                f"current={lead.get('current_score')}"
            ),
        )

    def check_product_matches_unchanged(self) -> None:
        assert self.lead_id is not None

        try:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            id::text,
                            product_id::text,
                            fit_score,
                            rationale,
                            created_at,
                            updated_at
                        FROM product_matches
                        WHERE lead_id = %s::uuid
                        ORDER BY id
                        """,
                        (self.lead_id,),
                    )

                    current = cur.fetchall()

                    self.assert_true(
                        "Approval does not modify ProductMatches",
                        current
                        == self.product_match_snapshot,
                        (
                            f"before="
                            f"{self.product_match_snapshot}; "
                            f"after={current}"
                        ),
                    )

        except Exception as exc:
            self.fail(
                "ProductMatch safety check",
                repr(exc),
            )

    # ========================================================
    # DB invariants / events
    # ========================================================

    def check_database_records(self) -> None:
        if not self.created_approval_ids:
            return

        try:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            id::text,
                            marketing_action_id::text,
                            status,
                            decided_by,
                            decided_at,
                            content_snapshot
                        FROM approval_requests
                        WHERE id = ANY(%s::uuid[])
                        """,
                        (self.created_approval_ids,),
                    )

                    rows = cur.fetchall()

                    self.assert_true(
                        "Created ApprovalRequests persisted",
                        len(rows)
                        == len(
                            self.created_approval_ids
                        ),
                        f"rows={rows}",
                    )

                    self.assert_true(
                        "Validator leaves no created approvals PENDING",
                        all(
                            row[2] != "PENDING"
                            for row in rows
                        ),
                        str(
                            [
                                (
                                    row[0],
                                    row[2],
                                )
                                for row in rows
                            ]
                        ),
                    )

                    cur.execute(
                        """
                        SELECT
                            marketing_action_id::text,
                            COUNT(*)
                        FROM approval_requests
                        WHERE status = 'PENDING'
                        GROUP BY marketing_action_id
                        HAVING COUNT(*) > 1
                        """
                    )

                    duplicates = cur.fetchall()

                    self.assert_true(
                        "DB has no duplicate PENDING approvals",
                        len(duplicates) == 0,
                        str(duplicates),
                    )

        except Exception as exc:
            self.fail(
                "Approval DB invariant checks",
                repr(exc),
            )

    def check_events(
        self,
        expected: dict[str, str],
    ) -> None:
        try:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            entity_id::text,
                            event_type,
                            metadata
                        FROM events
                        WHERE entity_type = 'APPROVAL'
                          AND entity_id = ANY(%s::uuid[])
                        ORDER BY created_at
                        """,
                        (
                            list(expected.keys()),
                        ),
                    )

                    rows = cur.fetchall()

                    by_approval: dict[
                        str,
                        list[tuple[str, dict]]
                    ] = {}

                    for (
                        entity_id,
                        event_type,
                        metadata,
                    ) in rows:
                        by_approval.setdefault(
                            entity_id,
                            [],
                        ).append(
                            (
                                event_type,
                                metadata,
                            )
                        )

                    for (
                        approval_id,
                        decision_event,
                    ) in expected.items():
                        events = by_approval.get(
                            approval_id,
                            [],
                        )

                        types = [
                            event_type
                            for event_type, _
                            in events
                        ]

                        self.assert_true(
                            (
                                "approval_requested exists "
                                f"for {approval_id}"
                            ),
                            "approval_requested"
                            in types,
                            str(types),
                        )

                        self.assert_true(
                            (
                                f"{decision_event} exists "
                                f"for {approval_id}"
                            ),
                            decision_event
                            in types,
                            str(types),
                        )

                        for (
                            event_type,
                            metadata,
                        ) in events:
                            self.assert_true(
                                (
                                    f"{event_type} references "
                                    "correct approval"
                                ),
                                metadata.get(
                                    "approval_id"
                                )
                                == approval_id,
                                str(metadata),
                            )

        except Exception as exc:
            self.fail(
                "Approval event checks",
                repr(exc),
            )

    def check_marketing_action_submitted_events(
        self,
    ) -> None:
        if not self.created_action_ids:
            return

        try:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            entity_id::text,
                            event_type,
                            metadata
                        FROM events
                        WHERE entity_type = 'MARKETING_ACTION'
                          AND entity_id = ANY(%s::uuid[])
                          AND event_type =
                              'marketing_action_submitted'
                        """,
                        (self.created_action_ids,),
                    )

                    rows = cur.fetchall()

                    actions_with_submit = {
                        row[0]
                        for row in rows
                    }

                    self.assert_true(
                        "marketing_action_submitted events exist",
                        set(
                            self.created_action_ids
                        ).issubset(
                            actions_with_submit
                        ),
                        str(
                            sorted(
                                actions_with_submit
                            )
                        ),
                    )

        except Exception as exc:
            self.fail(
                "Marketing Action submitted-event checks",
                repr(exc),
            )

    # ========================================================
    # Summary
    # ========================================================

    def summary(self) -> int:
        passes = sum(
            1
            for result in self.results
            if result.status == "PASS"
        )

        failures = sum(
            1
            for result in self.results
            if result.status == "FAIL"
        )

        skips = sum(
            1
            for result in self.results
            if result.status == "SKIP"
        )

        print("\n" + "=" * 72)
        print(
            "LorrySystem Approval API "
            "Validation Summary"
        )
        print("=" * 72)

        print(f"PASS: {passes}")
        print(f"FAIL: {failures}")
        print(f"SKIP: {skips}")

        if self.created_action_ids:
            print("\nCreated validation actions:")
            for action_id in self.created_action_ids:
                print(f"  - {action_id}")

        if self.created_approval_ids:
            print("\nCreated validation approvals:")
            for approval_id in self.created_approval_ids:
                print(f"  - {approval_id}")

        if failures:
            print("\nRESULT: FAILED")
            return 1

        print("\nRESULT: PASSED")
        return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate LorrySystem Approval API MVP1."
        )
    )

    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
    )

    parser.add_argument(
        "--lead-id",
        default=None,
        help=(
            "Eligible lead with current_score "
            "and at least one ProductMatch."
        ),
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    validator = Validator(
        args.base_url
    )

    print("=" * 72)
    print(
        "LorrySystem Approval API MVP1 Validation"
    )
    print("=" * 72)
    print(
        f"Base URL: {validator.base_url}\n"
    )

    validator.check_openapi()
    validator.check_database_schema()

    lead = validator.choose_lead(
        args.lead_id
    )

    if not lead:
        return validator.summary()

    if not validator.validate_lead(
        lead
    ):
        return validator.summary()

    validator.snapshot_product_matches()

    print(
        f"\nUsing lead: {validator.lead_id} "
        f"(status={validator.initial_lead_status}, "
        f"current_score={validator.initial_lead_score})\n"
    )

    validator.check_not_found_cases()

    approve_action = validator.create_linkedin_draft(
        "approve-flow",
        (
            "Approval validator draft "
            "for the approve flow."
        ),
    )

    reject_action = validator.create_linkedin_draft(
        "reject-flow",
        (
            "Approval validator draft "
            "for the reject flow."
        ),
    )

    changes_action = validator.create_linkedin_draft(
        "changes-flow",
        (
            "Approval validator draft "
            "before requested changes."
        ),
    )

    if not all(
        [
            approve_action,
            reject_action,
            changes_action,
        ]
    ):
        return validator.summary()

    approve_pending = validator.submit(
        approve_action,
        "approve-flow",
    )

    reject_pending = validator.submit(
        reject_action,
        "reject-flow",
    )

    changes_pending = validator.submit(
        changes_action,
        "changes-flow",
    )

    if not all(
        [
            approve_pending,
            reject_pending,
            changes_pending,
        ]
    ):
        return validator.summary()

    validator.check_duplicate_submit(
        approve_action["id"]
    )

    validator.check_pending_action_locked(
        approve_action["id"]
    )

    validator.check_approval_detail(
        approve_pending
    )

    validator.check_pending_list(
        [
            approve_pending["id"],
            reject_pending["id"],
            changes_pending["id"],
        ]
    )

    validator.check_decision_payload_validation(
        approve_pending["id"]
    )

    approved = validator.approve_flow(
        approve_pending,
        approve_action,
    )

    rejected = validator.reject_flow(
        reject_pending
    )

    changes_decided = (
        validator.request_changes_flow(
            changes_pending
        )
    )

    if not all(
        [
            approved,
            rejected,
            changes_decided,
        ]
    ):
        return validator.summary()

    revised_action = validator.edit_after_changes(
        changes_action["id"]
    )

    if not revised_action:
        return validator.summary()

    resubmitted = validator.check_resubmission(
        revised_action,
        changes_pending,
    )

    if not resubmitted:
        return validator.summary()

    resubmission_approved = validator.approve_flow(
        resubmitted,
        revised_action,
    )

    if not resubmission_approved:
        return validator.summary()

    validator.check_lead_unchanged()
    validator.check_product_matches_unchanged()

    validator.check_database_records()

    validator.check_events(
        {
            approve_pending["id"]:
                "approval_approved",
            reject_pending["id"]:
                "approval_rejected",
            changes_pending["id"]:
                "approval_changes_requested",
            resubmitted["id"]:
                "approval_approved",
        }
    )

    validator.check_marketing_action_submitted_events()

    return validator.summary()


if __name__ == "__main__":
    sys.exit(main())
