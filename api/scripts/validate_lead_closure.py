from __future__ import annotations

import os
import sys
from uuid import UUID, uuid4

import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class StdlibResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        if isinstance(self._body, (dict, list)):
            return self._body
        return json.loads(self._body)

    @property
    def text(self):
        if isinstance(self._body, str):
            return self._body
        return json.dumps(self._body)


class StdlibClient:
    def __init__(
        self,
        *,
        base_url,
        headers=None,
        timeout=30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.headers = dict(headers or {})
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def request(
        self,
        method,
        path,
        *,
        json=None,
    ):
        body = None
        headers = dict(self.headers)

        if json is not None:
            body = __import__("json").dumps(
                json
            ).encode("utf-8")
            headers["Content-Type"] = (
                "application/json"
            )

        req = Request(
            self.base_url + path,
            data=body,
            headers=headers,
            method=method,
        )

        try:
            with urlopen(
                req,
                timeout=self.timeout,
            ) as response:
                raw = response.read().decode(
                    "utf-8"
                )

                try:
                    payload = (
                        __import__("json").loads(raw)
                        if raw
                        else None
                    )
                except ValueError:
                    payload = raw

                return StdlibResponse(
                    response.status,
                    payload,
                )

        except HTTPError as exc:
            raw = exc.read().decode("utf-8")

            try:
                payload = (
                    __import__("json").loads(raw)
                    if raw
                    else None
                )
            except ValueError:
                payload = raw

            return StdlibResponse(
                exc.code,
                payload,
            )
from sqlalchemy import select

from app.db.session import get_db
from app.models.catalog import ICPProfile
from app.models.marketing import Event


BASE_URL = "http://127.0.0.1:8000"

API_KEY = (
    os.getenv("MARKETING_API_KEY")
    or os.getenv("API_KEY")
    or os.getenv("LORRYSYSTEM_API_KEY")
    or ""
).strip()

PASS = 0
FAIL = 0

created = {}


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL

    if condition:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        print(f"[FAIL] {name}")
        if detail:
            print(f"       {detail}")


def request(
    client: StdlibClient,
    method: str,
    path: str,
    *,
    json: dict | None = None,
):
    response = client.request(
        method,
        path,
        json=json,
    )

    try:
        body = response.json()
    except ValueError:
        body = response.text

    return response.status_code, body


def get_icp_id() -> str:
    gen = get_db()
    db = next(gen)

    try:
        icp = db.scalars(
            select(ICPProfile)
        ).first()

        if icp is None:
            raise RuntimeError(
                "No ICP profile exists."
            )

        return str(icp.id)

    finally:
        db.close()


def create_test_lead(
    client: StdlibClient,
    icp_id: str,
    label: str,
):
    suffix = uuid4().hex[:8]

    company_name = (
        f"MVP1 Closure Regression "
        f"{label} {suffix}"
    )

    code, company = request(
        client,
        "POST",
        "/api/companies",
        json={
            "name": company_name,
            "source_type": "DASHBOARD_MANUAL",
            "metadata": {
                "entered_via":
                    "closure_regression_validator",
                "test_case": label,
            },
        },
    )

    check(
        f"{label}: company created",
        code == 201,
        f"HTTP {code}: {company}",
    )

    if code != 201:
        raise RuntimeError(
            f"Cannot create company for {label}"
        )

    code, lead = request(
        client,
        "POST",
        "/api/leads",
        json={
            "company_id": company["id"],
            "primary_contact_id": None,
            "icp_profile_id": icp_id,
            "priority": "MEDIUM",
        },
    )

    check(
        f"{label}: Lead created",
        code == 201,
        f"HTTP {code}: {lead}",
    )

    if code != 201:
        raise RuntimeError(
            f"Cannot create Lead for {label}"
        )

    created[label] = {
        "company_name": company_name,
        "company_id": company["id"],
        "lead_id": lead["id"],
    }

    return lead["id"]


def transition(
    client: StdlibClient,
    lead_id: str,
    status: str,
):
    return request(
        client,
        "PATCH",
        f"/api/leads/{lead_id}/status",
        json={
            "status": status,
        },
    )


def advance(
    client: StdlibClient,
    lead_id: str,
    statuses: list[str],
    label: str,
):
    for status in statuses:
        code, body = transition(
            client,
            lead_id,
            status,
        )

        check(
            f"{label}: transition → {status}",
            (
                code == 200
                and body.get("status") == status
            ),
            f"HTTP {code}: {body}",
        )

        if code != 200:
            raise RuntimeError(
                f"Transition failed for {label}"
            )


def close_lead(
    client: StdlibClient,
    lead_id: str,
    *,
    status: str,
    reason: str,
    note: str,
    label: str,
):
    code, body = request(
        client,
        "PATCH",
        f"/api/leads/{lead_id}/status",
        json={
            "status": status,
            "reason": reason,
            "note": note,
            "closed_by": "parimala",
        },
    )

    check(
        f"{label}: close HTTP 200",
        code == 200,
        f"HTTP {code}: {body}",
    )

    check(
        f"{label}: final status = {status}",
        (
            code == 200
            and body.get("status") == status
        ),
        str(body),
    )

    return code, body


def verify_event(
    lead_id: str,
    *,
    expected_status: str,
    expected_reason: str,
    expected_note: str,
    label: str,
):
    gen = get_db()
    db = next(gen)

    try:
        event = db.scalars(
            select(Event)
            .where(
                Event.entity_type == "LEAD",
                Event.entity_id == UUID(lead_id),
                Event.event_type == "lead_closed",
            )
            .order_by(
                Event.created_at.desc()
            )
        ).first()

        check(
            f"{label}: lead_closed Event exists",
            event is not None,
        )

        if event is None:
            return

        metadata = event.metadata_json or {}

        check(
            f"{label}: event new_status",
            metadata.get("new_status")
            == expected_status,
            str(metadata),
        )

        check(
            f"{label}: event reason",
            metadata.get("reason")
            == expected_reason,
            str(metadata),
        )

        check(
            f"{label}: event note",
            metadata.get("note")
            == expected_note,
            str(metadata),
        )

        check(
            f"{label}: event closed_by",
            metadata.get("closed_by")
            == "parimala",
            str(metadata),
        )

        check(
            f"{label}: event actor",
            (
                event.actor_type == "DASHBOARD"
                and event.actor_id == "parimala"
            ),
            (
                f"actor_type={event.actor_type}, "
                f"actor_id={event.actor_id}"
            ),
        )

        check(
            f"{label}: closure timestamp exists",
            event.created_at is not None,
        )

    finally:
        db.close()


def get_lead(
    client: StdlibClient,
    lead_id: str,
):
    return request(
        client,
        "GET",
        f"/api/leads/{lead_id}",
    )


def main():
    if not API_KEY:
        print(
            "[FATAL] No Marketing API key found "
            "inside container environment."
        )
        return 2

    icp_id = get_icp_id()

    headers = {
        "X-API-Key": API_KEY,
    }

    with StdlibClient(
        base_url=BASE_URL,
        headers=headers,
        timeout=30.0,
    ) as client:

        # ====================================================
        # 1. CONTACTED → LOST / NO_RESPONSE
        # ====================================================

        label = "CONTACTED_NO_RESPONSE"

        lead_id = create_test_lead(
            client,
            icp_id,
            label,
        )

        advance(
            client,
            lead_id,
            [
                "RESEARCHING",
                "QUALIFIED",
                "READY_FOR_OUTREACH",
                "CONTACTED",
            ],
            label,
        )

        note = (
            "Regression test: "
            "no response after follow-up."
        )

        close_lead(
            client,
            lead_id,
            status="LOST",
            reason="NO_RESPONSE",
            note=note,
            label=label,
        )

        verify_event(
            lead_id,
            expected_status="LOST",
            expected_reason="NO_RESPONSE",
            expected_note=note,
            label=label,
        )

        # Duplicate close must fail.
        code, body = request(
            client,
            "PATCH",
            f"/api/leads/{lead_id}/status",
            json={
                "status": "LOST",
                "reason": "NO_RESPONSE",
                "note": "Duplicate closure attempt",
                "closed_by": "parimala",
            },
        )

        check(
            "already LOST → duplicate close rejected",
            code == 409,
            f"HTTP {code}: {body}",
        )

        # ====================================================
        # 2. READY_FOR_OUTREACH → LOST
        # ====================================================

        label = "READY_FOR_OUTREACH_LOST"

        lead_id = create_test_lead(
            client,
            icp_id,
            label,
        )

        advance(
            client,
            lead_id,
            [
                "RESEARCHING",
                "QUALIFIED",
                "READY_FOR_OUTREACH",
            ],
            label,
        )

        close_lead(
            client,
            lead_id,
            status="LOST",
            reason="NO_RESPONSE",
            note="Regression test from outreach-ready.",
            label=label,
        )

        # ====================================================
        # 3. REPLIED → LOST / NOT_INTERESTED
        # ====================================================

        label = "REPLIED_NOT_INTERESTED"

        lead_id = create_test_lead(
            client,
            icp_id,
            label,
        )

        advance(
            client,
            lead_id,
            [
                "RESEARCHING",
                "QUALIFIED",
                "READY_FOR_OUTREACH",
                "CONTACTED",
                "REPLIED",
            ],
            label,
        )

        close_lead(
            client,
            lead_id,
            status="LOST",
            reason="NOT_INTERESTED",
            note="Regression test: prospect declined.",
            label=label,
        )

        # ====================================================
        # 4. QUALIFIED → DISQUALIFIED / WRONG_FIT
        # ====================================================

        label = "QUALIFIED_WRONG_FIT"

        lead_id = create_test_lead(
            client,
            icp_id,
            label,
        )

        advance(
            client,
            lead_id,
            [
                "RESEARCHING",
                "QUALIFIED",
            ],
            label,
        )

        close_lead(
            client,
            lead_id,
            status="DISQUALIFIED",
            reason="WRONG_FIT",
            note="Regression test: unsuitable fit.",
            label=label,
        )

        verify_event(
            lead_id,
            expected_status="DISQUALIFIED",
            expected_reason="WRONG_FIT",
            expected_note="Regression test: unsuitable fit.",
            label=label,
        )

        code, body = request(
            client,
            "PATCH",
            f"/api/leads/{lead_id}/status",
            json={
                "status": "DISQUALIFIED",
                "reason": "WRONG_FIT",
                "closed_by": "parimala",
            },
        )

        check(
            "already DISQUALIFIED → duplicate close rejected",
            code == 409,
            f"HTTP {code}: {body}",
        )

        # ====================================================
        # 5. CONVERTED cannot be closed
        # ====================================================

        label = "CONVERTED_TERMINAL"

        lead_id = create_test_lead(
            client,
            icp_id,
            label,
        )

        advance(
            client,
            lead_id,
            [
                "RESEARCHING",
                "QUALIFIED",
                "READY_FOR_OUTREACH",
                "CONTACTED",
                "REPLIED",
                "CONVERTED",
            ],
            label,
        )

        code, body = request(
            client,
            "PATCH",
            f"/api/leads/{lead_id}/status",
            json={
                "status": "LOST",
                "reason": "NO_RESPONSE",
                "note": "Should never succeed.",
                "closed_by": "parimala",
            },
        )

        check(
            "CONVERTED → LOST rejected",
            code == 409,
            f"HTTP {code}: {body}",
        )

        code, body = get_lead(
            client,
            lead_id,
        )

        check(
            "CONVERTED remains CONVERTED",
            (
                code == 200
                and body.get("status")
                == "CONVERTED"
            ),
            f"HTTP {code}: {body}",
        )

        # ====================================================
        # 6. Invalid closure requests
        # ====================================================

        label = "INVALID_CLOSURE"

        lead_id = create_test_lead(
            client,
            icp_id,
            label,
        )

        code, body = request(
            client,
            "PATCH",
            f"/api/leads/{lead_id}/status",
            json={
                "status": "LOST",
            },
        )

        check(
            "LOST without reason rejected",
            code == 409,
            f"HTTP {code}: {body}",
        )

        code, body = request(
            client,
            "PATCH",
            f"/api/leads/{lead_id}/status",
            json={
                "status": "LOST",
                "reason": "WRONG_FIT",
                "closed_by": "parimala",
            },
        )

        check(
            "reason/status mismatch rejected",
            code == 409,
            f"HTTP {code}: {body}",
        )

        # Finish the disposable Lead so no active test Lead
        # remains after validation.
        close_lead(
            client,
            lead_id,
            status="LOST",
            reason="OTHER",
            note="Regression cleanup closure.",
            label=label,
        )

    print()
    print("=" * 68)
    print("LorrySystem Lead Closure Regression")
    print("=" * 68)
    print(f"PASS: {PASS}")
    print(f"FAIL: {FAIL}")

    print()
    print("Created disposable regression records:")

    for label, item in created.items():
        print(
            f"{label}: "
            f"{item['company_name']} "
            f"(lead={item['lead_id']})"
        )

    print()

    if FAIL == 0:
        print("RESULT: PASSED")
        return 0

    print("RESULT: FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
