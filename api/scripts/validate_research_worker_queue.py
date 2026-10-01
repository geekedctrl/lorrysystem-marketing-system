from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from sqlalchemy import select

from app.db.session import get_db
from app.models.catalog import ICPProfile
from app.models.discovery import LeadCandidate
from app.models.leads import Lead, LeadResearch
from app.models.marketing import Event
from app.schemas.candidate import CandidateAccept


BASE_URL = "http://127.0.0.1:8000"

API_KEY = (
    os.getenv("MARKETING_API_KEY")
    or os.getenv("API_KEY")
    or os.getenv("LORRYSYSTEM_API_KEY")
    or ""
).strip()

PASS = 0
FAIL = 0


def check(
    name: str,
    condition: bool,
    detail: str = "",
):
    global PASS, FAIL

    if condition:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        print(f"[FAIL] {name}")
        if detail:
            print(f"       {detail}")


class Response:
    def __init__(
        self,
        status_code: int,
        body,
    ):
        self.status_code = status_code
        self.body = body

    def json(self):
        return self.body


def request(
    method: str,
    path: str,
    *,
    body: dict | None = None,
):
    headers = {
        "Accept": "application/json",
    }

    if API_KEY:
        headers["X-API-Key"] = API_KEY

    data = None

    if body is not None:
        data = json.dumps(
            body
        ).encode("utf-8")

        headers["Content-Type"] = (
            "application/json"
        )

    req = Request(
        BASE_URL + path,
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urlopen(
            req,
            timeout=30,
        ) as response:
            raw = response.read().decode(
                "utf-8"
            )

            payload = (
                json.loads(raw)
                if raw
                else None
            )

            return Response(
                response.status,
                payload,
            )

    except HTTPError as exc:
        raw = exc.read().decode(
            "utf-8"
        )

        try:
            payload = (
                json.loads(raw)
                if raw
                else None
            )
        except ValueError:
            payload = raw

        return Response(
            exc.code,
            payload,
        )


def first_active_icp(db):
    statement = (
        select(ICPProfile)
        .where(
            ICPProfile.active.is_(True)
        )
        .order_by(
            ICPProfile.created_at.asc()
        )
        .limit(1)
    )

    return db.scalar(statement)


def build_accept_payload(
    icp_id,
):
    fields = CandidateAccept.model_fields

    known_values = {
        "reviewed_by": (
            "research-worker-validator"
        ),
        "review_notes": (
            "Research Worker queue "
            "lifecycle regression."
        ),
        "priority": "MEDIUM",
        "icp_profile_id": icp_id,
    }

    payload = {}

    for name, value in known_values.items():
        if name in fields:
            payload[name] = value

    missing_required = []

    for name, field in fields.items():
        if (
            field.is_required()
            and name not in payload
        ):
            missing_required.append(name)

    if missing_required:
        raise RuntimeError(
            "Unhandled required CandidateAccept "
            f"fields: {missing_required}"
        )

    return payload


def event_for(
    db,
    *,
    event_type: str,
    entity_id,
):
    statement = (
        select(Event)
        .where(
            Event.event_type == event_type,
            Event.entity_id == entity_id,
        )
        .order_by(
            Event.created_at.desc()
        )
        .limit(1)
    )

    return db.scalar(statement)


def main():
    if not API_KEY:
        print(
            "ERROR: Marketing API key "
            "not found in environment."
        )
        return 1

    db = next(get_db())

    try:
        icp = first_active_icp(db)

        check(
            "Active ICP available",
            icp is not None,
        )

        if icp is None:
            return 1

        token = uuid4().hex[:12]

        candidate = LeadCandidate(
            status="READY_FOR_REVIEW",
            company_name=(
                f"Research Queue Validator {token}"
            ),
            normalized_name=(
                f"research queue validator {token}"
            ),
            website_url=(
                f"https://research-queue-{token}.example/"
            ),
            normalized_website=(
                f"https://research-queue-{token}.example"
            ),
            domain=(
                f"research-queue-{token}.example"
            ),
            industry="Logistics",
            country_code="MY",
            state="Selangor",
            city="Port Klang",
            contact_name=None,
            job_title=None,
            email=None,
            phone=None,
            linkedin_url=None,
            suggested_icp_profile_id=icp.id,
            icp_confidence=0.95,
            icp_reasoning=(
                "Disposable Research Worker "
                "queue validation candidate."
            ),
            fleet_clues=[
                "validator fixture"
            ],
            buying_signals=[],
            source_summary=(
                "Disposable validation record."
            ),
        )

        db.add(candidate)
        db.commit()
        db.refresh(candidate)

        candidate_id = candidate.id

        check(
            "Disposable Candidate created",
            candidate.status
            == "READY_FOR_REVIEW",
        )

        accept_payload = build_accept_payload(
            str(icp.id)
        )

        accepted = request(
            "POST",
            (
                f"/api/candidates/"
                f"{candidate_id}/accept"
            ),
            body=accept_payload,
        )

        check(
            "Candidate Accept HTTP 200",
            accepted.status_code == 200,
            str(accepted.body),
        )

        if accepted.status_code != 200:
            return 1

        result = accepted.json()

        check(
            "Candidate outcome ACCEPTED",
            result.get("outcome")
            == "ACCEPTED",
            str(result),
        )

        lead_id = result.get(
            "lead_id"
        )

        check(
            "Accepted Lead ID returned",
            bool(lead_id),
        )

        if not lead_id:
            return 1

        lead_response = request(
            "GET",
            f"/api/leads/{lead_id}",
        )

        check(
            "Accepted Lead readable",
            lead_response.status_code == 200,
            str(lead_response.body),
        )

        lead_data = (
            lead_response.json()
            if lead_response.status_code
            == 200
            else {}
        )

        check(
            "Lead remains DISCOVERED "
            "while Research is queued",
            lead_data.get("status")
            == "DISCOVERED",
            str(lead_data),
        )

        research_response = request(
            "GET",
            (
                f"/api/leads/"
                f"{lead_id}/research"
            ),
        )

        check(
            "Lead Research history readable",
            research_response.status_code
            == 200,
            str(research_response.body),
        )

        research_rows = (
            research_response.json()
            if research_response.status_code
            == 200
            else []
        )

        check(
            "Exactly one automatic "
            "Research run created",
            len(research_rows) == 1,
            str(research_rows),
        )

        if not research_rows:
            return 1

        research_id = research_rows[0].get(
            "id"
        )

        check(
            "Automatic Research is PENDING",
            research_rows[0].get(
                "research_status"
            )
            == "PENDING",
            str(research_rows[0]),
        )

        # ----------------------------------------------------
        # Make this disposable job older than any operational
        # PENDING job so /claim deterministically selects it.
        # ----------------------------------------------------

        research = db.get(
            LeadResearch,
            research_id,
        )

        research.created_at = datetime(
            2000,
            1,
            1,
            tzinfo=timezone.utc,
        )

        db.commit()

        queue_query = urlencode({
            "status": "PENDING",
            "limit": 100,
            "offset": 0,
        })

        pending = request(
            "GET",
            f"/api/research?{queue_query}",
        )

        check(
            "PENDING queue HTTP 200",
            pending.status_code == 200,
            str(pending.body),
        )

        pending_rows = (
            pending.json()
            if pending.status_code == 200
            else []
        )

        pending_ids = {
            row.get("id")
            for row in pending_rows
        }

        check(
            "Automatic Research appears "
            "in PENDING queue",
            research_id in pending_ids,
            str(pending_ids),
        )

        requested_event = event_for(
            db,
            event_type="research_requested",
            entity_id=research.id,
        )

        check(
            "research_requested Event exists",
            requested_event is not None,
        )

        if requested_event is not None:
            metadata = (
                requested_event.metadata_json
                or {}
            )

            check(
                "research_requested records "
                "PENDING",
                metadata.get(
                    "research_status"
                )
                == "PENDING",
                str(metadata),
            )

            check(
                "research_requested keeps "
                "Lead unstarted",
                metadata.get(
                    "lead_moved_to_researching"
                )
                is False,
                str(metadata),
            )

        claim = request(
            "POST",
            "/api/research/claim",
        )

        check(
            "Research claim HTTP 200",
            claim.status_code == 200,
            str(claim.body),
        )

        claimed = claim.json()

        check(
            "Claim returned Research",
            isinstance(
                claimed,
                dict,
            ),
            str(claimed),
        )

        if not isinstance(
            claimed,
            dict,
        ):
            return 1

        check(
            "Correct Research claimed",
            claimed.get("id")
            == research_id,
            str(claimed),
        )

        check(
            "Claimed Research is RUNNING",
            claimed.get(
                "research_status"
            )
            == "RUNNING",
            str(claimed),
        )

        check(
            "Claimed Research has "
            "started_at",
            bool(
                claimed.get(
                    "started_at"
                )
            ),
            str(claimed),
        )

        lead_after = request(
            "GET",
            f"/api/leads/{lead_id}",
        )

        lead_after_data = (
            lead_after.json()
            if lead_after.status_code == 200
            else {}
        )

        check(
            "Lead readable after claim",
            lead_after.status_code == 200,
            str(lead_after.body),
        )

        check(
            "Lead becomes RESEARCHING "
            "on claim",
            lead_after_data.get(
                "status"
            )
            == "RESEARCHING",
            str(lead_after_data),
        )

        research_after = request(
            "GET",
            f"/api/research/{research_id}",
        )

        research_after_data = (
            research_after.json()
            if research_after.status_code
            == 200
            else {}
        )

        check(
            "Research detail readable "
            "after claim",
            research_after.status_code
            == 200,
            str(research_after.body),
        )

        check(
            "Research detail = RUNNING",
            research_after_data.get(
                "research_status"
            )
            == "RUNNING",
            str(research_after_data),
        )

        pending_after = request(
            "GET",
            f"/api/research?{queue_query}",
        )

        pending_after_rows = (
            pending_after.json()
            if pending_after.status_code
            == 200
            else []
        )

        pending_after_ids = {
            row.get("id")
            for row in pending_after_rows
        }

        check(
            "Claimed Research removed "
            "from PENDING queue",
            research_id
            not in pending_after_ids,
            str(pending_after_ids),
        )

        db.expire_all()

        research_uuid = research.id

        started_event = event_for(
            db,
            event_type="research_started",
            entity_id=research_uuid,
        )

        check(
            "research_started Event exists",
            started_event is not None,
        )

        if started_event is not None:
            metadata = (
                started_event.metadata_json
                or {}
            )

            check(
                "research_started records "
                "atomic claim method",
                metadata.get(
                    "claim_method"
                )
                == "FOR_UPDATE_SKIP_LOCKED",
                str(metadata),
            )

            check(
                "research_started records "
                "Lead transition",
                metadata.get(
                    "lead_moved_to_researching"
                )
                is True,
                str(metadata),
            )

        lead_status_event = event_for(
            db,
            event_type="lead_status_changed",
            entity_id=research.lead_id,
        )

        check(
            "Lead status Event exists",
            lead_status_event is not None,
        )

        if lead_status_event is not None:
            metadata = (
                lead_status_event.metadata_json
                or {}
            )

            check(
                "Lead status Event "
                "DISCOVERED → RESEARCHING",
                (
                    metadata.get(
                        "previous_status"
                    )
                    == "DISCOVERED"
                    and metadata.get(
                        "new_status"
                    )
                    == "RESEARCHING"
                ),
                str(metadata),
            )

            check(
                "Lead status Event linked "
                "to Research",
                metadata.get(
                    "research_id"
                )
                == research_id,
                str(metadata),
            )

        print()
        print("=" * 68)
        print(
            "LorrySystem Research Worker "
            "Queue Lifecycle Regression"
        )
        print("=" * 68)
        print(f"PASS: {PASS}")
        print(f"FAIL: {FAIL}")
        print()
        print(
            "Disposable Candidate:",
            candidate_id,
        )
        print(
            "Disposable Lead:",
            lead_id,
        )
        print(
            "Disposable Research:",
            research_id,
        )
        print()

        if FAIL:
            print("RESULT: FAILED")
            return 1

        print("RESULT: PASSED")
        return 0

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
