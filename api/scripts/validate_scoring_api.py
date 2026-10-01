#!/usr/bin/env python3
"""
LorrySystem Scoring API MVP1 validation suite.

Run inside the Marketing API container:

    python /tmp/validate_scoring_api.py \
        --lead-id dcb7d435-cf8c-4202-868f-3666dc53f8ac

Optional extra leads:

    --unresearched-lead-id <uuid>
        A real non-terminal lead with no COMPLETED/PARTIAL research.
        Used to validate "no usable research -> 409".

    --no-score-lead-id <uuid>
        A real lead with no current score.
        Used to validate "current score missing -> 404".

This is an integration test. It creates two new valid score rows on the
selected researched lead so score replacement/history can be validated.
It intentionally leaves those score rows in the database.
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


EXPECTED_SCORING_ROUTES = {
    "/api/leads/{lead_id}/scores": {"get", "post"},
    "/api/leads/{lead_id}/scores/current": {"get"},
    "/api/scoring/{score_id}": {"get"},
}

USABLE_RESEARCH_STATUSES = {
    "COMPLETED",
    "PARTIAL",
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
        self.initial_current_score: int | None = None
        self.created_score_ids: list[str] = []

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
        expected: int,
        payload: Any,
    ) -> bool:
        return self.assert_true(
            name,
            actual == expected,
            (
                f"HTTP {actual}, expected {expected}; "
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
            with urllib.request.urlopen(
                req,
                timeout=15,
            ) as response:
                raw = response.read().decode("utf-8")
                payload = (
                    json.loads(raw)
                    if raw
                    else None
                )
                return response.status, payload

        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")

            try:
                payload = (
                    json.loads(raw)
                    if raw
                    else None
                )
            except json.JSONDecodeError:
                payload = raw

            return exc.code, payload

        except Exception as exc:
            return 0, {
                "error": repr(exc)
            }

    def get(
        self,
        path: str,
    ) -> tuple[int, Any]:
        return self.request(
            "GET",
            path,
        )

    def post(
        self,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        return self.request(
            "POST",
            path,
            body,
        )

    # ========================================================
    # Database helpers
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
    # OpenAPI
    # ========================================================

    def check_openapi(self) -> None:
        code, payload = self.get(
            "/openapi.json"
        )

        if not self.assert_true(
            "OpenAPI reachable",
            code == 200
            and isinstance(payload, dict),
            f"HTTP {code}",
        ):
            return

        paths = payload.get(
            "paths",
            {},
        )

        for (
            path,
            expected_methods,
        ) in EXPECTED_SCORING_ROUTES.items():
            actual_methods = {
                key.lower()
                for key in paths.get(
                    path,
                    {},
                ).keys()
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
    # DB schema / constraints
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
                          AND table_name = 'lead_scores'
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
                        "total_score",
                        "score_breakdown",
                        "scoring_version",
                        "rationale",
                        "is_current",
                        "created_at",
                    }

                    self.assert_true(
                        "lead_scores columns present",
                        required_columns.issubset(
                            columns.keys()
                        ),
                        str(
                            sorted(
                                columns.keys()
                            )
                        ),
                    )

                    self.assert_true(
                        "total_score is NOT NULL",
                        columns.get(
                            "total_score",
                            {},
                        ).get(
                            "nullable"
                        )
                        == "NO",
                    )

                    self.assert_true(
                        "scoring_version is NOT NULL",
                        columns.get(
                            "scoring_version",
                            {},
                        ).get(
                            "nullable"
                        )
                        == "NO",
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
                          AND t.relname = 'lead_scores'
                        """
                    )

                    constraints = {
                        row[0]
                        for row in cur.fetchall()
                    }

                    self.assert_true(
                        "Score range DB constraint exists",
                        (
                            "ck_lead_scores_total_score_range"
                            in constraints
                        ),
                        str(sorted(constraints)),
                    )

                    cur.execute(
                        """
                        SELECT indexname, indexdef
                        FROM pg_indexes
                        WHERE schemaname = 'public'
                          AND tablename = 'lead_scores'
                        """
                    )

                    indexes = {
                        row[0]: row[1]
                        for row in cur.fetchall()
                    }

                    self.assert_true(
                        "Lead score history index exists",
                        (
                            "idx_lead_scores_lead_id"
                            in indexes
                        ),
                    )

                    current_index = indexes.get(
                        "idx_lead_scores_one_current",
                        "",
                    )

                    self.assert_true(
                        "One-current-score DB index exists",
                        bool(current_index),
                        current_index,
                    )

                    self.assert_true(
                        "One-current-score index is UNIQUE",
                        "UNIQUE INDEX"
                        in current_index.upper(),
                        current_index,
                    )

                    self.assert_true(
                        "One-current-score index is partial",
                        "WHERE"
                        in current_index.upper()
                        and "IS TRUE"
                        in current_index.upper(),
                        current_index,
                    )

        except Exception as exc:
            self.fail(
                "Database schema checks",
                repr(exc),
            )

    # ========================================================
    # Lead selection / research eligibility
    # ========================================================

    def choose_lead(
        self,
        explicit_lead_id: str | None,
    ) -> dict[str, Any] | None:

        if explicit_lead_id:
            code, lead = self.get(
                f"/api/leads/{explicit_lead_id}"
            )

            if code != 200:
                self.fail(
                    "Selected lead exists",
                    (
                        f"HTTP {code}: "
                        f"{lead}"
                    ),
                )
                return None

            self.pass_(
                "Selected lead exists",
                (
                    f"{lead['id']} "
                    f"({lead['status']})"
                ),
            )

            return lead

        code, leads = self.get(
            "/api/leads"
        )

        if (
            code != 200
            or not isinstance(
                leads,
                list,
            )
        ):
            self.fail(
                "List leads",
                (
                    f"HTTP {code}: "
                    f"{leads}"
                ),
            )
            return None

        for lead in leads:
            lead_id = lead["id"]

            r_code, research = self.get(
                (
                    f"/api/leads/"
                    f"{lead_id}/research"
                )
            )

            if (
                r_code == 200
                and isinstance(
                    research,
                    list,
                )
                and any(
                    item.get(
                        "research_status"
                    )
                    in USABLE_RESEARCH_STATUSES
                    for item in research
                )
            ):
                self.pass_(
                    "Auto-selected researched lead",
                    (
                        f"{lead_id} "
                        f"({lead['status']})"
                    ),
                )
                return lead

        self.fail(
            "Find researched lead",
            (
                "No lead with COMPLETED "
                "or PARTIAL research found."
            ),
        )
        return None

    def check_research_eligibility(
        self,
    ) -> bool:
        assert self.lead_id is not None

        code, research = self.get(
            (
                f"/api/leads/"
                f"{self.lead_id}/research"
            )
        )

        if not self.assert_http(
            "Research history reachable",
            code,
            200,
            research,
        ):
            return False

        usable = [
            row
            for row in research
            if row.get(
                "research_status"
            )
            in USABLE_RESEARCH_STATUSES
        ]

        return self.assert_true(
            "Lead has usable research for scoring",
            len(usable) >= 1,
            (
                f"usable_research="
                f"{len(usable)}"
            ),
        )

    # ========================================================
    # Generic score payload
    # ========================================================

    @staticmethod
    def score_payload(
        *,
        total_score: int,
        scoring_version: str,
        rationale: str,
        marker: str,
    ) -> dict[str, Any]:
        return {
            "total_score": total_score,
            "score_breakdown": {
                "validation_marker": marker,
                "country_fit": 10,
                "industry_fit": 20,
                "fleet_size": 18,
                "decision_maker": 10,
                "buying_signal": 12,
                "product_fit": 8,
            },
            "scoring_version": scoring_version,
            "rationale": rationale,
        }

    # ========================================================
    # 404 / validation paths
    # ========================================================

    def check_not_found_cases(
        self,
    ) -> None:
        fake_lead = str(
            uuid.uuid4()
        )

        code, payload = self.post(
            (
                f"/api/leads/"
                f"{fake_lead}/scores"
            ),
            self.score_payload(
                total_score=50,
                scoring_version="validator-not-found",
                rationale="Not found test.",
                marker="not-found",
            ),
        )

        self.assert_http(
            "Nonexistent lead score request rejected",
            code,
            404,
            payload,
        )

        fake_score = str(
            uuid.uuid4()
        )

        code, payload = self.get(
            f"/api/scoring/{fake_score}"
        )

        self.assert_http(
            "Nonexistent score lookup rejected",
            code,
            404,
            payload,
        )

    def check_schema_validation(
        self,
    ) -> None:
        assert self.lead_id is not None

        base = {
            "total_score": 50,
            "score_breakdown": {
                "test": 50
            },
            "scoring_version": "validation-v1",
            "rationale": "Validation request.",
        }

        cases: list[
            tuple[
                str,
                dict[str, Any],
            ]
        ] = []

        payload = dict(base)
        payload["total_score"] = -1
        cases.append(
            (
                "total_score -1 rejected",
                payload,
            )
        )

        payload = dict(base)
        payload["total_score"] = 101
        cases.append(
            (
                "total_score 101 rejected",
                payload,
            )
        )

        payload = dict(base)
        payload["scoring_version"] = ""
        cases.append(
            (
                "empty scoring_version rejected",
                payload,
            )
        )

        payload = dict(base)
        payload["scoring_version"] = "   "
        cases.append(
            (
                "blank scoring_version rejected",
                payload,
            )
        )

        payload = dict(base)
        payload["rationale"] = ""
        cases.append(
            (
                "empty rationale rejected",
                payload,
            )
        )

        payload = dict(base)
        payload["rationale"] = "   "
        cases.append(
            (
                "blank rationale rejected",
                payload,
            )
        )

        payload = {
            "total_score": 50,
            "score_breakdown": {},
            "rationale": (
                "Missing version test."
            ),
        }

        cases.append(
            (
                "missing scoring_version rejected",
                payload,
            )
        )

        for name, payload in cases:
            code, response = self.post(
                (
                    f"/api/leads/"
                    f"{self.lead_id}/scores"
                ),
                payload,
            )

            self.assert_http(
                name,
                code,
                422,
                response,
            )

    # ========================================================
    # Create / history / current replacement
    # ========================================================

    def create_validation_score(
        self,
        *,
        total_score: int,
        suffix: str,
    ) -> dict[str, Any] | None:
        assert self.lead_id is not None

        marker = uuid.uuid4().hex[:10]

        payload = self.score_payload(
            total_score=total_score,
            scoring_version=(
                f"validator-{suffix}"
            ),
            rationale=(
                f"Automated scoring "
                f"validation {suffix}."
            ),
            marker=marker,
        )

        code, score = self.post(
            (
                f"/api/leads/"
                f"{self.lead_id}/scores"
            ),
            payload,
        )

        if not self.assert_http(
            (
                f"Create validation score "
                f"{suffix}"
            ),
            code,
            201,
            score,
        ):
            return None

        self.created_score_ids.append(
            score["id"]
        )

        self.assert_true(
            (
                f"Score {suffix} "
                f"total persisted"
            ),
            score.get(
                "total_score"
            )
            == total_score,
            str(
                score.get(
                    "total_score"
                )
            ),
        )

        self.assert_true(
            (
                f"Score {suffix} "
                f"is current"
            ),
            (
                score.get(
                    "is_current"
                )
                is True
            ),
            str(
                score.get(
                    "is_current"
                )
            ),
        )

        return score

    def check_score_detail(
        self,
        score: dict[str, Any],
    ) -> None:
        score_id = score["id"]

        code, detail = self.get(
            f"/api/scoring/{score_id}"
        )

        if self.assert_http(
            "Score detail retrieval",
            code,
            200,
            detail,
        ):
            self.assert_true(
                "Score detail ID matches",
                (
                    detail.get("id")
                    == score_id
                ),
                str(
                    detail.get("id")
                ),
            )

    def check_current_endpoint(
        self,
        expected_score_id: str,
        expected_total: int,
    ) -> None:
        assert self.lead_id is not None

        code, current = self.get(
            (
                f"/api/leads/"
                f"{self.lead_id}"
                f"/scores/current"
            )
        )

        if not self.assert_http(
            "Current score endpoint",
            code,
            200,
            current,
        ):
            return

        self.assert_true(
            "Current endpoint returns expected score ID",
            (
                current.get("id")
                == expected_score_id
            ),
            str(
                current.get("id")
            ),
        )

        self.assert_true(
            "Current endpoint returns expected total",
            (
                current.get(
                    "total_score"
                )
                == expected_total
            ),
            str(
                current.get(
                    "total_score"
                )
            ),
        )

        self.assert_true(
            "Current endpoint score marked current",
            (
                current.get(
                    "is_current"
                )
                is True
            ),
            str(
                current.get(
                    "is_current"
                )
            ),
        )

    def check_lead_sync(
        self,
        expected_total: int,
    ) -> None:
        assert self.lead_id is not None

        code, lead = self.get(
            f"/api/leads/{self.lead_id}"
        )

        if not self.assert_http(
            "Lead readable after scoring",
            code,
            200,
            lead,
        ):
            return

        self.assert_true(
            "leads.current_score synchronized",
            (
                lead.get(
                    "current_score"
                )
                == expected_total
            ),
            (
                f"current_score="
                f"{lead.get('current_score')}"
            ),
        )

        self.assert_true(
            "Scoring does not mutate lead status",
            (
                lead.get("status")
                == self.initial_lead_status
            ),
            (
                f"initial="
                f"{self.initial_lead_status}, "
                f"current="
                f"{lead.get('status')}"
            ),
        )

    def check_history(
        self,
        first_score: dict[str, Any],
        second_score: dict[str, Any],
    ) -> None:
        assert self.lead_id is not None

        code, history = self.get(
            (
                f"/api/leads/"
                f"{self.lead_id}/scores"
            )
        )

        if not self.assert_http(
            "Score history retrieval",
            code,
            200,
            history,
        ):
            return

        if not isinstance(
            history,
            list,
        ):
            self.fail(
                "Score history response is a list",
                repr(history),
            )
            return

        self.pass_(
            "Score history response is a list",
            (
                f"{len(history)} "
                f"total score(s)"
            ),
        )

        history_by_id = {
            row["id"]: row
            for row in history
        }

        first_id = first_score["id"]
        second_id = second_score["id"]

        self.assert_true(
            "Both validation scores preserved",
            (
                first_id
                in history_by_id
                and second_id
                in history_by_id
            ),
            (
                f"first={first_id}, "
                f"second={second_id}"
            ),
        )

        if (
            first_id in history_by_id
            and second_id in history_by_id
        ):
            self.assert_true(
                "Previous validation score became non-current",
                (
                    history_by_id[
                        first_id
                    ].get(
                        "is_current"
                    )
                    is False
                ),
                str(
                    history_by_id[
                        first_id
                    ].get(
                        "is_current"
                    )
                ),
            )

            self.assert_true(
                "Newest validation score remains current",
                (
                    history_by_id[
                        second_id
                    ].get(
                        "is_current"
                    )
                    is True
                ),
                str(
                    history_by_id[
                        second_id
                    ].get(
                        "is_current"
                    )
                ),
            )

        ids = [
            row["id"]
            for row in history
        ]

        if (
            first_id in ids
            and second_id in ids
        ):
            self.assert_true(
                "Score history is newest first",
                (
                    ids.index(
                        second_id
                    )
                    < ids.index(
                        first_id
                    )
                ),
                (
                    f"first_index="
                    f"{ids.index(first_id)}, "
                    f"second_index="
                    f"{ids.index(second_id)}"
                ),
            )

    # ========================================================
    # DB invariant / events
    # ========================================================

    def check_db_invariants(
        self,
        expected_score_id: str,
        expected_total: int,
    ) -> None:
        assert self.lead_id is not None

        try:
            with self.db_connect() as conn:
                with conn.cursor() as cur:

                    cur.execute(
                        """
                        SELECT COUNT(*)
                        FROM lead_scores
                        WHERE lead_id = %s::uuid
                          AND is_current IS TRUE
                        """,
                        (
                            self.lead_id,
                        ),
                    )

                    current_count = (
                        cur.fetchone()[0]
                    )

                    self.assert_true(
                        "Exactly one current score in PostgreSQL",
                        current_count == 1,
                        (
                            f"current_count="
                            f"{current_count}"
                        ),
                    )

                    cur.execute(
                        """
                        SELECT
                            l.current_score,
                            s.id::text,
                            s.total_score,
                            s.is_current
                        FROM leads l
                        LEFT JOIN lead_scores s
                          ON s.lead_id = l.id
                         AND s.is_current IS TRUE
                        WHERE l.id = %s::uuid
                        """,
                        (
                            self.lead_id,
                        ),
                    )

                    row = cur.fetchone()

                    if row is None:
                        self.fail(
                            "Lead/current-score DB synchronization",
                            "Lead row missing.",
                        )
                    else:
                        (
                            lead_current,
                            score_id,
                            score_total,
                            is_current,
                        ) = row

                        self.assert_true(
                            "Lead/current-score DB synchronization",
                            (
                                lead_current
                                == expected_total
                                and score_total
                                == expected_total
                                and score_id
                                == expected_score_id
                                and is_current
                                is True
                            ),
                            (
                                f"lead_current="
                                f"{lead_current}, "
                                f"score_id="
                                f"{score_id}, "
                                f"score_total="
                                f"{score_total}, "
                                f"is_current="
                                f"{is_current}"
                            ),
                        )

        except Exception as exc:
            self.fail(
                "Scoring DB invariant checks",
                repr(exc),
            )

    def check_events(
        self,
        first_score: dict[str, Any],
        second_score: dict[str, Any],
    ) -> None:
        assert self.lead_id is not None

        try:
            with self.db_connect() as conn:
                with conn.cursor() as cur:

                    cur.execute(
                        """
                        SELECT
                            metadata
                        FROM events
                        WHERE entity_id = %s::uuid
                          AND event_type = 'lead_scored'
                        ORDER BY created_at
                        """,
                        (
                            self.lead_id,
                        ),
                    )

                    events = [
                        row[0]
                        for row in cur.fetchall()
                    ]

                    by_score = {
                        event.get(
                            "score_id"
                        ): event
                        for event in events
                    }

                    first_id = first_score["id"]
                    second_id = second_score["id"]

                    self.assert_true(
                        "lead_scored event exists for first validation score",
                        first_id
                        in by_score,
                        str(
                            sorted(
                                by_score.keys()
                            )
                        ),
                    )

                    self.assert_true(
                        "lead_scored event exists for second validation score",
                        second_id
                        in by_score,
                        str(
                            sorted(
                                by_score.keys()
                            )
                        ),
                    )

                    if first_id in by_score:
                        event = by_score[
                            first_id
                        ]

                        self.assert_true(
                            "First validation event references correct total",
                            (
                                event.get(
                                    "total_score"
                                )
                                == first_score[
                                    "total_score"
                                ]
                            ),
                            str(event),
                        )

                    if second_id in by_score:
                        event = by_score[
                            second_id
                        ]

                        self.assert_true(
                            "Second validation event previous_score is first score",
                            (
                                event.get(
                                    "previous_score"
                                )
                                == first_score[
                                    "total_score"
                                ]
                            ),
                            str(event),
                        )

        except Exception as exc:
            self.fail(
                "Scoring event checks",
                repr(exc),
            )

    # ========================================================
    # Optional business-rule leads
    # ========================================================

    def check_unresearched_lead(
        self,
        lead_id: str | None,
    ) -> None:
        if not lead_id:
            self.skip(
                "No usable research -> 409",
                (
                    "No --unresearched-lead-id "
                    "provided."
                ),
            )
            return

        code, research = self.get(
            (
                f"/api/leads/"
                f"{lead_id}/research"
            )
        )

        if code != 200:
            self.fail(
                "Unresearched test lead readable",
                (
                    f"research endpoint "
                    f"HTTP {code}: "
                    f"{research}"
                ),
            )
            return

        usable = [
            row
            for row in research
            if row.get(
                "research_status"
            )
            in USABLE_RESEARCH_STATUSES
        ]

        if usable:
            self.fail(
                "Unresearched test lead has no usable research",
                (
                    f"usable_research="
                    f"{len(usable)}"
                ),
            )
            return

        payload = self.score_payload(
            total_score=50,
            scoring_version=(
                "validator-no-research"
            ),
            rationale=(
                "No research eligibility test."
            ),
            marker="no-research",
        )

        code, response = self.post(
            (
                f"/api/leads/"
                f"{lead_id}/scores"
            ),
            payload,
        )

        self.assert_http(
            "No usable research -> 409",
            code,
            409,
            response,
        )

    def check_no_current_score_lead(
        self,
        lead_id: str | None,
    ) -> None:
        if not lead_id:
            self.skip(
                "No current score -> 404",
                (
                    "No --no-score-lead-id "
                    "provided."
                ),
            )
            return

        code, history = self.get(
            (
                f"/api/leads/"
                f"{lead_id}/scores"
            )
        )

        if code != 200:
            self.fail(
                "No-score test lead readable",
                (
                    f"score history "
                    f"HTTP {code}: "
                    f"{history}"
                ),
            )
            return

        current_rows = [
            row
            for row in history
            if row.get(
                "is_current"
            )
            is True
        ]

        if current_rows:
            self.fail(
                "No-score test lead has no current score",
                (
                    f"current_scores="
                    f"{len(current_rows)}"
                ),
            )
            return

        code, response = self.get(
            (
                f"/api/leads/"
                f"{lead_id}"
                f"/scores/current"
            )
        )

        self.assert_http(
            "No current score -> 404",
            code,
            404,
            response,
        )

    # ========================================================
    # Final summary
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

        print(
            "\n"
            + "=" * 72
        )
        print(
            "LorrySystem Scoring API "
            "Validation Summary"
        )
        print(
            "=" * 72
        )
        print(
            f"PASS: {passes}"
        )
        print(
            f"FAIL: {failures}"
        )
        print(
            f"SKIP: {skips}"
        )

        if self.created_score_ids:
            print(
                "\nCreated score rows:"
            )

            for score_id in (
                self.created_score_ids
            ):
                print(
                    f"  - {score_id}"
                )

        if failures:
            print(
                "\nRESULT: FAILED"
            )
            return 1

        print(
            "\nRESULT: PASSED"
        )
        return 0


# ============================================================
# CLI
# ============================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the LorrySystem "
            "Scoring API MVP1."
        )
    )

    parser.add_argument(
        "--base-url",
        default=(
            "http://127.0.0.1:8000"
        ),
        help=(
            "Marketing API base URL."
        ),
    )

    parser.add_argument(
        "--lead-id",
        default=None,
        help=(
            "Existing lead UUID with at least "
            "one COMPLETED/PARTIAL research run."
        ),
    )

    parser.add_argument(
        "--unresearched-lead-id",
        default=None,
        help=(
            "Optional real lead UUID with no "
            "COMPLETED/PARTIAL research."
        ),
    )

    parser.add_argument(
        "--no-score-lead-id",
        default=None,
        help=(
            "Optional real lead UUID with no "
            "current score."
        ),
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    validator = Validator(
        args.base_url
    )

    print(
        "=" * 72
    )
    print(
        "LorrySystem Scoring API "
        "MVP1 Validation"
    )
    print(
        "=" * 72
    )
    print(
        f"Base URL: "
        f"{validator.base_url}\n"
    )

    validator.check_openapi()
    validator.check_db_schema()
    validator.check_not_found_cases()

    lead = validator.choose_lead(
        args.lead_id
    )

    if not lead:
        return validator.summary()

    validator.lead_id = lead["id"]
    validator.initial_lead_status = (
        lead["status"]
    )
    validator.initial_current_score = (
        lead.get(
            "current_score"
        )
    )

    print(
        f"\nUsing lead: "
        f"{validator.lead_id} "
        f"(initial status: "
        f"{validator.initial_lead_status}, "
        f"initial current_score: "
        f"{validator.initial_current_score})\n"
    )

    if not validator.check_research_eligibility():
        return validator.summary()

    validator.check_schema_validation()

    # Use clearly different scores so replacement behavior is
    # unambiguous even if the lead already has score history.
    first_score = (
        validator.create_validation_score(
            total_score=73,
            suffix="run-a",
        )
    )

    if not first_score:
        return validator.summary()

    validator.check_score_detail(
        first_score
    )

    validator.check_current_endpoint(
        first_score["id"],
        first_score["total_score"],
    )

    validator.check_lead_sync(
        first_score["total_score"]
    )

    second_score = (
        validator.create_validation_score(
            total_score=87,
            suffix="run-b",
        )
    )

    if not second_score:
        return validator.summary()

    validator.check_current_endpoint(
        second_score["id"],
        second_score["total_score"],
    )

    validator.check_lead_sync(
        second_score["total_score"]
    )

    validator.check_history(
        first_score,
        second_score,
    )

    validator.check_db_invariants(
        second_score["id"],
        second_score["total_score"],
    )

    validator.check_events(
        first_score,
        second_score,
    )

    validator.check_unresearched_lead(
        args.unresearched_lead_id
    )

    validator.check_no_current_score_lead(
        args.no_score_lead_id
    )

    return validator.summary()


if __name__ == "__main__":
    sys.exit(
        main()
    )
