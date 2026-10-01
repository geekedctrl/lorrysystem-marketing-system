#!/usr/bin/env python3
"""
LorrySystem Marketing API — Full Stack Regression Validator

Purpose
-------
Validate the complete MVP1 API chain before n8n integration:

    Companies
    Contacts
    Leads
    Research
    Scoring
    Product Matching
    Marketing Actions
    Approval

Default mode is a non-destructive regression audit.

Optional --deep mode discovers and runs existing module validators from
/api/scripts (or the configured scripts directory). Deep validators may
create/update test records according to their own behavior.

Typical use inside the Marketing API container:

    python /tmp/validate_full_stack.py \
        --lead-id dcb7d435-cf8c-4202-868f-3666dc53f8ac

Maximum-confidence run:

    python /tmp/validate_full_stack.py \
        --lead-id dcb7d435-cf8c-4202-868f-3666dc53f8ac \
        --deep
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import psycopg
except ImportError:
    psycopg = None


EXPECTED_ALEMBIC_HEAD = "006"

CONTROLLED_ACTION_CHANNELS = {
    "EMAIL",
    "LINKEDIN",
    "FACEBOOK",
    "INSTAGRAM",
    "X",
}

CONTROLLED_ACTION_TYPES = {
    "EMAIL",
    "FOLLOW_UP",
    "POST",
    "COMMENT",
    "DIRECT_MESSAGE",
}

CONTROLLED_ACTION_STATUSES = {
    "DRAFT",
    "PENDING_APPROVAL",
    "APPROVED",
    "QUEUED",
    "SENT",
    "PUBLISHED",
    "REJECTED",
    "FAILED",
    "CANCELLED",
}

CONTROLLED_APPROVAL_STATUSES = {
    "PENDING",
    "APPROVED",
    "REJECTED",
    "CHANGES_REQUESTED",
}

VALID_CHANNEL_ACTION_PAIRS = {
    ("EMAIL", "EMAIL"),
    ("EMAIL", "FOLLOW_UP"),
    ("LINKEDIN", "POST"),
    ("LINKEDIN", "COMMENT"),
    ("LINKEDIN", "DIRECT_MESSAGE"),
    ("FACEBOOK", "POST"),
    ("INSTAGRAM", "POST"),
    ("X", "POST"),
}

CORE_ROUTES: dict[str, set[str] | None] = {
    # Foundation
    "/api/companies": None,
    "/api/contacts/{contact_id}": {"get"},
    "/api/leads": {"get"},
    "/api/leads/{lead_id}": {"get"},

    # Research
    "/api/leads/{lead_id}/research": {"get", "post"},
    "/api/research/{research_id}": {"get"},
    "/api/research/{research_id}/start": {"patch"},
    "/api/research/{research_id}/sources": {"post"},
    "/api/research/{research_id}/complete": {"patch"},
    "/api/research/{research_id}/partial": {"patch"},
    "/api/research/{research_id}/fail": {"patch"},

    # Scoring
    "/api/leads/{lead_id}/scores": {"get", "post"},
    "/api/leads/{lead_id}/scores/current": {"get"},
    "/api/scoring/{score_id}": {"get"},

    # Product Matching
    "/api/products": {"get"},
    "/api/products/{product_id}": {"get"},
    "/api/leads/{lead_id}/product-matches": {"get", "post"},
    "/api/product-matches/{match_id}": {"get"},

    # Marketing Actions
    "/api/leads/{lead_id}/actions": {"get", "post"},
    "/api/actions/{action_id}": {"get", "patch"},
    "/api/actions/{action_id}/cancel": {"patch"},

    # Approval
    "/api/actions/{action_id}/submit": {"post"},
    "/api/approvals": {"get"},
    "/api/approvals/{approval_id}": {"get"},
    "/api/actions/{action_id}/approvals": {"get"},
    "/api/approvals/{approval_id}/approve": {"patch"},
    "/api/approvals/{approval_id}/reject": {"patch"},
    "/api/approvals/{approval_id}/request-changes": {"patch"},
}

REQUIRED_TABLES = {
    "companies",
    "contacts",
    "leads",
    "lead_research",
    "research_sources",
    "lead_scores",
    "products",
    "product_matches",
    "marketing_actions",
    "approval_requests",
    "events",
}

REQUIRED_MARKETING_ACTION_CONSTRAINTS = {
    "ck_marketing_actions_channel",
    "ck_marketing_actions_action_type",
    "ck_marketing_actions_status",
    "ck_marketing_actions_channel_action_pair",
}

REQUIRED_APPROVAL_CONSTRAINTS = {
    "ck_approval_requests_status",
}

REQUIRED_APPROVAL_INDEXES = {
    "idx_approval_requests_status",
    "idx_approval_requests_action",
    "idx_approval_requests_requested_at",
    "idx_approval_requests_one_pending",
}


@dataclass
class Result:
    stage: str
    name: str
    status: str
    detail: str = ""


class FullStackValidator:
    def __init__(
        self,
        base_url: str,
        lead_id: str | None,
        scripts_dir: str,
        deep: bool,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.lead_id = lead_id
        self.scripts_dir = Path(scripts_dir)
        self.deep = deep

        self.results: list[Result] = []
        self.openapi: dict[str, Any] | None = None

        self.lead: dict[str, Any] | None = None

    # ========================================================
    # Result helpers
    # ========================================================

    def _record(
        self,
        stage: str,
        name: str,
        status: str,
        detail: str = "",
    ) -> None:
        self.results.append(
            Result(
                stage=stage,
                name=name,
                status=status,
                detail=detail,
            )
        )

        print(
            f"[{status}] [{stage}] {name}"
            + (f" — {detail}" if detail else "")
        )

    def pass_(
        self,
        stage: str,
        name: str,
        detail: str = "",
    ) -> None:
        self._record(
            stage,
            name,
            "PASS",
            detail,
        )

    def fail(
        self,
        stage: str,
        name: str,
        detail: str = "",
    ) -> None:
        self._record(
            stage,
            name,
            "FAIL",
            detail,
        )

    def skip(
        self,
        stage: str,
        name: str,
        detail: str = "",
    ) -> None:
        self._record(
            stage,
            name,
            "SKIP",
            detail,
        )

    def assert_true(
        self,
        stage: str,
        name: str,
        condition: bool,
        detail: str = "",
    ) -> bool:
        if condition:
            self.pass_(
                stage,
                name,
                detail,
            )
            return True

        self.fail(
            stage,
            name,
            detail,
        )
        return False

    def assert_http(
        self,
        stage: str,
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
            stage,
            name,
            actual in expected_values,
            (
                f"HTTP {actual}, "
                f"expected {expected_values}; "
                f"response={payload}"
            ),
        )

    # ========================================================
    # HTTP
    # ========================================================

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        data = None
        headers: dict[str, str] = {}

        if body is not None:
            data = json.dumps(
                body
            ).encode("utf-8")
            headers[
                "Content-Type"
            ] = "application/json"

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
                raw = (
                    response.read()
                    .decode("utf-8")
                )

                payload = (
                    json.loads(raw)
                    if raw
                    else None
                )

                return (
                    response.status,
                    payload,
                )

        except urllib.error.HTTPError as exc:
            raw = (
                exc.read()
                .decode("utf-8")
            )

            try:
                payload = (
                    json.loads(raw)
                    if raw
                    else None
                )
            except json.JSONDecodeError:
                payload = raw

            return (
                exc.code,
                payload,
            )

        except Exception as exc:
            return (
                0,
                {
                    "error": repr(exc)
                },
            )

    def get(
        self,
        path: str,
    ) -> tuple[int, Any]:
        return self.request(
            "GET",
            path,
        )

    # ========================================================
    # Database
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
            dbname=os.environ[
                "POSTGRES_DB"
            ],
            user=os.environ[
                "POSTGRES_USER"
            ],
            password=os.environ[
                "POSTGRES_PASSWORD"
            ],
            host=os.environ[
                "POSTGRES_HOST"
            ],
            port=os.environ[
                "POSTGRES_PORT"
            ],
        )

    # ========================================================
    # Preflight
    # ========================================================

    def check_health_and_openapi(
        self,
    ) -> None:
        stage = "PRECHECK"

        code, payload = self.get(
            "/openapi.json"
        )

        if not self.assert_http(
            stage,
            "OpenAPI reachable",
            code,
            200,
            payload,
        ):
            return

        if not isinstance(
            payload,
            dict,
        ):
            self.fail(
                stage,
                "OpenAPI payload is object",
                repr(payload),
            )
            return

        self.openapi = payload

        self.pass_(
            stage,
            "OpenAPI document loaded",
            (
                f"paths="
                f"{len(payload.get('paths', {}))}"
            ),
        )

        root_code, root_payload = (
            self.get("/")
        )

        self.assert_http(
            stage,
            "API root reachable",
            root_code,
            200,
            root_payload,
        )

    def check_routes(self) -> None:
        stage = "ROUTES"

        if self.openapi is None:
            self.fail(
                stage,
                "Route audit",
                (
                    "OpenAPI unavailable; "
                    "cannot inspect routes."
                ),
            )
            return

        paths = self.openapi.get(
            "paths",
            {},
        )

        for (
            path,
            expected_methods,
        ) in CORE_ROUTES.items():
            if path not in paths:
                self.fail(
                    stage,
                    f"Route exists: {path}",
                    "missing",
                )
                continue

            if expected_methods is None:
                self.pass_(
                    stage,
                    f"Route exists: {path}",
                )
                continue

            actual_methods = {
                method.lower()
                for method
                in paths[path].keys()
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
                stage,
                f"Methods correct: {path}",
                expected_methods.issubset(
                    actual_methods
                ),
                (
                    f"expected="
                    f"{sorted(expected_methods)}, "
                    f"actual="
                    f"{sorted(actual_methods)}"
                ),
            )

    # ========================================================
    # Schema / migration
    # ========================================================

    def check_database_structure(
        self,
    ) -> None:
        stage = "DATABASE"

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
                    version = (
                        row[0]
                        if row
                        else None
                    )

                    self.assert_true(
                        stage,
                        "Alembic head",
                        (
                            version
                            == EXPECTED_ALEMBIC_HEAD
                        ),
                        (
                            f"expected="
                            f"{EXPECTED_ALEMBIC_HEAD}, "
                            f"actual={version}"
                        ),
                    )

                    cur.execute(
                        """
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                        """
                    )

                    tables = {
                        row[0]
                        for row
                        in cur.fetchall()
                    }

                    for table in sorted(
                        REQUIRED_TABLES
                    ):
                        self.assert_true(
                            stage,
                            f"Table exists: {table}",
                            table in tables,
                            (
                                ""
                                if table in tables
                                else f"tables="
                                f"{sorted(tables)}"
                            ),
                        )

                    self._check_constraints(
                        cur
                    )

                    self._check_indexes(
                        cur
                    )

        except Exception as exc:
            self.fail(
                stage,
                "Database structure audit",
                repr(exc),
            )

    def _check_constraints(
        self,
        cur,
    ) -> None:
        stage = "DATABASE"

        cur.execute(
            """
            SELECT
                t.relname,
                c.conname
            FROM pg_constraint c
            JOIN pg_class t
              ON t.oid = c.conrelid
            JOIN pg_namespace n
              ON n.oid = t.relnamespace
            WHERE n.nspname = 'public'
            """
        )

        constraint_map: dict[
            str,
            set[str],
        ] = {}

        for table, name in cur.fetchall():
            constraint_map.setdefault(
                table,
                set(),
            ).add(name)

        marketing_constraints = (
            constraint_map.get(
                "marketing_actions",
                set(),
            )
        )

        for name in sorted(
            REQUIRED_MARKETING_ACTION_CONSTRAINTS
        ):
            self.assert_true(
                stage,
                (
                    "Marketing Action "
                    f"constraint: {name}"
                ),
                (
                    name
                    in marketing_constraints
                ),
            )

        approval_constraints = (
            constraint_map.get(
                "approval_requests",
                set(),
            )
        )

        for name in sorted(
            REQUIRED_APPROVAL_CONSTRAINTS
        ):
            self.assert_true(
                stage,
                (
                    "Approval constraint: "
                    f"{name}"
                ),
                (
                    name
                    in approval_constraints
                ),
            )

    def _check_indexes(
        self,
        cur,
    ) -> None:
        stage = "DATABASE"

        cur.execute(
            """
            SELECT
                indexname,
                indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename = 'approval_requests'
            """
        )

        indexes = {
            row[0]: row[1]
            for row
            in cur.fetchall()
        }

        for name in sorted(
            REQUIRED_APPROVAL_INDEXES
        ):
            self.assert_true(
                stage,
                (
                    "Approval index: "
                    f"{name}"
                ),
                name in indexes,
                indexes.get(name, ""),
            )

        pending_index = indexes.get(
            "idx_approval_requests_one_pending",
            "",
        )

        self.assert_true(
            stage,
            (
                "One-PENDING index "
                "is unique and partial"
            ),
            (
                "UNIQUE INDEX"
                in pending_index.upper()
                and "WHERE"
                in pending_index.upper()
                and "PENDING"
                in pending_index.upper()
            ),
            pending_index,
        )

    # ========================================================
    # Foundation stage
    # ========================================================

    def check_foundation_apis(
        self,
    ) -> None:
        stage = "FOUNDATION"

        code, companies = self.get(
            "/api/companies"
        )

        self.assert_http(
            stage,
            "Companies list endpoint",
            code,
            200,
            companies,
        )

        code, leads = self.get(
            "/api/leads"
        )

        self.assert_http(
            stage,
            "Leads list endpoint",
            code,
            200,
            leads,
        )

        if (
            code == 200
            and isinstance(leads, list)
        ):
            self.pass_(
                stage,
                "Leads response is list",
                f"count={len(leads)}",
            )

        if not self.lead_id:
            self.skip(
                stage,
                "Lead-specific foundation checks",
                (
                    "No --lead-id supplied."
                ),
            )
            return

        code, lead = self.get(
            f"/api/leads/{self.lead_id}"
        )

        if not self.assert_http(
            stage,
            "Selected lead detail",
            code,
            200,
            lead,
        ):
            return

        if not isinstance(
            lead,
            dict,
        ):
            self.fail(
                stage,
                "Lead detail is object",
                repr(lead),
            )
            return

        self.lead = lead

        company_id = lead.get(
            "company_id"
        )

        contact_id = lead.get(
            "primary_contact_id"
        )

        self.assert_true(
            stage,
            "Lead has company_id",
            bool(company_id),
            str(company_id),
        )

        if contact_id:
            c_code, contact = self.get(
                f"/api/contacts/{contact_id}"
            )

            if self.assert_http(
                stage,
                "Primary contact detail",
                c_code,
                200,
                contact,
            ):
                self.assert_true(
                    stage,
                    (
                        "Primary contact belongs "
                        "to lead company"
                    ),
                    (
                        isinstance(
                            contact,
                            dict,
                        )
                        and contact.get(
                            "company_id"
                        )
                        == company_id
                    ),
                    (
                        f"lead_company="
                        f"{company_id}, "
                        f"contact_company="
                        f"{contact.get('company_id') if isinstance(contact, dict) else None}"
                    ),
                )
        else:
            self.skip(
                stage,
                "Primary contact check",
                (
                    "Selected lead has no "
                    "primary_contact_id."
                ),
            )

    # ========================================================
    # Research stage
    # ========================================================

    def check_research_stage(
        self,
    ) -> None:
        stage = "RESEARCH"

        if not self.lead_id:
            self.skip(
                stage,
                "Research stage",
                "No --lead-id supplied.",
            )
            return

        code, payload = self.get(
            f"/api/leads/{self.lead_id}/research"
        )

        self.assert_http(
            stage,
            "Lead research endpoint",
            code,
            200,
            payload,
        )

        try:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            research_status,
                            COUNT(*)
                        FROM lead_research
                        WHERE lead_id = %s::uuid
                        GROUP BY research_status
                        ORDER BY research_status
                        """,
                        (self.lead_id,),
                    )

                    rows = cur.fetchall()

                    self.assert_true(
                        stage,
                        "Research rows exist",
                        len(rows) >= 1,
                        str(rows),
                    )

                    usable = sum(
                        count
                        for status, count
                        in rows
                        if status
                        in {
                            "COMPLETED",
                            "PARTIAL",
                        }
                    )

                    self.assert_true(
                        stage,
                        (
                            "Usable Research exists "
                            "(COMPLETED/PARTIAL)"
                        ),
                        usable >= 1,
                        str(rows),
                    )

        except Exception as exc:
            self.fail(
                stage,
                "Research DB audit",
                repr(exc),
            )

    # ========================================================
    # Scoring stage
    # ========================================================

    def check_scoring_stage(
        self,
    ) -> None:
        stage = "SCORING"

        if not self.lead_id:
            self.skip(
                stage,
                "Scoring stage",
                "No --lead-id supplied.",
            )
            return

        code, current = self.get(
            (
                f"/api/leads/"
                f"{self.lead_id}/scores/current"
            )
        )

        self.assert_http(
            stage,
            "Current score endpoint",
            code,
            200,
            current,
        )

        code, history = self.get(
            f"/api/leads/{self.lead_id}/scores"
        )

        self.assert_http(
            stage,
            "Score history endpoint",
            code,
            200,
            history,
        )

        try:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            COUNT(*)
                        FROM lead_scores
                        WHERE lead_id = %s::uuid
                          AND is_current = TRUE
                        """,
                        (self.lead_id,),
                    )

                    current_count = (
                        cur.fetchone()[0]
                    )

                    self.assert_true(
                        stage,
                        (
                            "Exactly one current "
                            "score for selected lead"
                        ),
                        current_count == 1,
                        (
                            f"count={current_count}"
                        ),
                    )

                    cur.execute(
                        """
                        SELECT
                            l.current_score,
                            s.total_score
                        FROM leads l
                        LEFT JOIN lead_scores s
                          ON s.lead_id = l.id
                         AND s.is_current = TRUE
                        WHERE l.id = %s::uuid
                        """,
                        (self.lead_id,),
                    )

                    row = cur.fetchone()

                    if row is None:
                        self.fail(
                            stage,
                            (
                                "Lead score DB "
                                "consistency row"
                            ),
                            "lead not found",
                        )
                    else:
                        lead_score = row[0]
                        score_total = row[1]

                        self.assert_true(
                            stage,
                            (
                                "leads.current_score "
                                "matches current "
                                "lead_scores.total_score"
                            ),
                            (
                                lead_score
                                == score_total
                            ),
                            (
                                f"lead.current_score="
                                f"{lead_score}, "
                                f"current score total="
                                f"{score_total}"
                            ),
                        )

                    cur.execute(
                        """
                        SELECT
                            lead_id::text,
                            COUNT(*)
                        FROM lead_scores
                        WHERE is_current = TRUE
                        GROUP BY lead_id
                        HAVING COUNT(*) > 1
                        """
                    )

                    duplicates = cur.fetchall()

                    self.assert_true(
                        stage,
                        (
                            "No lead has multiple "
                            "current scores"
                        ),
                        len(duplicates) == 0,
                        str(duplicates),
                    )

        except Exception as exc:
            self.fail(
                stage,
                "Scoring DB audit",
                repr(exc),
            )

    # ========================================================
    # Product Matching
    # ========================================================

    def check_product_matching_stage(
        self,
    ) -> None:
        stage = "PRODUCT_MATCHING"

        code, products = self.get(
            "/api/products"
        )

        if self.assert_http(
            stage,
            "Products endpoint",
            code,
            200,
            products,
        ):
            self.assert_true(
                stage,
                "Product catalog is non-empty",
                (
                    isinstance(
                        products,
                        list,
                    )
                    and len(products) >= 1
                ),
                (
                    f"count="
                    f"{len(products) if isinstance(products, list) else 'n/a'}"
                ),
            )

        if not self.lead_id:
            self.skip(
                stage,
                "Lead ProductMatch stage",
                "No --lead-id supplied.",
            )
            return

        code, matches = self.get(
            (
                f"/api/leads/"
                f"{self.lead_id}/product-matches"
            )
        )

        if self.assert_http(
            stage,
            "Lead ProductMatches endpoint",
            code,
            200,
            matches,
        ):
            self.assert_true(
                stage,
                (
                    "Selected lead has "
                    "at least one ProductMatch"
                ),
                (
                    isinstance(
                        matches,
                        list,
                    )
                    and len(matches) >= 1
                ),
                (
                    f"count="
                    f"{len(matches) if isinstance(matches, list) else 'n/a'}"
                ),
            )

        try:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            lead_id::text,
                            product_id::text,
                            COUNT(*)
                        FROM product_matches
                        GROUP BY
                            lead_id,
                            product_id
                        HAVING COUNT(*) > 1
                        """
                    )

                    duplicate_pairs = (
                        cur.fetchall()
                    )

                    self.assert_true(
                        stage,
                        (
                            "No duplicate "
                            "(lead_id, product_id) "
                            "ProductMatch pairs"
                        ),
                        (
                            len(
                                duplicate_pairs
                            )
                            == 0
                        ),
                        str(
                            duplicate_pairs
                        ),
                    )

                    cur.execute(
                        """
                        SELECT
                            id::text,
                            fit_score
                        FROM product_matches
                        WHERE fit_score < 0
                           OR fit_score > 100
                        """
                    )

                    bad_scores = cur.fetchall()

                    self.assert_true(
                        stage,
                        (
                            "All ProductMatch "
                            "fit_score values "
                            "are 0..100"
                        ),
                        len(bad_scores) == 0,
                        str(bad_scores),
                    )

        except Exception as exc:
            self.fail(
                stage,
                "Product Matching DB audit",
                repr(exc),
            )

    # ========================================================
    # Marketing Actions
    # ========================================================

    def check_marketing_actions_stage(
        self,
    ) -> None:
        stage = "MARKETING_ACTIONS"

        if self.lead_id:
            code, actions = self.get(
                f"/api/leads/{self.lead_id}/actions"
            )

            self.assert_http(
                stage,
                "Lead Marketing Actions endpoint",
                code,
                200,
                actions,
            )

        try:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            id::text,
                            channel,
                            action_type,
                            status,
                            content,
                            subject,
                            contact_id::text
                        FROM marketing_actions
                        """
                    )

                    rows = cur.fetchall()

                    self.pass_(
                        stage,
                        (
                            "Marketing Action rows "
                            "read successfully"
                        ),
                        f"count={len(rows)}",
                    )

                    bad_channel = [
                        row
                        for row in rows
                        if row[1]
                        not in CONTROLLED_ACTION_CHANNELS
                    ]

                    self.assert_true(
                        stage,
                        (
                            "All Marketing Action "
                            "channels controlled"
                        ),
                        len(bad_channel) == 0,
                        str(bad_channel),
                    )

                    bad_type = [
                        row
                        for row in rows
                        if row[2]
                        not in CONTROLLED_ACTION_TYPES
                    ]

                    self.assert_true(
                        stage,
                        (
                            "All Marketing Action "
                            "types controlled"
                        ),
                        len(bad_type) == 0,
                        str(bad_type),
                    )

                    bad_status = [
                        row
                        for row in rows
                        if row[3]
                        not in CONTROLLED_ACTION_STATUSES
                    ]

                    self.assert_true(
                        stage,
                        (
                            "All Marketing Action "
                            "statuses controlled"
                        ),
                        len(bad_status) == 0,
                        str(bad_status),
                    )

                    bad_pair = [
                        row
                        for row in rows
                        if (
                            row[1],
                            row[2],
                        )
                        not in VALID_CHANNEL_ACTION_PAIRS
                    ]

                    self.assert_true(
                        stage,
                        (
                            "All channel/action "
                            "pairs valid"
                        ),
                        len(bad_pair) == 0,
                        str(bad_pair),
                    )

                    blank_content = [
                        row[0]
                        for row in rows
                        if (
                            row[4] is None
                            or not row[4].strip()
                        )
                    ]

                    self.assert_true(
                        stage,
                        (
                            "No Marketing Action "
                            "has blank content"
                        ),
                        (
                            len(
                                blank_content
                            )
                            == 0
                        ),
                        str(blank_content),
                    )

                    bad_email = [
                        row[0]
                        for row in rows
                        if (
                            row[1] == "EMAIL"
                            and (
                                row[5] is None
                                or not row[5].strip()
                                or row[6] is None
                            )
                        )
                    ]

                    self.assert_true(
                        stage,
                        (
                            "EMAIL actions have "
                            "subject and contact"
                        ),
                        len(bad_email) == 0,
                        str(bad_email),
                    )

        except Exception as exc:
            self.fail(
                stage,
                "Marketing Actions DB audit",
                repr(exc),
            )

    # ========================================================
    # Approval
    # ========================================================

    def check_approval_stage(
        self,
    ) -> None:
        stage = "APPROVAL"

        code, approvals = self.get(
            "/api/approvals"
        )

        self.assert_http(
            stage,
            "Approval list endpoint",
            code,
            200,
            approvals,
        )

        try:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            id::text,
                            marketing_action_id::text,
                            status,
                            content_snapshot,
                            decided_by,
                            decided_at
                        FROM approval_requests
                        """
                    )

                    rows = cur.fetchall()

                    self.pass_(
                        stage,
                        (
                            "ApprovalRequest rows "
                            "read successfully"
                        ),
                        f"count={len(rows)}",
                    )

                    bad_status = [
                        row
                        for row in rows
                        if row[2]
                        not in CONTROLLED_APPROVAL_STATUSES
                    ]

                    self.assert_true(
                        stage,
                        (
                            "All ApprovalRequest "
                            "statuses controlled"
                        ),
                        len(bad_status) == 0,
                        str(bad_status),
                    )

                    empty_snapshot = [
                        row[0]
                        for row in rows
                        if (
                            not isinstance(
                                row[3],
                                dict,
                            )
                            or not row[3]
                        )
                    ]

                    self.assert_true(
                        stage,
                        (
                            "All ApprovalRequests "
                            "have non-empty snapshots"
                        ),
                        (
                            len(
                                empty_snapshot
                            )
                            == 0
                        ),
                        str(
                            empty_snapshot
                        ),
                    )

                    decided_without_identity = [
                        row[0]
                        for row in rows
                        if (
                            row[2]
                            != "PENDING"
                            and (
                                row[4] is None
                                or not row[4].strip()
                                or row[5] is None
                            )
                        )
                    ]

                    self.assert_true(
                        stage,
                        (
                            "All decided approvals "
                            "have reviewer + "
                            "decision timestamp"
                        ),
                        (
                            len(
                                decided_without_identity
                            )
                            == 0
                        ),
                        str(
                            decided_without_identity
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

                    duplicate_pending = (
                        cur.fetchall()
                    )

                    self.assert_true(
                        stage,
                        (
                            "No duplicate PENDING "
                            "approval per action"
                        ),
                        (
                            len(
                                duplicate_pending
                            )
                            == 0
                        ),
                        str(
                            duplicate_pending
                        ),
                    )

                    cur.execute(
                        """
                        SELECT
                            ar.id::text,
                            ar.marketing_action_id::text,
                            ma.status
                        FROM approval_requests ar
                        JOIN marketing_actions ma
                          ON ma.id =
                             ar.marketing_action_id
                        WHERE ar.status = 'PENDING'
                          AND ma.status
                              <> 'PENDING_APPROVAL'
                        """
                    )

                    bad_sync = cur.fetchall()

                    self.assert_true(
                        stage,
                        (
                            "PENDING approvals "
                            "synchronized with "
                            "PENDING_APPROVAL actions"
                        ),
                        len(bad_sync) == 0,
                        str(bad_sync),
                    )

        except Exception as exc:
            self.fail(
                stage,
                "Approval DB audit",
                repr(exc),
            )

    # ========================================================
    # Cross-stage consistency
    # ========================================================

    def check_cross_stage_chain(
        self,
    ) -> None:
        stage = "CROSS_STAGE"

        if not self.lead_id:
            self.skip(
                stage,
                "Cross-stage lead chain",
                "No --lead-id supplied.",
            )
            return

        try:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            l.id::text,
                            l.status,
                            l.current_score,

                            (
                                SELECT COUNT(*)
                                FROM lead_research r
                                WHERE r.lead_id = l.id
                                  AND r.research_status IN (
                                      'COMPLETED',
                                      'PARTIAL'
                                  )
                            ) AS usable_research,

                            (
                                SELECT COUNT(*)
                                FROM lead_scores s
                                WHERE s.lead_id = l.id
                                  AND s.is_current = TRUE
                            ) AS current_scores,

                            (
                                SELECT COUNT(*)
                                FROM product_matches pm
                                WHERE pm.lead_id = l.id
                            ) AS product_matches,

                            (
                                SELECT COUNT(*)
                                FROM marketing_actions ma
                                WHERE ma.lead_id = l.id
                            ) AS marketing_actions,

                            (
                                SELECT COUNT(*)
                                FROM approval_requests ar
                                JOIN marketing_actions ma
                                  ON ma.id =
                                     ar.marketing_action_id
                                WHERE ma.lead_id = l.id
                            ) AS approvals

                        FROM leads l
                        WHERE l.id = %s::uuid
                        """,
                        (self.lead_id,),
                    )

                    row = cur.fetchone()

                    if row is None:
                        self.fail(
                            stage,
                            "Selected lead chain",
                            "lead missing",
                        )
                        return

                    (
                        lead_id,
                        status,
                        current_score,
                        usable_research,
                        current_scores,
                        product_matches,
                        marketing_actions,
                        approvals,
                    ) = row

                    self.pass_(
                        stage,
                        "Selected lead chain loaded",
                        (
                            f"lead={lead_id}, "
                            f"status={status}, "
                            f"score={current_score}"
                        ),
                    )

                    self.assert_true(
                        stage,
                        "Usable Research in chain",
                        usable_research >= 1,
                        (
                            f"count="
                            f"{usable_research}"
                        ),
                    )

                    self.assert_true(
                        stage,
                        "Exactly one current score in chain",
                        current_scores == 1,
                        (
                            f"count="
                            f"{current_scores}"
                        ),
                    )

                    self.assert_true(
                        stage,
                        "ProductMatch in chain",
                        product_matches >= 1,
                        (
                            f"count="
                            f"{product_matches}"
                        ),
                    )

                    self.assert_true(
                        stage,
                        "Marketing Action in chain",
                        marketing_actions >= 1,
                        (
                            f"count="
                            f"{marketing_actions}"
                        ),
                    )

                    self.assert_true(
                        stage,
                        "ApprovalRequest in chain",
                        approvals >= 1,
                        f"count={approvals}",
                    )

        except Exception as exc:
            self.fail(
                stage,
                "Cross-stage DB audit",
                repr(exc),
            )

    # ========================================================
    # Events
    # ========================================================

    def check_events(
        self,
    ) -> None:
        stage = "EVENTS"

        required_event_types = {
            "marketing_action_created",
            "marketing_action_updated",
            "marketing_action_cancelled",
            "marketing_action_submitted",
            "approval_requested",
            "approval_approved",
            "approval_rejected",
            "approval_changes_requested",
        }

        try:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            event_type,
                            COUNT(*)
                        FROM events
                        GROUP BY event_type
                        """
                    )

                    counts = {
                        event_type: count
                        for event_type, count
                        in cur.fetchall()
                    }

                    for event_type in sorted(
                        required_event_types
                    ):
                        self.assert_true(
                            stage,
                            (
                                "Event type exists: "
                                f"{event_type}"
                            ),
                            counts.get(
                                event_type,
                                0,
                            )
                            >= 1,
                            (
                                f"count="
                                f"{counts.get(event_type, 0)}"
                            ),
                        )

        except Exception as exc:
            self.fail(
                stage,
                "Event audit",
                repr(exc),
            )

    # ========================================================
    # Deep validator runner
    # ========================================================

    def run_deep_validators(
        self,
    ) -> None:
        stage = "DEEP"

        if not self.deep:
            self.skip(
                stage,
                "Existing module validators",
                (
                    "Use --deep to run "
                    "individual validators."
                ),
            )
            return

        if not self.scripts_dir.exists():
            self.fail(
                stage,
                "Scripts directory exists",
                str(self.scripts_dir),
            )
            return

        candidates = sorted(
            path
            for path in self.scripts_dir.glob(
                "validate_*_api.py"
            )
            if path.name
            not in {
                "validate_full_stack.py",
                "validate_all_api.py",
            }
        )

        if not candidates:
            self.fail(
                stage,
                "Discover module validators",
                (
                    f"No validate_*_api.py "
                    f"files found in "
                    f"{self.scripts_dir}"
                ),
            )
            return

        self.pass_(
            stage,
            "Discovered module validators",
            ", ".join(
                path.name
                for path in candidates
            ),
        )

        for path in candidates:
            self._run_one_validator(
                path
            )

    def _run_one_validator(
        self,
        path: Path,
    ) -> None:
        stage = "DEEP"

        try:
            help_result = subprocess.run(
                [
                    sys.executable,
                    str(path),
                    "--help",
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )

            help_text = (
                help_result.stdout
                + "\n"
                + help_result.stderr
            )

            command = [
                sys.executable,
                str(path),
            ]

            if (
                self.lead_id
                and "--lead-id"
                in help_text
            ):
                command.extend(
                    [
                        "--lead-id",
                        self.lead_id,
                    ]
                )

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=180,
            )

            output = (
                result.stdout
                + "\n"
                + result.stderr
            ).strip()

            tail = "\n".join(
                output.splitlines()[-12:]
            )

            if result.returncode == 0:
                self.pass_(
                    stage,
                    path.name,
                    tail,
                )
            else:
                self.fail(
                    stage,
                    path.name,
                    (
                        f"exit="
                        f"{result.returncode}\n"
                        f"{tail}"
                    ),
                )

        except subprocess.TimeoutExpired:
            self.fail(
                stage,
                path.name,
                "validator timed out",
            )

        except Exception as exc:
            self.fail(
                stage,
                path.name,
                repr(exc),
            )

    # ========================================================
    # Summary
    # ========================================================

    def summary(
        self,
    ) -> int:
        passes = sum(
            result.status == "PASS"
            for result in self.results
        )

        failures = sum(
            result.status == "FAIL"
            for result in self.results
        )

        skips = sum(
            result.status == "SKIP"
            for result in self.results
        )

        print(
            "\n"
            + "=" * 76
        )
        print(
            "LorrySystem Marketing API "
            "Full Stack Regression Summary"
        )
        print("=" * 76)

        print(
            f"PASS: {passes}"
        )
        print(
            f"FAIL: {failures}"
        )
        print(
            f"SKIP: {skips}"
        )

        stage_names = []
        for result in self.results:
            if (
                result.stage
                not in stage_names
            ):
                stage_names.append(
                    result.stage
                )

        print("\nStage summary:")

        for stage in stage_names:
            stage_results = [
                result
                for result in self.results
                if result.stage == stage
            ]

            p = sum(
                result.status == "PASS"
                for result in stage_results
            )

            f = sum(
                result.status == "FAIL"
                for result in stage_results
            )

            s = sum(
                result.status == "SKIP"
                for result in stage_results
            )

            state = (
                "PASSED"
                if f == 0
                else "FAILED"
            )

            print(
                f"  {stage:<20} "
                f"{state:<7} "
                f"(PASS {p}, FAIL {f}, SKIP {s})"
            )

        print()

        if failures:
            print(
                "RESULT: FAILED"
            )
            print(
                "Do not move to n8n integration "
                "until failures are understood."
            )
            return 1

        print(
            "RESULT: PASSED"
        )

        if self.deep:
            print(
                "Full regression audit + "
                "deep module validators passed."
            )
        else:
            print(
                "Read-only regression audit passed."
            )
            print(
                "For maximum confidence, "
                "run again with --deep."
            )

        return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the complete LorrySystem "
            "Marketing API MVP1 stack."
        )
    )

    parser.add_argument(
        "--base-url",
        default=(
            "http://127.0.0.1:8000"
        ),
    )

    parser.add_argument(
        "--lead-id",
        default=None,
        help=(
            "Known lead that has completed "
            "Research, Scoring, Product Matching, "
            "Marketing Actions and Approval."
        ),
    )

    parser.add_argument(
        "--scripts-dir",
        default="/app/scripts",
        help=(
            "Directory containing existing "
            "validate_*_api.py scripts."
        ),
    )

    parser.add_argument(
        "--deep",
        action="store_true",
        help=(
            "Run all discovered individual "
            "module validators after the "
            "read-only regression audit. "
            "Module validators may create or "
            "update validation data."
        ),
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    validator = FullStackValidator(
        base_url=args.base_url,
        lead_id=args.lead_id,
        scripts_dir=args.scripts_dir,
        deep=args.deep,
    )

    print("=" * 76)
    print(
        "LorrySystem Marketing API "
        "Full Stack Regression Validator"
    )
    print("=" * 76)
    print(
        f"Base URL: {args.base_url}"
    )
    print(
        f"Expected Alembic head: "
        f"{EXPECTED_ALEMBIC_HEAD}"
    )
    print(
        f"Lead ID: "
        f"{args.lead_id or 'not supplied'}"
    )
    print(
        f"Mode: "
        f"{'DEEP' if args.deep else 'READ-ONLY AUDIT'}"
    )
    print()

    validator.check_health_and_openapi()
    validator.check_routes()
    validator.check_database_structure()

    validator.check_foundation_apis()
    validator.check_research_stage()
    validator.check_scoring_stage()
    validator.check_product_matching_stage()
    validator.check_marketing_actions_stage()
    validator.check_approval_stage()

    validator.check_cross_stage_chain()
    validator.check_events()

    validator.run_deep_validators()

    return validator.summary()


if __name__ == "__main__":
    sys.exit(main())
