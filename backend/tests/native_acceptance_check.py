"""Actual HTTP/BFF/DB/worker acceptance; only external provider/evidence data is synthetic."""

import json
import os
import time
import uuid
from pathlib import Path
import httpx


def manifest():
    if os.getenv("APP_ENV") != "native-acceptance":
        raise RuntimeError("This runner is only for isolated native acceptance")
    return json.loads(Path("/fixtures/accounts.json").read_text())


def check(response, status=200):
    if response.status_code != status:
        raise AssertionError(
            f"{response.request.method} {response.request.url.path}: expected {status}, got {response.status_code}"
        )
    return response.json() if response.content else None


def until(read, predicate, label, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = read()
        if predicate(value):
            return value
        time.sleep(0.4)
    raise AssertionError("Timed out: " + label)


def login(client, account):
    value = check(client.post("/auth/login", json=account))
    return {"Authorization": "Bearer " + value["token"]}


def main():
    data = manifest()
    api = httpx.Client(
        base_url=os.getenv("NATIVE_API_URL", "http://backend-api:8000"), timeout=15
    )
    frontend = httpx.Client(
        base_url=os.getenv("NATIVE_FRONTEND_URL", "http://native-frontend:8080"),
        timeout=20,
    )
    check(api.get("/health"))
    check(frontend.get("/health"))
    headers = login(api, data["accounts"]["ADMIN"])
    assert not check(api.get("/auth/me", headers=headers))["capabilities"][
        "create_workspace"
    ]
    workspaces = check(api.get("/workspaces", headers=headers))
    assert {w["id"] for w in workspaces} == set(data["workspaces"])
    approval_ids = []
    for index, wid in enumerate(data["workspaces"]):
        prefix = f"/workspaces/{wid}"
        product = {
            "kind": "PRODUCT",
            "code": "OFFER",
            "name": "Invoice Assist" if index else "Transport Scheduling",
            "description": (
                "Accounting invoice processing and reconciliation"
                if index
                else "Commercial transport scheduling and delivery operations"
            ),
            "rules": {},
        }
        check(api.put(prefix + "/catalog", headers=headers, json=product), 201)
        activation = {
            "idempotency_key": "acceptance-setup-" + uuid.uuid4().hex,
            "product_description": product["description"],
            "batch_size": 1,
        }
        setup = check(
            api.post(prefix + "/automation/activate", headers=headers, json=activation),
            202,
        )
        until(
            lambda: check(
                api.get(prefix + "/jobs/" + setup["job_id"], headers=headers)
            ),
            lambda j: j["status"] == "COMPLETED",
            "product setup",
        )
        leads = until(
            lambda: check(api.get(prefix + "/leads", headers=headers)),
            bool,
            "native discovery",
        )
        lid = leads[0]["id"]
        lead = until(
            lambda: check(api.get(prefix + "/leads/" + lid, headers=headers)),
            lambda l: l["current_preparation"]
            and l["current_preparation"]["status"] == "PENDING_APPROVAL",
            "native preparation",
        )
        assert lead["current_preparation"]["results"]["SCORING"]["score"] == 85
        assert (
            lead["current_preparation"]["results"]["RESEARCH"]["industry"]["kind"]
            == "OBSERVED"
        )
        approvals = check(api.get(prefix + "/approvals", headers=headers))
        approval_ids.append(
            next(
                a["id"]
                for a in approvals
                if a["run_id"] == lead["current_preparation"]["id"]
            )
        )
        operations = check(api.get(prefix + "/operations", headers=headers))
        assert operations["provider_health"] and operations["recent_provider_usage"]
        assert all(
            u["estimated_microusd"] == 0 for u in operations["recent_provider_usage"]
        )
    # Browser-facing bridge uses actual native API; token never returns in its response.
    signed_in = check(
        frontend.post(
            "/session/login",
            headers={"X-Native-Request": "1"},
            json=data["accounts"]["ADMIN"],
        )
    )
    assert signed_in == {"signed_in": True}
    session = check(frontend.get("/session"))
    csrf = session["csrf"]
    switched = check(
        frontend.post(
            "/session/workspace",
            headers={"X-CSRF-Token": csrf},
            json={"workspace_id": data["workspaces"][0]},
        )
    )
    csrf = switched["csrf"]
    wid = data["workspaces"][0]
    prefix = f"/workspaces/{wid}"
    check(frontend.get(f"/gateway/{wid}/leads"))
    check(frontend.get(f'/gateway/{data["workspaces"][1]}/leads'), 409)
    check(
        frontend.post(
            f"/gateway/{wid}/discovery", json={"idempotency_key": uuid.uuid4().hex}
        ),
        403,
    )
    # Review gap and continuation use real source snapshots and actual stage jobs.
    contact = check(
        api.post(
            prefix + "/leads",
            headers=headers,
            json={
                "company_name": "Contact Review Haulage",
                "website": "https://contact-review.fixtures.example.org/",
            },
        ),
        201,
    )
    rid = check(
        api.post(
            prefix + f'/leads/{contact["id"]}/prepare',
            headers=headers,
            json={"idempotency_key": uuid.uuid4().hex},
        ),
        202,
    )["run_id"]
    run = until(
        lambda: check(api.get(prefix + "/preparation/" + rid, headers=headers)),
        lambda r: r["status"] == "NEEDS_REVIEW",
        "ambiguous contact review",
    )
    assert run["stop_reason"] == "SUPPORTED_CONTACT_REQUIRED"
    candidates = run["results"]["CONTACT_SEARCH"]["people"][0]["profile_candidates"]
    assert len(candidates) == 2
    check(
        api.post(
            prefix + f"/preparation/{rid}/contact",
            headers=headers,
            json={"person_index": 0, "profile_url": candidates[0]["url"]},
        ),
        202,
    )
    until(
        lambda: check(api.get(prefix + "/preparation/" + rid, headers=headers)),
        lambda r: r["status"] == "PENDING_APPROVAL",
        "contact continuation",
    )
    # Retry after a deterministic provider failure preserves old failed history.
    retry_lead = check(
        api.post(
            prefix + "/leads",
            headers=headers,
            json={
                "company_name": "Provider Failure Haulage",
                "website": "https://provider-failure.fixtures.example.org/",
            },
        ),
        201,
    )
    retry_rid = check(
        api.post(
            prefix + f'/leads/{retry_lead["id"]}/prepare',
            headers=headers,
            json={"idempotency_key": uuid.uuid4().hex},
        ),
        202,
    )["run_id"]
    until(
        lambda: check(api.get(prefix + "/preparation/" + retry_rid, headers=headers)),
        lambda r: r["status"] == "FAILED",
        "provider failure",
    )
    job = next(
        j
        for j in check(api.get(prefix + "/jobs", headers=headers))
        if j["run_id"] == retry_rid
    )
    check(api.post(prefix + "/automation/pause", headers=headers))
    check(api.post(prefix + f'/jobs/{job["id"]}/retry', headers=headers), 409)
    check(api.post(prefix + "/automation/resume", headers=headers))
    check(api.post(prefix + f'/jobs/{job["id"]}/retry', headers=headers), 202)
    until(
        lambda: check(api.get(prefix + "/preparation/" + retry_rid, headers=headers)),
        lambda r: r["status"] == "PENDING_APPROVAL",
        "explicit provider retry",
    )
    completed = check(api.get(prefix + "/jobs/" + job["id"], headers=headers))
    assert completed["status"] == "COMPLETED" and any(
        e.get("code") == "SYNTHETIC_PROVIDER_FAILURE" for e in completed["history"]
    )
    # Every role is checked against actual backend permissions, not only hidden controls.
    for role in ("OPERATOR", "REVIEWER", "VIEWER"):
        role_headers = login(api, data["accounts"][role])
        check(api.get(prefix + "/leads/page", headers=role_headers))
        check(api.post(prefix + "/automation/pause", headers=role_headers), 403)
        if role == "VIEWER":
            check(
                api.post(
                    prefix + f"/approvals/{approval_ids[0]}/decision",
                    headers=role_headers,
                    json={
                        "decision": "APPROVED",
                        "note": "Unauthorized synthetic decision",
                    },
                ),
                403,
            )
    outsider = login(api, data["accounts"]["OUTSIDER"])
    check(api.get(prefix + "/leads", headers=outsider), 404)
    check(api.get(prefix + f'/leads/{contact["id"]}', headers=outsider), 404)
    # Retain first approvals for the actual browser review. Manifest contains only synthetic IDs/passwords.
    Path("/fixtures/journey.json").write_text(
        json.dumps(
            {
                "workspaces": data["workspaces"],
                "approval_ids": approval_ids,
                "contact_lead_id": contact["id"],
            }
        )
    )
    api.close()
    frontend.close()
    print(
        "PASS: actual native API/BFF/DB/workers; two unrelated products, sourced industry, contact review/continuation, provider failure/retry, pause/resume, four roles and tenant isolation; no sends or paid providers"
    )


if __name__ == "__main__":
    main()
