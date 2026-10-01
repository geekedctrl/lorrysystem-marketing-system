#!/usr/bin/env python3
"""
LorrySystem Marketing Actions API MVP1 validation suite.

Typical run inside the Marketing API container:

    python /tmp/validate_marketing_actions_api.py \
        --lead-id dcb7d435-cf8c-4202-868f-3666dc53f8ac

Optional fixture IDs:

    --no-score-lead-id <uuid>
    --no-match-lead-id <uuid>
    --terminal-lead-id <uuid>
    --foreign-contact-id <uuid>

The validator creates two Marketing Actions for the selected eligible lead.
Both are cancelled before the run finishes, so no active validation drafts
are intentionally left behind.
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
from datetime import datetime, timedelta, timezone
from typing import Any

try:
    import psycopg
except ImportError:
    psycopg = None


EXPECTED_ROUTES = {
    "/api/leads/{lead_id}/actions": {"get", "post"},
    "/api/actions/{action_id}": {"get", "patch"},
    "/api/actions/{action_id}/cancel": {"patch"},
}

TERMINAL_LEAD_STATUSES = {
    "CONVERTED",
    "DISQUALIFIED",
    "LOST",
}

REQUIRED_CONSTRAINTS = {
    "ck_marketing_actions_channel",
    "ck_marketing_actions_action_type",
    "ck_marketing_actions_status",
    "ck_marketing_actions_channel_action_pair",
}

REQUIRED_INDEXES = {
    "idx_marketing_actions_lead",
    "idx_marketing_actions_status",
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
        self.lead_company_id: str | None = None
        self.contact_id: str | None = None
        self.initial_lead_status: str | None = None
        self.initial_lead_score: int | None = None

        self.product_match_snapshot: list[tuple] = []
        self.created_action_ids: list[str] = []

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
            name
            for name in required
            if not os.getenv(name)
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
    # OpenAPI / schema / migration
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
                for method in paths.get(path, {}).keys()
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
                        """
                        SELECT version_num
                        FROM alembic_version
                        """
                    )
                    row = cur.fetchone()
                    version = row[0] if row else None

                    self.assert_true(
                        "Alembic revision is present",
                        version is not None,
                        f"current_head={version}",
                    )

                    cur.execute(
                        """
                        SELECT
                            column_name,
                            is_nullable,
                            column_default
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'marketing_actions'
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
                        "lead_id",
                        "contact_id",
                        "channel",
                        "action_type",
                        "subject",
                        "content",
                        "status",
                        "scheduled_at",
                        "executed_at",
                        "external_reference",
                        "created_by",
                        "created_at",
                        "updated_at",
                    }

                    self.assert_true(
                        "marketing_actions columns present",
                        required_columns.issubset(
                            columns.keys()
                        ),
                        str(sorted(columns.keys())),
                    )

                    self.assert_true(
                        "channel is NOT NULL",
                        columns.get("channel", {}).get(
                            "nullable"
                        )
                        == "NO",
                    )

                    self.assert_true(
                        "action_type is NOT NULL",
                        columns.get("action_type", {}).get(
                            "nullable"
                        )
                        == "NO",
                    )

                    self.assert_true(
                        "content is NOT NULL",
                        columns.get("content", {}).get(
                            "nullable"
                        )
                        == "NO",
                    )

                    self.assert_true(
                        "status is NOT NULL",
                        columns.get("status", {}).get(
                            "nullable"
                        )
                        == "NO",
                    )

                    self.assert_true(
                        "status DB default is DRAFT",
                        "DRAFT"
                        in str(
                            columns.get(
                                "status",
                                {},
                            ).get(
                                "default"
                            )
                        ),
                        str(
                            columns.get(
                                "status",
                                {},
                            ).get(
                                "default"
                            )
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
                          AND t.relname = 'marketing_actions'
                        """
                    )

                    constraints = {
                        row[0]
                        for row in cur.fetchall()
                    }

                    for constraint in sorted(
                        REQUIRED_CONSTRAINTS
                    ):
                        self.assert_true(
                            f"Constraint exists: {constraint}",
                            constraint in constraints,
                            str(sorted(constraints)),
                        )

                    cur.execute(
                        """
                        SELECT indexname
                        FROM pg_indexes
                        WHERE schemaname = 'public'
                          AND tablename = 'marketing_actions'
                        """
                    )

                    indexes = {
                        row[0]
                        for row in cur.fetchall()
                    }

                    for index in sorted(REQUIRED_INDEXES):
                        self.assert_true(
                            f"Index exists: {index}",
                            index in indexes,
                            str(sorted(indexes)),
                        )

        except Exception as exc:
            self.fail(
                "Database schema checks",
                repr(exc),
            )

    # ========================================================
    # Lead / ProductMatch / contact fixtures
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
                        "Auto-selected eligible lead",
                        (
                            f"{lead['id']} "
                            f"(status={lead['status']}, "
                            f"current_score="
                            f"{lead['current_score']})"
                        ),
                    )
                    return lead

        self.fail(
            "Find Marketing-Action-eligible lead",
            (
                "No non-terminal lead with "
                "current_score and ProductMatch found."
            ),
        )
        return None

    def validate_selected_lead(
        self,
        lead: dict[str, Any],
    ) -> bool:
        self.lead_id = lead["id"]
        self.lead_company_id = lead["company_id"]
        self.initial_lead_status = lead["status"]
        self.initial_lead_score = lead.get(
            "current_score"
        )

        scored = self.assert_true(
            "Selected lead has current score",
            self.initial_lead_score is not None,
            (
                f"current_score="
                f"{self.initial_lead_score}"
            ),
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

        has_matches = (
            self.assert_http(
                "ProductMatch prerequisite endpoint",
                code,
                200,
                matches,
            )
            and isinstance(matches, list)
            and len(matches) >= 1
        )

        self.assert_true(
            "Selected lead has ProductMatch",
            bool(has_matches),
            (
                f"count="
                f"{len(matches) if isinstance(matches, list) else 'n/a'}"
            ),
        )

        return (
            scored
            and non_terminal
            and bool(has_matches)
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

    def choose_email_contact(
        self,
        lead: dict[str, Any],
    ) -> dict[str, Any] | None:
        primary_contact_id = lead.get(
            "primary_contact_id"
        )

        if primary_contact_id:
            code, contact = self.get(
                f"/api/contacts/{primary_contact_id}"
            )

            if (
                code == 200
                and contact.get("email")
                and contact.get("company_id")
                == lead["company_id"]
            ):
                self.pass_(
                    "Selected primary email contact",
                    (
                        f"{contact['id']} "
                        f"({contact['email']})"
                    ),
                )
                self.contact_id = contact["id"]
                return contact

        code, contacts = self.get(
            (
                "/api/contacts?company_id="
                f"{lead['company_id']}"
            )
        )

        if code == 200 and isinstance(contacts, list):
            for contact in contacts:
                if contact.get("email"):
                    self.pass_(
                        "Selected company email contact",
                        (
                            f"{contact['id']} "
                            f"({contact['email']})"
                        ),
                    )
                    self.contact_id = contact["id"]
                    return contact

        self.fail(
            "Find email contact for selected lead",
            (
                "No contact with email was available "
                "for the lead's company."
            ),
        )
        return None

    # ========================================================
    # 404 / Pydantic / service validation
    # ========================================================

    def check_not_found_cases(self) -> None:
        assert self.lead_id is not None
        assert self.contact_id is not None

        fake_action = str(uuid.uuid4())

        code, payload = self.get(
            f"/api/actions/{fake_action}"
        )
        self.assert_http(
            "Unknown Marketing Action detail -> 404",
            code,
            404,
            payload,
        )

        code, payload = self.patch(
            f"/api/actions/{fake_action}",
            {"content": "test"},
        )
        self.assert_http(
            "Unknown Marketing Action update -> 404",
            code,
            404,
            payload,
        )

        code, payload = self.patch(
            f"/api/actions/{fake_action}/cancel"
        )
        self.assert_http(
            "Unknown Marketing Action cancel -> 404",
            code,
            404,
            payload,
        )

        fake_lead = str(uuid.uuid4())

        code, payload = self.post(
            f"/api/leads/{fake_lead}/actions",
            self.valid_email_payload(),
        )
        self.assert_http(
            "Unknown lead action creation -> 404",
            code,
            404,
            payload,
        )

        fake_contact = str(uuid.uuid4())
        payload = self.valid_email_payload()
        payload["contact_id"] = fake_contact

        code, response = self.post(
            f"/api/leads/{self.lead_id}/actions",
            payload,
        )
        self.assert_http(
            "Unknown contact -> 404",
            code,
            404,
            response,
        )

    def valid_email_payload(self) -> dict[str, Any]:
        assert self.contact_id is not None

        future = (
            datetime.now(timezone.utc)
            + timedelta(days=1)
        )

        return {
            "contact_id": self.contact_id,
            "channel": "EMAIL",
            "action_type": "EMAIL",
            "subject": "Fleet visibility discussion",
            "content": (
                "Automated validation draft for "
                "LorrySystem Marketing Actions."
            ),
            "scheduled_at": (
                future.isoformat()
            ),
            "created_by": (
                "marketing-actions-validator"
            ),
        }

    def check_create_validation(self) -> None:
        assert self.lead_id is not None
        assert self.contact_id is not None

        cases: list[
            tuple[
                str,
                dict[str, Any],
                int,
            ]
        ] = []

        payload = self.valid_email_payload()
        payload["channel"] = "BANANA"
        cases.append(
            (
                "Unsupported channel rejected",
                payload,
                422,
            )
        )

        payload = self.valid_email_payload()
        payload["action_type"] = "WHATEVER"
        cases.append(
            (
                "Unsupported action_type rejected",
                payload,
                422,
            )
        )

        payload = self.valid_email_payload()
        payload["action_type"] = "COMMENT"
        cases.append(
            (
                "Invalid EMAIL + COMMENT pair rejected",
                payload,
                422,
            )
        )

        payload = self.valid_email_payload()
        payload["content"] = ""
        cases.append(
            (
                "Empty content rejected",
                payload,
                422,
            )
        )

        payload = self.valid_email_payload()
        payload["content"] = "   "
        cases.append(
            (
                "Blank content rejected",
                payload,
                422,
            )
        )

        payload = self.valid_email_payload()
        payload.pop("subject")
        cases.append(
            (
                "EMAIL without subject rejected",
                payload,
                422,
            )
        )

        payload = self.valid_email_payload()
        payload["subject"] = "   "
        cases.append(
            (
                "EMAIL with blank subject rejected",
                payload,
                422,
            )
        )

        payload = self.valid_email_payload()
        payload.pop("contact_id")
        cases.append(
            (
                "EMAIL without contact rejected",
                payload,
                422,
            )
        )

        payload = self.valid_email_payload()
        payload["scheduled_at"] = (
            datetime.now(timezone.utc)
            - timedelta(minutes=5)
        ).isoformat()
        cases.append(
            (
                "Past scheduled_at rejected",
                payload,
                422,
            )
        )

        payload = self.valid_email_payload()
        payload["scheduled_at"] = (
            datetime.now()
            + timedelta(days=1)
        ).replace(
            microsecond=0
        ).isoformat()
        cases.append(
            (
                "Timezone-naive scheduled_at rejected",
                payload,
                422,
            )
        )

        for name, body, expected in cases:
            code, response = self.post(
                f"/api/leads/{self.lead_id}/actions",
                body,
            )

            self.assert_http(
                name,
                code,
                expected,
                response,
            )

    # ========================================================
    # Positive draft workflow
    # ========================================================

    def create_email_draft(self) -> dict[str, Any] | None:
        assert self.lead_id is not None

        code, action = self.post(
            f"/api/leads/{self.lead_id}/actions",
            self.valid_email_payload(),
        )

        if not self.assert_http(
            "Valid EMAIL draft creation",
            code,
            201,
            action,
        ):
            return None

        self.created_action_ids.append(
            action["id"]
        )

        self.assert_true(
            "Created action status = DRAFT",
            action.get("status") == "DRAFT",
            str(action.get("status")),
        )

        self.assert_true(
            "Created action lead_id correct",
            action.get("lead_id")
            == self.lead_id,
            str(action.get("lead_id")),
        )

        self.assert_true(
            "Created action contact_id correct",
            action.get("contact_id")
            == self.contact_id,
            str(action.get("contact_id")),
        )

        self.assert_true(
            "Created action channel/type correct",
            (
                action.get("channel")
                == "EMAIL"
                and action.get("action_type")
                == "EMAIL"
            ),
            (
                f"channel={action.get('channel')}, "
                f"type={action.get('action_type')}"
            ),
        )

        return action

    def check_action_detail(
        self,
        expected: dict[str, Any],
    ) -> None:
        code, action = self.get(
            f"/api/actions/{expected['id']}"
        )

        if not self.assert_http(
            "Action detail retrieval",
            code,
            200,
            action,
        ):
            return

        self.assert_true(
            "Action detail ID matches",
            action.get("id")
            == expected.get("id"),
            str(action.get("id")),
        )

    def update_email_draft(
        self,
        action: dict[str, Any],
    ) -> dict[str, Any] | None:
        future = (
            datetime.now(timezone.utc)
            + timedelta(days=2)
        )

        payload = {
            "subject": (
                "Updated fleet visibility discussion"
            ),
            "content": (
                "Updated automated validation "
                "draft content."
            ),
            "scheduled_at": future.isoformat(),
        }

        code, updated = self.patch(
            f"/api/actions/{action['id']}",
            payload,
        )

        if not self.assert_http(
            "DRAFT update succeeds",
            code,
            200,
            updated,
        ):
            return None

        self.assert_true(
            "Action ID preserved on update",
            updated.get("id")
            == action.get("id"),
            (
                f"before={action.get('id')}, "
                f"after={updated.get('id')}"
            ),
        )

        self.assert_true(
            "created_at preserved on update",
            updated.get("created_at")
            == action.get("created_at"),
            (
                f"before={action.get('created_at')}, "
                f"after={updated.get('created_at')}"
            ),
        )

        self.assert_true(
            "updated_at advances on update",
            updated.get("updated_at")
            >= action.get("updated_at"),
            (
                f"before={action.get('updated_at')}, "
                f"after={updated.get('updated_at')}"
            ),
        )

        self.assert_true(
            "Updated subject persisted",
            updated.get("subject")
            == payload["subject"],
            str(updated.get("subject")),
        )

        self.assert_true(
            "Updated content persisted",
            updated.get("content")
            == payload["content"],
            str(updated.get("content")),
        )

        return updated

    def check_update_validation(
        self,
        action: dict[str, Any],
    ) -> None:
        code, response = self.patch(
            f"/api/actions/{action['id']}",
            {},
        )

        self.assert_http(
            "Empty update rejected",
            code,
            422,
            response,
        )

        code, response = self.patch(
            f"/api/actions/{action['id']}",
            {"content": None},
        )

        self.assert_http(
            "Null content update rejected",
            code,
            422,
            response,
        )

        code, response = self.patch(
            f"/api/actions/{action['id']}",
            {"subject": None},
        )

        self.assert_http(
            "EMAIL subject cannot be cleared",
            code,
            422,
            response,
        )

        fake_contact = str(uuid.uuid4())

        code, response = self.patch(
            f"/api/actions/{action['id']}",
            {"contact_id": fake_contact},
        )

        self.assert_http(
            "Unknown contact on update -> 404",
            code,
            404,
            response,
        )

    def create_linkedin_post(
        self,
    ) -> dict[str, Any] | None:
        assert self.lead_id is not None

        payload = {
            "channel": "LINKEDIN",
            "action_type": "POST",
            "content": (
                "Automated validation LinkedIn post."
            ),
            "created_by": (
                "marketing-actions-validator"
            ),
        }

        code, action = self.post(
            f"/api/leads/{self.lead_id}/actions",
            payload,
        )

        if not self.assert_http(
            "LINKEDIN POST without contact succeeds",
            code,
            201,
            action,
        ):
            return None

        self.created_action_ids.append(
            action["id"]
        )

        self.assert_true(
            "LinkedIn POST contact_id is null",
            action.get("contact_id") is None,
            str(action.get("contact_id")),
        )

        self.assert_true(
            "LinkedIn POST status = DRAFT",
            action.get("status") == "DRAFT",
            str(action.get("status")),
        )

        return action

    def check_list_order(
        self,
        first_action: dict[str, Any],
        second_action: dict[str, Any],
    ) -> None:
        assert self.lead_id is not None

        code, actions = self.get(
            f"/api/leads/{self.lead_id}/actions"
        )

        if not self.assert_http(
            "Lead action list retrieval",
            code,
            200,
            actions,
        ):
            return

        if not isinstance(actions, list):
            self.fail(
                "Lead action list is a list",
                repr(actions),
            )
            return

        self.pass_(
            "Lead action list is a list",
            f"count={len(actions)}",
        )

        ids = [
            item.get("id")
            for item in actions
        ]

        self.assert_true(
            "Both validation actions are listed",
            (
                first_action["id"] in ids
                and second_action["id"] in ids
            ),
            str(ids),
        )

        if (
            first_action["id"] in ids
            and second_action["id"] in ids
        ):
            self.assert_true(
                "Lead action list is newest first",
                (
                    ids.index(second_action["id"])
                    < ids.index(first_action["id"])
                ),
                (
                    f"first_index="
                    f"{ids.index(first_action['id'])}, "
                    f"second_index="
                    f"{ids.index(second_action['id'])}"
                ),
            )

    # ========================================================
    # Cancellation / invalid transitions
    # ========================================================

    def cancel_and_validate(
        self,
        action: dict[str, Any],
        *,
        test_invalid_after: bool,
    ) -> dict[str, Any] | None:
        code, cancelled = self.patch(
            f"/api/actions/{action['id']}/cancel"
        )

        if not self.assert_http(
            "DRAFT cancellation succeeds",
            code,
            200,
            cancelled,
        ):
            return None

        self.assert_true(
            "Cancelled status persisted",
            cancelled.get("status")
            == "CANCELLED",
            str(cancelled.get("status")),
        )

        self.assert_true(
            "Action ID preserved on cancellation",
            cancelled.get("id")
            == action.get("id"),
            str(cancelled.get("id")),
        )

        if test_invalid_after:
            code, response = self.patch(
                f"/api/actions/{action['id']}",
                {
                    "content": (
                        "This edit must fail."
                    )
                },
            )

            self.assert_http(
                "Editing CANCELLED action rejected",
                code,
                409,
                response,
            )

            code, response = self.patch(
                f"/api/actions/{action['id']}/cancel"
            )

            self.assert_http(
                "Cancelling CANCELLED action rejected",
                code,
                409,
                response,
            )

        return cancelled

    # ========================================================
    # Safety verification
    # ========================================================

    def check_lead_unchanged(self) -> None:
        assert self.lead_id is not None

        code, lead = self.get(
            f"/api/leads/{self.lead_id}"
        )

        if not self.assert_http(
            "Lead readable after Marketing Actions",
            code,
            200,
            lead,
        ):
            return

        self.assert_true(
            "Marketing Actions do not mutate lead status",
            lead.get("status")
            == self.initial_lead_status,
            (
                f"initial="
                f"{self.initial_lead_status}, "
                f"current={lead.get('status')}"
            ),
        )

        self.assert_true(
            "Marketing Actions do not mutate lead current_score",
            lead.get("current_score")
            == self.initial_lead_score,
            (
                f"initial="
                f"{self.initial_lead_score}, "
                f"current="
                f"{lead.get('current_score')}"
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
                        "ProductMatch rows unchanged",
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
    # DB action rows / events
    # ========================================================

    def check_action_database_rows(
        self,
        action_ids: list[str],
    ) -> None:
        try:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            id::text,
                            lead_id::text,
                            status,
                            channel,
                            action_type
                        FROM marketing_actions
                        WHERE id = ANY(%s::uuid[])
                        ORDER BY created_at
                        """,
                        (action_ids,),
                    )

                    rows = cur.fetchall()

                    self.assert_true(
                        "Validation actions persisted in PostgreSQL",
                        len(rows) == len(action_ids),
                        f"rows={rows}",
                    )

                    self.assert_true(
                        "Validation actions finish CANCELLED",
                        (
                            len(rows) == len(action_ids)
                            and all(
                                row[2] == "CANCELLED"
                                for row in rows
                            )
                        ),
                        str(rows),
                    )

        except Exception as exc:
            self.fail(
                "Marketing Action DB row checks",
                repr(exc),
            )

    def check_events(
        self,
        email_action_id: str,
        linkedin_action_id: str,
    ) -> None:
        assert self.lead_id is not None

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
                        ORDER BY created_at
                        """,
                        (
                            [
                                email_action_id,
                                linkedin_action_id,
                            ],
                        ),
                    )

                    rows = cur.fetchall()

                    by_action: dict[
                        str,
                        list[tuple[str, dict]]
                    ] = {}

                    for (
                        entity_id,
                        event_type,
                        metadata,
                    ) in rows:
                        by_action.setdefault(
                            entity_id,
                            [],
                        ).append(
                            (
                                event_type,
                                metadata,
                            )
                        )

                    email_events = by_action.get(
                        email_action_id,
                        [],
                    )

                    linkedin_events = by_action.get(
                        linkedin_action_id,
                        [],
                    )

                    email_types = [
                        event_type
                        for event_type, _
                        in email_events
                    ]

                    self.assert_true(
                        "EMAIL action created event exists",
                        "marketing_action_created"
                        in email_types,
                        str(email_types),
                    )

                    self.assert_true(
                        "EMAIL action updated event exists",
                        "marketing_action_updated"
                        in email_types,
                        str(email_types),
                    )

                    self.assert_true(
                        "EMAIL action cancelled event exists",
                        "marketing_action_cancelled"
                        in email_types,
                        str(email_types),
                    )

                    linkedin_types = [
                        event_type
                        for event_type, _
                        in linkedin_events
                    ]

                    self.assert_true(
                        "LINKEDIN action created event exists",
                        "marketing_action_created"
                        in linkedin_types,
                        str(linkedin_types),
                    )

                    self.assert_true(
                        "LINKEDIN action cancelled event exists",
                        "marketing_action_cancelled"
                        in linkedin_types,
                        str(linkedin_types),
                    )

                    for (
                        entity_id,
                        event_type,
                        metadata,
                    ) in rows:
                        self.assert_true(
                            (
                                f"{event_type} event references "
                                f"correct action"
                            ),
                            metadata.get("action_id")
                            == entity_id,
                            str(metadata),
                        )

                        self.assert_true(
                            (
                                f"{event_type} event references "
                                f"correct lead"
                            ),
                            metadata.get("lead_id")
                            == self.lead_id,
                            str(metadata),
                        )

        except Exception as exc:
            self.fail(
                "Marketing Action event checks",
                repr(exc),
            )

    # ========================================================
    # Optional environment-dependent cases
    # ========================================================

    def check_no_score_lead(
        self,
        lead_id: str | None,
    ) -> None:
        if not lead_id:
            self.skip(
                "Lead without current score -> 409",
                (
                    "No --no-score-lead-id "
                    "provided."
                ),
            )
            return

        code, lead = self.get(
            f"/api/leads/{lead_id}"
        )

        if code != 200:
            self.fail(
                "No-score fixture lead exists",
                f"HTTP {code}: {lead}",
            )
            return

        if lead.get("current_score") is not None:
            self.fail(
                "No-score fixture has current_score = NULL",
                (
                    f"current_score="
                    f"{lead.get('current_score')}"
                ),
            )
            return

        payload = {
            "channel": "LINKEDIN",
            "action_type": "POST",
            "content": "No-score validation.",
        }

        code, response = self.post(
            f"/api/leads/{lead_id}/actions",
            payload,
        )

        self.assert_http(
            "Lead without current score -> 409",
            code,
            409,
            response,
        )

    def check_no_match_lead(
        self,
        lead_id: str | None,
    ) -> None:
        if not lead_id:
            self.skip(
                "Lead without ProductMatch -> 409",
                (
                    "No --no-match-lead-id "
                    "provided."
                ),
            )
            return

        code, lead = self.get(
            f"/api/leads/{lead_id}"
        )

        if code != 200:
            self.fail(
                "No-match fixture lead exists",
                f"HTTP {code}: {lead}",
            )
            return

        if lead.get("current_score") is None:
            self.fail(
                "No-match fixture has current score",
                "current_score is NULL",
            )
            return

        m_code, matches = self.get(
            f"/api/leads/{lead_id}/product-matches"
        )

        if (
            m_code != 200
            or not isinstance(matches, list)
        ):
            self.fail(
                "No-match fixture ProductMatch list",
                f"HTTP {m_code}: {matches}",
            )
            return

        if matches:
            self.fail(
                "No-match fixture has zero ProductMatches",
                f"count={len(matches)}",
            )
            return

        payload = {
            "channel": "LINKEDIN",
            "action_type": "POST",
            "content": "No ProductMatch validation.",
        }

        code, response = self.post(
            f"/api/leads/{lead_id}/actions",
            payload,
        )

        self.assert_http(
            "Lead without ProductMatch -> 409",
            code,
            409,
            response,
        )

    def check_terminal_lead(
        self,
        lead_id: str | None,
    ) -> None:
        if not lead_id:
            self.skip(
                "Terminal lead rejected",
                (
                    "No --terminal-lead-id "
                    "provided."
                ),
            )
            return

        code, lead = self.get(
            f"/api/leads/{lead_id}"
        )

        if code != 200:
            self.fail(
                "Terminal fixture lead exists",
                f"HTTP {code}: {lead}",
            )
            return

        if lead.get("status") not in TERMINAL_LEAD_STATUSES:
            self.fail(
                "Terminal fixture is terminal",
                f"status={lead.get('status')}",
            )
            return

        payload = {
            "channel": "LINKEDIN",
            "action_type": "POST",
            "content": "Terminal lead validation.",
        }

        code, response = self.post(
            f"/api/leads/{lead_id}/actions",
            payload,
        )

        self.assert_http(
            "Terminal lead rejected",
            code,
            409,
            response,
        )

    def check_foreign_contact(
        self,
        contact_id: str | None,
    ) -> None:
        if not contact_id:
            self.skip(
                "Contact from different company -> 409",
                (
                    "No --foreign-contact-id "
                    "provided."
                ),
            )
            return

        assert self.lead_id is not None

        code, contact = self.get(
            f"/api/contacts/{contact_id}"
        )

        if code != 200:
            self.fail(
                "Foreign-contact fixture exists",
                f"HTTP {code}: {contact}",
            )
            return

        if (
            contact.get("company_id")
            == self.lead_company_id
        ):
            self.fail(
                "Foreign-contact fixture belongs to different company",
                (
                    f"company_id="
                    f"{contact.get('company_id')}"
                ),
            )
            return

        payload = {
            "contact_id": contact_id,
            "channel": "LINKEDIN",
            "action_type": "DIRECT_MESSAGE",
            "content": "Foreign contact validation.",
        }

        code, response = self.post(
            f"/api/leads/{self.lead_id}/actions",
            payload,
        )

        self.assert_http(
            "Contact from different company -> 409",
            code,
            409,
            response,
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
            "LorrySystem Marketing Actions API "
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

        if failures:
            print("\nRESULT: FAILED")
            return 1

        print("\nRESULT: PASSED")
        return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate LorrySystem "
            "Marketing Actions API MVP1."
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
            "Eligible non-terminal lead UUID "
            "with current_score and ProductMatch."
        ),
    )

    parser.add_argument(
        "--no-score-lead-id",
        default=None,
    )

    parser.add_argument(
        "--no-match-lead-id",
        default=None,
    )

    parser.add_argument(
        "--terminal-lead-id",
        default=None,
    )

    parser.add_argument(
        "--foreign-contact-id",
        default=None,
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    validator = Validator(
        args.base_url
    )

    print("=" * 72)
    print(
        "LorrySystem Marketing Actions API "
        "MVP1 Validation"
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

    if not validator.validate_selected_lead(
        lead
    ):
        return validator.summary()

    contact = validator.choose_email_contact(
        lead
    )

    if not contact:
        return validator.summary()

    validator.snapshot_product_matches()

    print(
        f"\nUsing lead: {validator.lead_id} "
        f"(status={validator.initial_lead_status}, "
        f"current_score={validator.initial_lead_score})"
    )

    print(
        f"Using contact: {validator.contact_id} "
        f"({contact.get('email')})\n"
    )

    validator.check_not_found_cases()
    validator.check_create_validation()

    email_action = validator.create_email_draft()

    if not email_action:
        return validator.summary()

    validator.check_action_detail(
        email_action
    )

    validator.check_update_validation(
        email_action
    )

    updated_email = validator.update_email_draft(
        email_action
    )

    if not updated_email:
        return validator.summary()

    linkedin_action = validator.create_linkedin_post()

    if not linkedin_action:
        return validator.summary()

    validator.check_list_order(
        updated_email,
        linkedin_action,
    )

    cancelled_email = validator.cancel_and_validate(
        updated_email,
        test_invalid_after=True,
    )

    if not cancelled_email:
        return validator.summary()

    cancelled_linkedin = validator.cancel_and_validate(
        linkedin_action,
        test_invalid_after=False,
    )

    if not cancelled_linkedin:
        return validator.summary()

    validator.check_lead_unchanged()
    validator.check_product_matches_unchanged()

    validator.check_action_database_rows(
        [
            cancelled_email["id"],
            cancelled_linkedin["id"],
        ]
    )

    validator.check_events(
        cancelled_email["id"],
        cancelled_linkedin["id"],
    )

    validator.check_no_score_lead(
        args.no_score_lead_id
    )

    validator.check_no_match_lead(
        args.no_match_lead_id
    )

    validator.check_terminal_lead(
        args.terminal_lead_id
    )

    validator.check_foreign_contact(
        args.foreign_contact_id
    )

    return validator.summary()


if __name__ == "__main__":
    sys.exit(main())
