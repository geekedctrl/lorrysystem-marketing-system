#!/usr/bin/env python3
"""
LorrySystem Product Matching API MVP1 validation suite.

Typical run inside the Marketing API container:

    python /tmp/validate_product_matching_api.py \
        --lead-id dcb7d435-cf8c-4202-868f-3666dc53f8ac

Optional:

    --product-id <uuid>
        Force a specific active product for validation.

    --no-score-lead-id <uuid>
        Optional real non-terminal lead with current_score = NULL.
        Used to validate "no current score -> 409".

    --inactive-product-id <uuid>
        Optional real inactive product UUID.
        Used to validate "inactive product -> 409".

This is an integration test. It creates or updates one ProductMatch row
for the chosen lead/product pair and leaves the final validated state in
the database.
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


EXPECTED_ROUTES = {
    "/api/products": {"get"},
    "/api/products/{product_id}": {"get"},
    "/api/leads/{lead_id}/product-matches": {"get", "post"},
    "/api/product-matches/{match_id}": {"get"},
}

TERMINAL_STATUSES = {
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
        self.product_id: str | None = None
        self.initial_lead_status: str | None = None
        self.initial_lead_score: int | None = None
        self.match_id: str | None = None

    # ========================================================
    # Result helpers
    # ========================================================

    def pass_(self, name: str, detail: str = "") -> None:
        self.results.append(Result(name, "PASS", detail))
        print(f"[PASS] {name}" + (f" — {detail}" if detail else ""))

    def fail(self, name: str, detail: str = "") -> None:
        self.results.append(Result(name, "FAIL", detail))
        print(f"[FAIL] {name}" + (f" — {detail}" if detail else ""))

    def skip(self, name: str, detail: str = "") -> None:
        self.results.append(Result(name, "SKIP", detail))
        print(f"[SKIP] {name}" + (f" — {detail}" if detail else ""))

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

        ok = actual in expected_values

        return self.assert_true(
            name,
            ok,
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

    def post(
        self,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        return self.request("POST", path, body)

    # ========================================================
    # DB helpers
    # ========================================================

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
    # OpenAPI
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
                key.lower()
                for key in paths.get(path, {}).keys()
                if key.lower()
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

    # ========================================================
    # DB schema / indexes
    # ========================================================

    def check_db_schema(self) -> None:
        try:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            column_name,
                            is_nullable,
                            column_default
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'product_matches'
                        """
                    )

                    columns = {
                        row[0]: {
                            "nullable": row[1],
                            "default": row[2],
                        }
                        for row in cur.fetchall()
                    }

                    required = {
                        "id",
                        "lead_id",
                        "product_id",
                        "fit_score",
                        "rationale",
                        "created_at",
                        "updated_at",
                    }

                    self.assert_true(
                        "product_matches columns present",
                        required.issubset(columns.keys()),
                        str(sorted(columns.keys())),
                    )

                    self.assert_true(
                        "fit_score is NOT NULL",
                        columns.get("fit_score", {}).get("nullable") == "NO",
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
                          AND t.relname = 'product_matches'
                        """
                    )

                    constraints = {
                        row[0]
                        for row in cur.fetchall()
                    }

                    self.assert_true(
                        "Product-match score range DB constraint exists",
                        "ck_product_matches_fit_score_range" in constraints,
                        str(sorted(constraints)),
                    )

                    cur.execute(
                        """
                        SELECT indexname, indexdef
                        FROM pg_indexes
                        WHERE schemaname = 'public'
                          AND tablename = 'product_matches'
                        """
                    )

                    indexes = {
                        row[0]: row[1]
                        for row in cur.fetchall()
                    }

                    unique_index = indexes.get(
                        "idx_product_matches_unique",
                        "",
                    )

                    self.assert_true(
                        "Lead/product unique index exists",
                        bool(unique_index),
                        unique_index,
                    )

                    self.assert_true(
                        "Lead/product index is UNIQUE",
                        "UNIQUE INDEX" in unique_index.upper(),
                        unique_index,
                    )

        except Exception as exc:
            self.fail("Database schema checks", repr(exc))

    # ========================================================
    # Catalog
    # ========================================================

    def get_products(self) -> list[dict[str, Any]] | None:
        code, products = self.get("/api/products")

        if not self.assert_http(
            "Product catalog endpoint",
            code,
            200,
            products,
        ):
            return None

        if not self.assert_true(
            "Product catalog returns a list",
            isinstance(products, list),
            repr(products),
        ):
            return None

        self.assert_true(
            "Product catalog has active products",
            len(products) >= 1,
            f"count={len(products)}",
        )

        return products

    def choose_product(
        self,
        explicit_product_id: str | None,
    ) -> dict[str, Any] | None:
        products = self.get_products()

        if not products:
            return None

        if explicit_product_id:
            code, product = self.get(
                f"/api/products/{explicit_product_id}"
            )

            if not self.assert_http(
                "Selected product exists",
                code,
                200,
                product,
            ):
                return None

            if not self.assert_true(
                "Selected product is active",
                product.get("active") is True,
                str(product.get("active")),
            ):
                return None

            return product

        # Prefer AI_DASHCAM when available for deterministic tests.
        for product in products:
            if (
                product.get("code") == "AI_DASHCAM"
                and product.get("active") is True
            ):
                self.pass_(
                    "Auto-selected product",
                    (
                        f"{product['code']} "
                        f"({product['id']})"
                    ),
                )
                return product

        for product in products:
            if product.get("active") is True:
                self.pass_(
                    "Auto-selected product",
                    (
                        f"{product['code']} "
                        f"({product['id']})"
                    ),
                )
                return product

        self.fail(
            "Find active product",
            "No active product available.",
        )
        return None

    # ========================================================
    # Lead selection
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
                lead.get("current_score") is not None
                and lead.get("status") not in TERMINAL_STATUSES
            ):
                self.pass_(
                    "Auto-selected scored lead",
                    (
                        f"{lead['id']} "
                        f"(status={lead['status']}, "
                        f"current_score={lead['current_score']})"
                    ),
                )
                return lead

        self.fail(
            "Find scored non-terminal lead",
            "No suitable lead found.",
        )
        return None

    # ========================================================
    # Negative-path checks
    # ========================================================

    def check_not_found_cases(self) -> None:
        fake_product = str(uuid.uuid4())
        code, payload = self.get(
            f"/api/products/{fake_product}"
        )
        self.assert_http(
            "Nonexistent product lookup rejected",
            code,
            404,
            payload,
        )

        fake_match = str(uuid.uuid4())
        code, payload = self.get(
            f"/api/product-matches/{fake_match}"
        )
        self.assert_http(
            "Nonexistent ProductMatch lookup rejected",
            code,
            404,
            payload,
        )

        fake_lead = str(uuid.uuid4())

        product_id = self.product_id or str(uuid.uuid4())

        code, payload = self.post(
            f"/api/leads/{fake_lead}/product-matches",
            {
                "product_id": product_id,
                "fit_score": 50,
                "rationale": "Not found test.",
            },
        )

        self.assert_http(
            "Nonexistent lead ProductMatch request rejected",
            code,
            404,
            payload,
        )

    def check_schema_validation(self) -> None:
        assert self.lead_id is not None
        assert self.product_id is not None

        base = {
            "product_id": self.product_id,
            "fit_score": 50,
            "rationale": "Validation request.",
        }

        cases: list[tuple[str, dict[str, Any]]] = []

        payload = dict(base)
        payload["fit_score"] = -1
        cases.append(
            ("fit_score -1 rejected", payload)
        )

        payload = dict(base)
        payload["fit_score"] = 101
        cases.append(
            ("fit_score 101 rejected", payload)
        )

        payload = dict(base)
        payload["rationale"] = ""
        cases.append(
            ("empty rationale rejected", payload)
        )

        payload = dict(base)
        payload["rationale"] = "   "
        cases.append(
            ("blank rationale rejected", payload)
        )

        payload = {
            "product_id": self.product_id,
            "fit_score": 50,
        }
        cases.append(
            ("missing rationale rejected", payload)
        )

        fake_product = str(uuid.uuid4())
        payload = {
            "product_id": fake_product,
            "fit_score": 50,
            "rationale": "Missing product test.",
        }

        for name, body in cases:
            code, response = self.post(
                f"/api/leads/{self.lead_id}/product-matches",
                body,
            )
            self.assert_http(
                name,
                code,
                422,
                response,
            )

        code, response = self.post(
            f"/api/leads/{self.lead_id}/product-matches",
            payload,
        )
        self.assert_http(
            "Unknown product rejected",
            code,
            404,
            response,
        )

    # ========================================================
    # Match upsert flow
    # ========================================================

    def get_existing_pair_match(
        self,
    ) -> dict[str, Any] | None:
        assert self.lead_id is not None
        assert self.product_id is not None

        code, matches = self.get(
            f"/api/leads/{self.lead_id}/product-matches"
        )

        if code != 200 or not isinstance(matches, list):
            return None

        for item in matches:
            if item.get("product_id") == self.product_id:
                return item

        return None

    def create_or_update_first_match(
        self,
    ) -> dict[str, Any] | None:
        assert self.lead_id is not None
        assert self.product_id is not None

        existing = self.get_existing_pair_match()

        payload = {
            "product_id": self.product_id,
            "fit_score": 88,
            "rationale": (
                "Automated validation: strong product fit "
                "for the scored lead."
            ),
        }

        code, match = self.post(
            f"/api/leads/{self.lead_id}/product-matches",
            payload,
        )

        expected = 200 if existing else 201

        if not self.assert_http(
            (
                "Initial ProductMatch upsert "
                + ("updates existing row" if existing else "creates row")
            ),
            code,
            expected,
            match,
        ):
            return None

        self.match_id = match["id"]

        self.assert_true(
            "Initial ProductMatch fit_score persisted",
            match.get("fit_score") == 88,
            str(match.get("fit_score")),
        )

        self.assert_true(
            "Initial ProductMatch product_id persisted",
            match.get("product_id") == self.product_id,
            str(match.get("product_id")),
        )

        if existing:
            self.assert_true(
                "Existing ProductMatch ID preserved on upsert",
                match.get("id") == existing.get("id"),
                (
                    f"before={existing.get('id')}, "
                    f"after={match.get('id')}"
                ),
            )

        return match

    def update_same_match(
        self,
        first_match: dict[str, Any],
    ) -> dict[str, Any] | None:
        assert self.lead_id is not None
        assert self.product_id is not None

        payload = {
            "product_id": self.product_id,
            "fit_score": 94,
            "rationale": (
                "Automated validation update: stronger "
                "fit after revised product assessment."
            ),
        }

        code, updated = self.post(
            f"/api/leads/{self.lead_id}/product-matches",
            payload,
        )

        if not self.assert_http(
            "Existing ProductMatch update returns 200",
            code,
            200,
            updated,
        ):
            return None

        self.assert_true(
            "ProductMatch row ID unchanged on update",
            updated.get("id") == first_match.get("id"),
            (
                f"before={first_match.get('id')}, "
                f"after={updated.get('id')}"
            ),
        )

        self.assert_true(
            "Updated fit_score persisted",
            updated.get("fit_score") == 94,
            str(updated.get("fit_score")),
        )

        self.assert_true(
            "created_at preserved on update",
            updated.get("created_at") == first_match.get("created_at"),
            (
                f"before={first_match.get('created_at')}, "
                f"after={updated.get('created_at')}"
            ),
        )

        self.assert_true(
            "updated_at not older than initial value",
            updated.get("updated_at") >= first_match.get("updated_at"),
            (
                f"before={first_match.get('updated_at')}, "
                f"after={updated.get('updated_at')}"
            ),
        )

        return updated

    def check_match_detail(
        self,
        expected: dict[str, Any],
    ) -> None:
        code, match = self.get(
            f"/api/product-matches/{expected['id']}"
        )

        if not self.assert_http(
            "ProductMatch detail retrieval",
            code,
            200,
            match,
        ):
            return

        self.assert_true(
            "ProductMatch detail ID matches",
            match.get("id") == expected.get("id"),
            str(match.get("id")),
        )

        self.assert_true(
            "ProductMatch detail fit_score matches",
            match.get("fit_score") == expected.get("fit_score"),
            str(match.get("fit_score")),
        )

    def check_match_list(
        self,
        expected: dict[str, Any],
    ) -> None:
        assert self.lead_id is not None

        code, matches = self.get(
            f"/api/leads/{self.lead_id}/product-matches"
        )

        if not self.assert_http(
            "Lead ProductMatch list retrieval",
            code,
            200,
            matches,
        ):
            return

        if not isinstance(matches, list):
            self.fail(
                "Lead ProductMatch list is a list",
                repr(matches),
            )
            return

        self.pass_(
            "Lead ProductMatch list is a list",
            f"count={len(matches)}",
        )

        matching_ids = [
            row.get("id")
            for row in matches
            if row.get("product_id") == self.product_id
        ]

        self.assert_true(
            "Exactly one row exists for lead/product pair",
            len(matching_ids) == 1,
            str(matching_ids),
        )

        if expected.get("id") in matching_ids:
            self.pass_(
                "Updated ProductMatch present in lead list",
                expected["id"],
            )
        else:
            self.fail(
                "Updated ProductMatch present in lead list",
                (
                    f"expected={expected.get('id')}, "
                    f"found={matching_ids}"
                ),
            )

        # API is intended to order highest fit first.
        scores = [
            row.get("fit_score")
            for row in matches
            if isinstance(row.get("fit_score"), int)
        ]

        self.assert_true(
            "ProductMatch list ordered by fit_score descending",
            scores == sorted(scores, reverse=True),
            str(scores),
        )

    def check_lead_unchanged(self) -> None:
        assert self.lead_id is not None

        code, lead = self.get(
            f"/api/leads/{self.lead_id}"
        )

        if not self.assert_http(
            "Lead readable after Product Matching",
            code,
            200,
            lead,
        ):
            return

        self.assert_true(
            "Product Matching does not mutate lead status",
            lead.get("status") == self.initial_lead_status,
            (
                f"initial={self.initial_lead_status}, "
                f"current={lead.get('status')}"
            ),
        )

        self.assert_true(
            "Product Matching does not mutate lead current_score",
            lead.get("current_score") == self.initial_lead_score,
            (
                f"initial={self.initial_lead_score}, "
                f"current={lead.get('current_score')}"
            ),
        )

    # ========================================================
    # DB invariants
    # ========================================================

    def check_db_invariants(
        self,
        expected: dict[str, Any],
    ) -> None:
        assert self.lead_id is not None
        assert self.product_id is not None

        try:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT COUNT(*)
                        FROM product_matches
                        WHERE lead_id = %s::uuid
                          AND product_id = %s::uuid
                        """,
                        (
                            self.lead_id,
                            self.product_id,
                        ),
                    )

                    pair_count = cur.fetchone()[0]

                    self.assert_true(
                        "Exactly one ProductMatch row in PostgreSQL for pair",
                        pair_count == 1,
                        f"pair_count={pair_count}",
                    )

                    cur.execute(
                        """
                        SELECT
                            id::text,
                            fit_score,
                            rationale,
                            created_at,
                            updated_at
                        FROM product_matches
                        WHERE lead_id = %s::uuid
                          AND product_id = %s::uuid
                        """,
                        (
                            self.lead_id,
                            self.product_id,
                        ),
                    )

                    row = cur.fetchone()

                    if row is None:
                        self.fail(
                            "ProductMatch DB row exists",
                            "No row found.",
                        )
                        return

                    (
                        match_id,
                        fit_score,
                        rationale,
                        created_at,
                        updated_at,
                    ) = row

                    self.assert_true(
                        "ProductMatch DB ID matches API",
                        match_id == expected["id"],
                        (
                            f"db={match_id}, "
                            f"api={expected['id']}"
                        ),
                    )

                    self.assert_true(
                        "ProductMatch DB fit_score matches API",
                        fit_score == expected["fit_score"],
                        (
                            f"db={fit_score}, "
                            f"api={expected['fit_score']}"
                        ),
                    )

                    self.assert_true(
                        "ProductMatch DB rationale matches API",
                        rationale == expected["rationale"],
                        rationale or "",
                    )

                    self.assert_true(
                        "ProductMatch timestamps present",
                        created_at is not None and updated_at is not None,
                        (
                            f"created_at={created_at}, "
                            f"updated_at={updated_at}"
                        ),
                    )

        except Exception as exc:
            self.fail(
                "ProductMatch DB invariant checks",
                repr(exc),
            )

    # ========================================================
    # Events
    # ========================================================

    def check_events(self) -> None:
        assert self.match_id is not None
        assert self.lead_id is not None
        assert self.product_id is not None

        try:
            with self.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            event_type,
                            metadata
                        FROM events
                        WHERE entity_type = 'PRODUCT_MATCH'
                          AND entity_id = %s::uuid
                          AND event_type IN (
                              'product_matched',
                              'product_match_updated'
                          )
                        ORDER BY created_at
                        """,
                        (self.match_id,),
                    )

                    events = cur.fetchall()

                    self.assert_true(
                        "Product Matching event(s) exist",
                        len(events) >= 1,
                        f"count={len(events)}",
                    )

                    update_events = [
                        metadata
                        for event_type, metadata in events
                        if event_type == "product_match_updated"
                    ]

                    self.assert_true(
                        "product_match_updated event exists",
                        len(update_events) >= 1,
                        f"count={len(update_events)}",
                    )

                    if update_events:
                        latest = update_events[-1]

                        self.assert_true(
                            "Updated event references correct lead",
                            latest.get("lead_id") == self.lead_id,
                            str(latest),
                        )

                        self.assert_true(
                            "Updated event references correct product",
                            latest.get("product_id") == self.product_id,
                            str(latest),
                        )

                        self.assert_true(
                            "Updated event references correct match",
                            latest.get("product_match_id") == self.match_id,
                            str(latest),
                        )

                        self.assert_true(
                            "Updated event stores final fit_score",
                            latest.get("fit_score") == 94,
                            str(latest),
                        )

                        self.assert_true(
                            "Updated event stores previous_fit_score",
                            latest.get("previous_fit_score") == 88,
                            str(latest),
                        )

                        self.assert_true(
                            "Updated event records lead current score",
                            latest.get("lead_current_score")
                            == self.initial_lead_score,
                            str(latest),
                        )

        except Exception as exc:
            self.fail(
                "Product Matching event checks",
                repr(exc),
            )

    # ========================================================
    # Optional environment-dependent checks
    # ========================================================

    def check_no_score_lead(
        self,
        lead_id: str | None,
    ) -> None:
        if not lead_id:
            self.skip(
                "No current score -> 409",
                "No --no-score-lead-id provided.",
            )
            return

        code, lead = self.get(
            f"/api/leads/{lead_id}"
        )

        if code != 200:
            self.fail(
                "No-score test lead exists",
                f"HTTP {code}: {lead}",
            )
            return

        if lead.get("current_score") is not None:
            self.fail(
                "No-score test lead has current_score = NULL",
                f"current_score={lead.get('current_score')}",
            )
            return

        if lead.get("status") in TERMINAL_STATUSES:
            self.fail(
                "No-score test lead is non-terminal",
                f"status={lead.get('status')}",
            )
            return

        assert self.product_id is not None

        code, payload = self.post(
            f"/api/leads/{lead_id}/product-matches",
            {
                "product_id": self.product_id,
                "fit_score": 50,
                "rationale": "No current score validation.",
            },
        )

        self.assert_http(
            "No current score -> 409",
            code,
            409,
            payload,
        )

    def check_inactive_product(
        self,
        inactive_product_id: str | None,
    ) -> None:
        if not inactive_product_id:
            self.skip(
                "Inactive product -> 409",
                "No --inactive-product-id provided.",
            )
            return

        assert self.lead_id is not None

        code, product = self.get(
            f"/api/products/{inactive_product_id}"
        )

        if code != 200:
            self.fail(
                "Inactive product exists",
                f"HTTP {code}: {product}",
            )
            return

        if product.get("active") is not False:
            self.fail(
                "Inactive-product test product is inactive",
                f"active={product.get('active')}",
            )
            return

        code, payload = self.post(
            f"/api/leads/{self.lead_id}/product-matches",
            {
                "product_id": inactive_product_id,
                "fit_score": 50,
                "rationale": "Inactive product validation.",
            },
        )

        self.assert_http(
            "Inactive product -> 409",
            code,
            409,
            payload,
        )

    # ========================================================
    # Final summary
    # ========================================================

    def summary(self) -> int:
        passes = sum(
            1
            for item in self.results
            if item.status == "PASS"
        )

        failures = sum(
            1
            for item in self.results
            if item.status == "FAIL"
        )

        skips = sum(
            1
            for item in self.results
            if item.status == "SKIP"
        )

        print("\n" + "=" * 72)
        print(
            "LorrySystem Product Matching API "
            "Validation Summary"
        )
        print("=" * 72)
        print(f"PASS: {passes}")
        print(f"FAIL: {failures}")
        print(f"SKIP: {skips}")

        if self.match_id:
            print(
                "\nValidated ProductMatch:"
            )
            print(
                f"  - {self.match_id}"
            )

        if failures:
            print("\nRESULT: FAILED")
            return 1

        print("\nRESULT: PASSED")
        return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate LorrySystem Product Matching API MVP1."
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
            "Existing non-terminal lead UUID "
            "with current_score populated."
        ),
    )

    parser.add_argument(
        "--product-id",
        default=None,
        help=(
            "Optional active Product UUID."
        ),
    )

    parser.add_argument(
        "--no-score-lead-id",
        default=None,
        help=(
            "Optional non-terminal lead UUID "
            "with current_score = NULL."
        ),
    )

    parser.add_argument(
        "--inactive-product-id",
        default=None,
        help=(
            "Optional inactive Product UUID."
        ),
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    validator = Validator(args.base_url)

    print("=" * 72)
    print(
        "LorrySystem Product Matching API "
        "MVP1 Validation"
    )
    print("=" * 72)
    print(
        f"Base URL: {validator.base_url}\n"
    )

    validator.check_openapi()
    validator.check_db_schema()

    lead = validator.choose_lead(
        args.lead_id
    )

    if not lead:
        return validator.summary()

    validator.lead_id = lead["id"]
    validator.initial_lead_status = lead["status"]
    validator.initial_lead_score = lead.get(
        "current_score"
    )

    validator.assert_true(
        "Selected lead has current score",
        validator.initial_lead_score is not None,
        (
            f"current_score="
            f"{validator.initial_lead_score}"
        ),
    )

    validator.assert_true(
        "Selected lead is non-terminal",
        validator.initial_lead_status
        not in TERMINAL_STATUSES,
        (
            f"status="
            f"{validator.initial_lead_status}"
        ),
    )

    product = validator.choose_product(
        args.product_id
    )

    if not product:
        return validator.summary()

    validator.product_id = product["id"]

    print(
        f"\nUsing lead: {validator.lead_id} "
        f"(status={validator.initial_lead_status}, "
        f"current_score={validator.initial_lead_score})"
    )
    print(
        f"Using product: {product['code']} "
        f"({validator.product_id})\n"
    )

    validator.check_not_found_cases()
    validator.check_schema_validation()

    first_match = validator.create_or_update_first_match()

    if not first_match:
        return validator.summary()

    updated_match = validator.update_same_match(
        first_match
    )

    if not updated_match:
        return validator.summary()

    validator.check_match_detail(
        updated_match
    )

    validator.check_match_list(
        updated_match
    )

    validator.check_lead_unchanged()

    validator.check_db_invariants(
        updated_match
    )

    validator.check_events()

    validator.check_no_score_lead(
        args.no_score_lead_id
    )

    validator.check_inactive_product(
        args.inactive_product_id
    )

    return validator.summary()


if __name__ == "__main__":
    sys.exit(main())
