"""Real API/RLS regression for shared workers; no network search or model spend."""

import json
import os
import secrets
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import UUID
from sqlalchemy import select

sys.path.insert(0, "/app")
from app.auth import password_hash
from app.db.session import ControlSession
from app.models.workspaces import User, Membership
from app.models.automation import AutomationJob, ProductAutomationPlan
from app.models.leads import LeadResearch, LeadScore
from app.models.pipeline import PipelineRun
from app.workspace_context import LORRYSYSTEM_WORKSPACE_ID

if os.getenv("APP_ENV") not in ("ci", "workspace-test"):
    raise SystemExit("Disposable environments only")
BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")


def call(method, path, data=None, headers=None, expected=200):
    request = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            status, body = response.status, json.load(response)
    except urllib.error.HTTPError as error:
        status, body = error.code, json.load(error)
    accepted_statuses = expected if isinstance(expected, tuple) else (expected,)
    assert (
        status in accepted_statuses
    ), f'{method} {path}: {status}, expected {expected}; {body if status not in accepted_statuses else ""}'
    return body


suffix = secrets.token_hex(5)
password = secrets.token_urlsafe(24)
email = f"automation-{suffix}@example.test"
with ControlSession() as db:
    user = User(email=email, password_hash=password_hash(password), platform_admin=True)
    db.add(user)
    db.flush()
    db.add(
        Membership(workspace_id=LORRYSYSTEM_WORKSPACE_ID, user_id=user.id, role="ADMIN")
    )
    db.commit()
human = {
    "Authorization": "Bearer "
    + call("POST", "/api/auth/login", {"email": email, "password": password})["token"],
    "X-Workspace-ID": str(LORRYSYSTEM_WORKSPACE_ID),
}
worker = {
    "X-API-Key": call(
        "POST",
        "/api/automation/workers",
        {"name": "Shared regression " + suffix},
        human,
        201,
    )["token"]
}
fixtures = []
for label, kind, capability in [
    ("Fleet", "Fleet management software", "Dispatch and vehicle operations"),
    ("Accounting", "Accounting practice software", "Client billing and bookkeeping"),
]:
    wid = call(
        "POST",
        "/api/workspaces",
        {"name": label + " " + suffix, "slug": label.lower() + "-auto-" + suffix},
        human,
        201,
    )["id"]
    headers = {**human, "X-Workspace-ID": wid}
    setup = {
        "product_type": kind,
        "description": capability + " software for business teams.",
        "target_customers": "Professional business teams",
        "products": [
            {
                "name": label + " Pro",
                "description": capability + " for professional teams.",
            }
        ],
    }
    call("POST", "/api/automation/activate", setup, headers, 202)
    fixtures.append({"wid": wid, "headers": headers, "setup": setup, "label": label})
call("GET", "/api/companies", headers=worker, expected=401)
call("POST", "/api/automation/activate", fixtures[0]["setup"], worker, 401)


def claim():
    return call("POST", "/api/automation/worker/claim", headers=worker)


def lease(job):
    return {
        **worker,
        "X-Workspace-ID": job["workspace_id"],
        "X-Automation-Lease": job["lease_token"],
    }


def finish(job, output=None, reason=None, expected=200):
    return call(
        "POST",
        "/api/automation/worker/finish",
        {
            "job_id": job["job_id"],
            "lease_token": job["lease_token"],
            "output": output or {},
            **({"failure_reason": reason} if reason else {}),
        },
        worker,
        expected,
    )


for _ in range(2):
    job = claim()
    assert job["kind"] == "SETUP"
    f = next(f for f in fixtures if f["wid"] == job["workspace_id"])
    ctx = call("GET", "/api/automation/job-context", headers=lease(job))
    assert (
        ctx["profile"]["product_type"] == f["setup"]["product_type"]
        and ctx["products"][0]["name"] == f["label"] + " Pro"
    )
    call("GET", "/api/companies", headers=lease(job), expected=403)
    call(
        "GET",
        "/api/automation/job-context",
        headers={
            **lease(job),
            "X-Workspace-ID": next(x["wid"] for x in fixtures if x is not f),
        },
        expected=403,
    )
    finish(job, {}, expected=422)
    finish(
        job,
        {
            "discovery_query": f["label"] + " businesses Malaysia",
            "icps": [
                {
                    "name": f["label"] + " customer teams",
                    "description": "Businesses needing " + f["setup"]["product_type"],
                }
            ],
        },
    )
    assert finish(job)["status"] == "COMPLETED"
    call("GET", "/api/workspace-context", headers=lease(job), expected=401)
    f["catalog"] = call("GET", "/api/workspace-context", headers=f["headers"])
for f in fixtures:
    legacy = {
        "X-API-Key": call(
            "POST",
            f"/api/workspaces/{f['wid']}/credentials",
            {"name": "Legacy stop regression"},
            f["headers"],
            201,
        )["token"],
        "X-Workspace-ID": f["wid"],
    }
    contract = call("GET", "/api/workspace-context", headers=legacy)["automation"]
    assert (
        contract["credential_kind"] == "workspace"
        and contract["human_candidate_review_required"] is False
        and "job_id" not in contract
    )
    assert call("POST", "/api/research/claim", headers=legacy) is None
    assert call("POST", "/api/pipeline/claim", headers=legacy) is None
print(
    "PASS admin form activation, unrelated catalogs, root credential isolation and exact workspace/job leases",
    flush=True,
)
discovery = []
with ThreadPoolExecutor(max_workers=2) as pool:
    claims = list(pool.map(lambda _: claim(), range(2)))
assert len({j["workspace_id"] for j in claims}) == 2 and all(
    j["kind"] == "DISCOVERY" for j in claims
)
assert claim() is None
for job in claims:
    f = next(f for f in fixtures if f["wid"] == job["workspace_id"])
    f["discovery"] = job
    quote = f"{f['label']} Customer provides professional business services. Jane Tan is Operations Manager at {f['label']} Customer. Public business email: jane@{f['label'].lower()}customer.com."
    url = "https://" + f["label"].lower() + "customer.com/"
    candidate = {
        "company_name": f["label"] + " Customer",
        "website_url": url,
        "domain": f["label"].lower() + "customer.com",
        "suggested_icp_profile_id": f["catalog"]["icps"][0]["id"],
        "icp_confidence": 0.85,
        "icp_reasoning": "Supported business services fit this product.",
        "source": {"source_type": "COMPANY_WEBSITE", "url": url, "evidence": quote},
    }
    call(
        "POST",
        "/api/automation/candidates",
        {**candidate, "icp_confidence": 0.5},
        lease(job),
        422,
    )
    candidate["suggested_icp_profile_id"] = next(
        x["catalog"]["icps"][0]["id"] for x in fixtures if x is not f
    )
    call("POST", "/api/automation/candidates", candidate, lease(job), 422)
    candidate["suggested_icp_profile_id"] = f["catalog"]["icps"][0]["id"]
    result = call("POST", "/api/automation/candidates", candidate, lease(job))
    assert result["outcome"] == "ACCEPTED"
    f["lead"] = result["lead_id"]
    f["quote"] = quote
    f["url"] = url
    assert (
        call("POST", "/api/automation/candidates", candidate, lease(job))["outcome"]
        != "ACCEPTED"
    )
    call(
        "POST",
        f"/api/leads/{f['lead']}/contact-review",
        {"confirmed": True},
        lease(job),
        403,
    )
    finish(job)
print(
    "PASS bounded sourced discovery, automatic acceptance, atomic research scheduling and duplicate rejection",
    flush=True,
)
for _ in range(2):
    job = claim()
    assert job["kind"] == "RESEARCH"
    f = next(f for f in fixtures if f["wid"] == job["workspace_id"])
    rid = job["input"]["research_id"]
    f["research"] = rid
    call("GET", f"/api/research/{rid}/context", headers=lease(job))
    call(
        "GET",
        "/api/research/00000000-0000-0000-0000-000000000001/context",
        headers=lease(job),
        expected=403,
    )
    call(
        "POST",
        f"/api/research/{rid}/sources",
        {
            "source_type": "WEBSITE",
            "url": f["url"],
            "evidence": f["quote"],
            "confidence": 85,
        },
        lease(job),
        201,
    )
    call(
        "PATCH",
        f"/api/research/{rid}/complete",
        {
            "summary": "A professional business with documented services and public business contact.",
            "confidence": 85,
            "company_facts": {
                "company_identity_verified": True,
                "facts": [
                    {
                        "category": "SERVICES",
                        "fact": "Provides professional business services",
                        "evidence_quote": f["quote"],
                        "source_urls": [f["url"]],
                        "confidence": 85,
                    }
                ],
                "people": [
                    {
                        "name": "Jane Tan",
                        "job_title": "Operations Manager",
                        "business_email": "jane@" + f["label"].lower() + "customer.com",
                        "source_urls": [f["url"]],
                        "evidence_quote": f["quote"],
                        "confidence": 85,
                    }
                ],
            },
        },
        lease(job),
    )
    finish(job)
for kind in ("SCORING", "MATCHING", "DRAFTING"):
    for _ in range(2):
        job = claim()
        assert job["kind"] == kind, (kind, job["kind"])
        f = next(f for f in fixtures if f["wid"] == job["workspace_id"])
        rid = job["input"]["id"]
        ctx = call("GET", f"/api/pipeline/{rid}/context", headers=lease(job))
        citation = {"source_url": f["url"], "evidence_quote": f["quote"]}
        if kind == "SCORING":
            output = {
                "components": [
                    {
                        "criterion": r["criterion"],
                        "max_points": r["max_points"],
                        "points": (
                            r["max_points"] if r["criterion"] != "buying_signals" else 0
                        ),
                        "rationale": (
                            "Public evidence supports business suitability."
                            if r["criterion"] != "buying_signals"
                            else "Intent remains unknown."
                        ),
                        "evidence": (
                            [citation] if r["criterion"] != "buying_signals" else []
                        ),
                    }
                    for r in ctx["rubric"]
                ],
                "rationale": "Documented operations fit the product. Buying intent remains unknown.",
                "gaps": ["Confirm buying intent."],
            }
        elif kind == "MATCHING":
            output = {
                "matches": [
                    {
                        "product_code": f["catalog"]["products"][0]["code"],
                        "fit_score": 85,
                        "rationale": "Documented operations align with the catalog capabilities.",
                        "evidence": [citation],
                    }
                ]
            }
        else:
            output = {
                "subject": "A question about your operations",
                "content": "Hi Jane, your public website describes your business services. Our software may be relevant to your operations. Would a short conversation be useful?",
                "evidence": [citation],
            }
        result = call(
            "PATCH", f"/api/pipeline/{rid}/complete", {"output": output}, lease(job)
        )
        if kind == "DRAFTING":
            call(
                "PATCH",
                f"/api/approvals/{result['result']['approval_id']}/approve",
                {"decided_by": "automation"},
                lease(job),
                403,
            )
        finish(job)
        finish(job)
for f in fixtures:
    actions = call("GET", f"/api/leads/{f['lead']}/actions", headers=f["headers"])
    assert len(actions) == 1 and actions[0]["status"] == "PENDING_APPROVAL"
    other = next(x for x in fixtures if x is not f)
    call("GET", f"/api/leads/{f['lead']}", headers=other["headers"], expected=404)
print(
    "PASS automatic supported contacts → scoring → qualification → matching → drafts pending human approval; nothing sent",
    flush=True,
)
# Pause immediately invalidates business leases; finish mirrors failures into native queues.
f = fixtures[0]
with ControlSession() as db:
    db.add(AutomationJob(workspace_id=UUID(f["wid"]), kind="SETUP"))
    db.commit()
job = claim()
assert job["kind"] == "SETUP"
call("POST", "/api/automation/pause", {}, f["headers"])
call("GET", "/api/automation/job-context", headers=lease(job), expected=403)
assert finish(job)["status"] == "FAILED"
call("POST", "/api/automation/jobs/" + job["job_id"] + "/retry", {}, f["headers"], 409)
call("POST", "/api/automation/resume", {}, f["headers"])
call("POST", "/api/automation/jobs/" + job["job_id"] + "/retry", {}, f["headers"], 202)
job = claim()
with ControlSession() as db:
    row = db.get(AutomationJob, UUID(job["job_id"]))
    row.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
call("GET", "/api/automation/job-context", headers=lease(job), expected=401)
finish(job, expected=409)
assert claim() is None
with ControlSession() as db:
    assert db.get(AutomationJob, UUID(job["job_id"])).status == "FAILED"
print(
    "PASS paused/expired leases and explicit retries without automatic spend loops",
    flush=True,
)
# Unsupported people remain for review, instead of turning a general mailbox into a contact.
with ControlSession() as db:
    db.add(
        AutomationJob(
            workspace_id=UUID(f["wid"]),
            kind="DISCOVERY",
            payload={"query": "Business services", "target_new_companies": 1},
        )
    )
    db.commit()
job = claim()
assert job["kind"] == "DISCOVERY"
no_contact = {
    "company_name": "Unknown Contact Company",
    "website_url": "https://unknowncontact.com/",
    "domain": "unknowncontact.com",
    "suggested_icp_profile_id": f["catalog"]["icps"][0]["id"],
    "icp_confidence": 0.85,
    "icp_reasoning": "Documented services fit the active customer profile.",
    "source": {
        "source_type": "COMPANY_WEBSITE",
        "url": "https://unknowncontact.com/",
        "evidence": "Unknown Contact Company provides professional business services in Malaysia.",
    },
}
lead = call("POST", "/api/automation/candidates", no_contact, lease(job))["lead_id"]
finish(job)
job = claim()
assert job["kind"] == "RESEARCH"
rid = job["input"]["research_id"]
call(
    "POST",
    f"/api/research/{rid}/sources",
    {
        "source_type": "WEBSITE",
        "url": "https://unknowncontact.com/",
        "evidence": no_contact["source"]["evidence"],
        "confidence": 85,
    },
    lease(job),
    201,
)
call(
    "PATCH",
    f"/api/research/{rid}/complete",
    {
        "summary": "A professional services company with no supported public named business contact.",
        "confidence": 85,
        "company_facts": {"company_identity_verified": True, "people": [], "facts": []},
    },
    lease(job),
)
assert finish(job)["status"] == "NEEDS_REVIEW"
assert call("GET", f"/api/leads/{lead}/actions", headers=f["headers"]) == []
call("POST", "/api/automation/jobs/" + job["job_id"] + "/retry", {}, f["headers"], 409)
assert claim() is None
# A second worker cannot finish the first worker's lease; revocation is immediate.
review_job = job
company = call("GET", f"/api/leads/{lead}", headers=f["headers"])["company_id"]
contact = call(
    "POST",
    "/api/contacts",
    {
        "company_id": company,
        "full_name": "Confirmed Business Contact",
        "job_title": "Operations Manager",
        "email": "confirmed@unknowncontact.com",
        "source_url": "https://unknowncontact.com/",
    },
    f["headers"],
    201,
)
call(
    "POST",
    f"/api/leads/{lead}/contact-review",
    {"contact_id": contact["id"], "confirmed": True},
    f["headers"],
)
with ControlSession() as db:
    db.add(
        AutomationJob(
            workspace_id=UUID(f["wid"]),
            kind="DISCOVERY",
            payload={"query": "Business services", "target_new_companies": 1},
        )
    )
    db.commit()
other_job = claim()
assert other_job["kind"] == "DISCOVERY"
assert (
    call(
        "POST",
        "/api/automation/jobs/" + review_job["job_id"] + "/retry",
        {},
        f["headers"],
        202,
    )["status"]
    == "COMPLETED"
)
finish(other_job)
scoring = claim()
assert scoring["kind"] == "SCORING"
assert finish(scoring, reason="VALIDATION_TEST_FAILURE")["status"] == "FAILED"
with ControlSession() as db:
    assert db.get(PipelineRun, UUID(scoring["input"]["id"])).status == "FAILED"
call(
    "POST",
    "/api/automation/jobs/" + scoring["job_id"] + "/retry",
    {},
    f["headers"],
    202,
)
scoring = claim()
rid = scoring["input"]["id"]
ctx = call("GET", f"/api/pipeline/{rid}/context", headers=lease(scoring))
output = {
    "components": [
        {
            "criterion": r["criterion"],
            "max_points": r["max_points"],
            "points": 0 if r["criterion"] == "buying_signals" else r["max_points"],
            "rationale": "Documented business services support this criterion.",
            "evidence": (
                []
                if r["criterion"] == "buying_signals"
                else [
                    {
                        "source_url": "https://unknowncontact.com/",
                        "evidence_quote": no_contact["source"]["evidence"],
                    }
                ]
            ),
        }
        for r in ctx["rubric"]
    ],
    "rationale": "Documented services align with the customer profile; buying intent is unknown.",
    "gaps": ["Confirm buying intent."],
}
result = call(
    "PATCH", f"/api/pipeline/{rid}/complete", {"output": output}, lease(scoring)
)
with ControlSession() as db:
    row = db.get(LeadScore, UUID(result["result"]["score_id"]))
    row.is_current = False
    db.commit()
assert finish(scoring)["result"]["outcome"] == "SCORING_CONTEXT_CHANGED"
assert claim() is None
assert call("GET", f"/api/leads/{lead}/actions", headers=f["headers"]) == []
# Concurrent HTTP items must not bypass the batch bound or lose accepted counts.
with ControlSession() as db:
    db.add(
        AutomationJob(
            workspace_id=UUID(f["wid"]),
            kind="DISCOVERY",
            payload={"query": "Business services", "target_new_companies": 1},
        )
    )
    db.commit()
batch = claim()
assert batch["kind"] == "DISCOVERY"


def bounded_candidate(label):
    url = "https://budget-" + label.lower() + ".com/"
    return {
        "company_name": "Concurrent " + label,
        "website_url": url,
        "domain": "budget-" + label.lower() + ".com",
        "suggested_icp_profile_id": f["catalog"]["icps"][0]["id"],
        "icp_confidence": 0.85,
        "icp_reasoning": "Documented services fit the active customer profile.",
        "source": {
            "source_type": "COMPANY_WEBSITE",
            "url": url,
            "evidence": "Concurrent "
            + label
            + " provides professional business services in Malaysia.",
        },
    }


with ThreadPoolExecutor(max_workers=2) as pool:
    results = list(
        pool.map(
            lambda label: call(
                "POST",
                "/api/automation/candidates",
                bounded_candidate(label),
                lease(batch),
                (200, 409),
            ),
            ["Alpha", "Beta"],
        )
    )
assert sum(r.get("outcome") == "ACCEPTED" for r in results) == 1
assert finish(batch)["result"]["accepted_leads"] == 1
batch_research = claim()
assert batch_research["kind"] == "RESEARCH"
finish(batch_research, reason="VALIDATION_TEST_FAILURE")
job = review_job
second = call(
    "POST",
    "/api/automation/workers",
    {"name": "Revocation regression " + suffix},
    human,
    201,
)
call(
    "POST",
    "/api/automation/worker/finish",
    {"job_id": job["job_id"], "lease_token": job["lease_token"]},
    {"X-API-Key": second["token"]},
    403,
)
call("DELETE", "/api/automation/workers/" + second["id"], headers=human)
call(
    "GET",
    "/api/automation/worker/health",
    headers={"X-API-Key": second["token"]},
    expected=401,
)
with ControlSession() as db:
    operator = User(
        email="operator-" + suffix + "@example.test",
        password_hash=password_hash(password),
    )
    db.add(operator)
    db.flush()
    db.add(
        Membership(workspace_id=UUID(f["wid"]), user_id=operator.id, role="OPERATOR")
    )
    db.commit()
op = {
    "Authorization": "Bearer "
    + call(
        "POST",
        "/api/auth/login",
        {"email": "operator-" + suffix + "@example.test", "password": password},
    )["token"],
    "X-Workspace-ID": f["wid"],
}
call("POST", "/api/automation/activate", f["setup"], op, 403)
call("POST", "/api/automation/pause", {}, op, 403)
call("POST", "/api/automation/workers", {"name": "Unauthorized"}, op, 403)
print(
    "PASS missing contact/manual continuation, native failures/stale score protection, worker ownership/revocation and admin-only activation",
    flush=True,
)
if os.getenv("EXPORT_TEST_LOGIN") == "true":
    from pathlib import Path

    Path("/tmp/product-automation-account.json").write_text(
        json.dumps(
            {
                "email": email,
                "password": password,
                "workspace_id": f["wid"],
                "worker_key": worker["X-API-Key"],
            }
        )
    )
