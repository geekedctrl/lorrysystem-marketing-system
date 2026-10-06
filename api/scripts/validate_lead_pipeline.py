"""Full lead-preparation lifecycle and atomic workspace boundaries in disposable environments."""

import copy
import http.cookiejar
import json
import os
import re
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID
from sqlalchemy import select

sys.path.insert(0, "/app")
from app.auth import password_hash
from app.db.session import ControlSession, SessionLocal
from app.models.workspaces import User, Membership
from app.models.pipeline import PipelineRun
from app.models.catalog import Product
from app.models.companies import Contact
from app.models.leads import ProductMatch
from app.workspace_context import LORRYSYSTEM_WORKSPACE_ID

if os.getenv("APP_ENV") not in ("ci", "workspace-test"):
    raise SystemExit("Refusing to run outside disposable environments")
BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
DASHBOARD = os.getenv("DASHBOARD_BASE_URL", "http://workspace-test-dashboard:8080")


def call(method, path, data=None, headers=None, expected=200):
    request = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status, body = response.status, json.load(response)
    except urllib.error.HTTPError as error:
        status, body = error.code, json.load(error)
    assert (
        status == expected
    ), f'{method} {path}: {status}, expected {expected}; {body if status != expected else ""}'
    return body


suffix, password = secrets.token_hex(5), secrets.token_urlsafe(24)
email = f"pipeline-admin-{suffix}@example.test"
with ControlSession() as db:
    user = User(email=email, password_hash=password_hash(password), platform_admin=True)
    db.add(user)
    db.flush()
    user_id = user.id
    db.add(
        Membership(workspace_id=LORRYSYSTEM_WORKSPACE_ID, user_id=user.id, role="ADMIN")
    )
    db.commit()
human = {
    "Authorization": "Bearer "
    + call("POST", "/api/auth/login", {"email": email, "password": password})["token"]
}
fixtures = []
quote = "Acme Logistics operates 40 trucks across Malaysia. Jane Tan is Operations Manager at Acme Logistics. Public business email: jane@acme.com."
url = "https://acme.com/"
citation = {
    "source_url": url,
    "evidence_quote": "Acme Logistics operates 40 trucks across Malaysia.",
}
for label in ("Alpha", "Beta"):
    workspace = call(
        "POST",
        "/api/workspaces",
        {"name": f"Pipeline {label}", "slug": f"pipeline-{label.lower()}-{suffix}"},
        human,
        201,
    )["id"]
    headers = {**human, "X-Workspace-ID": workspace}
    key = call(
        "POST",
        f"/api/workspaces/{workspace}/credentials",
        {"name": "Stage worker"},
        headers,
        201,
    )["token"]
    service = {"X-API-Key": key, "X-Workspace-ID": workspace}
    icp = call(
        "POST",
        f"/api/workspaces/{workspace}/catalog/icps",
        {
            "code": "FLEET",
            "name": "Fleet operators",
            "description": "Public fleet operators",
        },
        headers,
        201,
    )["id"]
    product = call(
        "POST",
        f"/api/workspaces/{workspace}/catalog/products",
        {
            "code": "MAIN",
            "name": f"{label} fleet software",
            "description": "Fleet dispatch and operations software",
        },
        headers,
        201,
    )["id"]
    company = call(
        "POST",
        "/api/companies",
        {"name": "Acme Logistics", "website_url": url, "domain": "acme.com"},
        headers,
        201,
    )["id"]
    lead = call(
        "POST",
        "/api/leads",
        {"company_id": company, "icp_profile_id": icp},
        headers,
        201,
    )["id"]
    research = call("POST", f"/api/leads/{lead}/research", {}, headers, 201)["id"]
    call("PATCH", f"/api/research/{research}/start", {}, service)
    call(
        "POST",
        f"/api/research/{research}/sources",
        {"source_type": "WEBSITE", "url": url, "evidence": quote, "confidence": 90},
        service,
        201,
    )
    profile = "https://www.linkedin.com/in/jane-tan"
    profile_quote = "Jane Tan Operations Manager Acme Logistics"
    call(
        "POST",
        f"/api/research/{research}/sources",
        {
            "source_type": "SEARCH",
            "url": profile,
            "evidence": profile_quote,
            "confidence": 85,
        },
        service,
        201,
    )
    call(
        "PATCH",
        f"/api/research/{research}/complete",
        {
            "summary": "Acme operates a public fleet across Malaysia.",
            "confidence": 85,
            "company_facts": {
                "company_identity_verified": True,
                "facts": [
                    {
                        "category": "FLEET",
                        "fact": "Operates 40 trucks",
                        "evidence_quote": citation["evidence_quote"],
                        "source_urls": [url],
                        "confidence": 90,
                    }
                ],
                "people": [
                    {
                        "name": "Jane Tan",
                        "job_title": "Operations Manager",
                        "business_email": "jane@acme.com",
                        "evidence_quote": quote,
                        "source_urls": [url],
                        "professional_profiles": [
                            {
                                "platform": "LinkedIn",
                                "url": profile,
                                "evidence_quote": profile_quote,
                                "source_urls": [profile],
                                "confidence": 85,
                            }
                        ],
                    }
                ],
            },
        },
        service,
    )
    fixtures.append(
        {
            "workspace_id": workspace,
            "human": headers,
            "service": service,
            "company_id": company,
            "lead_id": lead,
            "research_id": research,
            "product_id": product,
        }
    )
a, b = fixtures
path = f"/api/leads/{a['lead_id']}"
review = {
    "research_id": a["research_id"],
    "person_index": 0,
    "linkedin_url": profile,
    "confirmed": True,
}
call("POST", path + "/contact-review", review, a["service"], 403)
call("POST", path + "/contact-review", {**review, "confirmed": False}, a["human"], 422)
call(
    "POST",
    path + "/contact-review",
    {**review, "research_id": b["research_id"]},
    a["human"],
    404,
)
call(
    "POST",
    path + "/contact-review",
    {**review, "linkedin_url": "https://linkedin.com/in/other"},
    a["human"],
    409,
)
contact = call("POST", path + "/contact-review", review, a["human"])
assert (
    contact["full_name"] == "Jane Tan"
    and contact["email"] == "jane@acme.com"
    and contact["linkedin_url"] == profile
)
assert call("POST", path + "/contact-review", review, a["human"])["id"] == contact["id"]
assert (
    len(call("GET", "/api/contacts?company_id=" + a["company_id"], headers=a["human"]))
    == 1
)
foreign = call(
    "POST",
    f"/api/leads/{b['lead_id']}/contact-review",
    {"research_id": b["research_id"], "person_index": 0, "confirmed": True},
    b["human"],
)
call(
    "POST",
    path + "/contact-review",
    {"contact_id": foreign["id"], "confirmed": True},
    a["human"],
    404,
)
call(
    "POST",
    path + "/qualify",
    {"note": "Public fleet operations fit our product."},
    a["human"],
    409,
)
print(
    "PASS reviewed sourced contact promotion, deduplication and foreign contact/profile rejection",
    flush=True,
)


def queue(stage, extra=None):
    return call(
        "POST", path + "/pipeline", {"stage": stage, **(extra or {})}, a["human"], 202
    )


def claim():
    return call("POST", "/api/pipeline/claim", headers=a["service"])


def finish(run, output, expected=200):
    return call(
        "PATCH",
        f"/api/pipeline/{run['id']}/complete",
        {"output": output},
        a["service"],
        expected,
    )


run = queue("SCORING")
call("POST", path + "/pipeline", {"stage": "SCORING"}, a["service"], 403)
call("POST", path + "/pipeline", {"stage": "SCORING"}, a["human"], 409)
call(
    "POST",
    path + "/contact-review",
    {"contact_id": contact["id"], "confirmed": True},
    a["human"],
    409,
)
with ThreadPoolExecutor(max_workers=2) as pool:
    claims = list(pool.map(lambda _: claim(), range(2)))
assert sum(job is not None for job in claims) == 1
run = next(job for job in claims if job)
call("GET", f"/api/pipeline/{run['id']}/context", headers=b["service"], expected=404)
call("PATCH", f"/api/pipeline/{run['id']}/complete", {"output": {}}, b["service"], 404)
ctx = call("GET", f"/api/pipeline/{run['id']}/context", headers=a["service"])
score = {
    "components": [
        {
            "criterion": r["criterion"],
            "max_points": r["max_points"],
            "points": r["max_points"] if r["criterion"] != "buying_signals" else 0,
            "rationale": (
                "Public fleet evidence supports this criterion."
                if r["criterion"] != "buying_signals"
                else "Buying intent has not been documented."
            ),
            "evidence": [citation] if r["criterion"] != "buying_signals" else [],
        }
        for r in ctx["rubric"]
    ],
    "rationale": "Documented fleet operations fit the workspace ICP. Buying intent remains unknown.",
    "gaps": ["Confirm buying intent and current tools."],
}
invalid = copy.deepcopy(score)
invalid["components"][0]["evidence"][0][
    "evidence_quote"
] = "Invented fleet count and nonexistent company details."
finish(run, invalid, 422)
assert call("GET", path + "/scores", headers=a["human"]) == []
finish(run, score)
finish(run, score)
assert len(call("GET", path + "/scores", headers=a["human"])) == 1
assert call("GET", path, headers=a["human"])["status"] == "RESEARCHING"
assert call("GET", path + "/pipeline-state", headers=a["human"])["scored"]
print(
    "PASS serialized workspace claim, exact evidence scoring and idempotent atomic score completion",
    flush=True,
)

call(
    "POST",
    path + "/qualify",
    {"note": "Public fleet operations fit our product."},
    a["service"],
    403,
)
matching = call(
    "POST",
    path + "/qualify",
    {"note": "Fleet operations align with our documented product offering."},
    a["human"],
    202,
)
matching = claim()
match = {
    "matches": [
        {
            "product_code": "MAIN",
            "fit_score": 85,
            "rationale": "Documented public fleet operations align with dispatch software.",
            "evidence": [citation],
        }
    ]
}
invalid = copy.deepcopy(match)
invalid["matches"].append({**invalid["matches"][0], "product_code": "FOREIGN"})
finish(matching, invalid, 422)
assert call("GET", path + "/product-matches", headers=a["human"]) == []
finish(matching, match)
assert call("GET", path + "/pipeline-state", headers=a["human"])[
    "draft_product_ids"
] == [a["product_id"]]
queue_args = {"product_id": a["product_id"], "channel": "EMAIL"}
call(
    "POST",
    path + "/pipeline",
    {"stage": "DRAFTING", "product_id": b["product_id"]},
    a["human"],
    409,
)
drafting = queue("DRAFTING", queue_args)
drafting = claim()
draft = {
    "subject": "A question about your fleet operations",
    "content": "Hi Jane, your public website mentions 40 trucks across Malaysia. Our fleet dispatch software may be relevant to your operations. Would a short conversation be useful?",
    "evidence": [citation],
}
finish(
    drafting,
    {**draft, "evidence": [{**citation, "source_url": "https://foreign.com/"}]},
    422,
)
assert call("GET", path + "/actions", headers=a["human"]) == []
result = finish(drafting, draft)["result"]
finish(drafting, draft)
actions = call("GET", path + "/actions", headers=a["human"])
assert len(actions) == 1 and actions[0]["status"] == "PENDING_APPROVAL"
assert (
    len(
        call("GET", f"/api/actions/{result['action_id']}/approvals", headers=a["human"])
    )
    == 1
)
call(
    "PATCH",
    f"/api/approvals/{result['approval_id']}/approve",
    {"decided_by": "worker"},
    a["service"],
    403,
)
call(
    "PATCH",
    f"/api/approvals/{result['approval_id']}/request-changes",
    {"decided_by": email, "reviewer_notes": "Make the invitation shorter."},
    a["human"],
)
call(
    "PATCH",
    f"/api/actions/{result['action_id']}",
    {"content": draft["content"] + " Thanks for considering."},
    a["human"],
)
approval = call(
    "POST", f"/api/actions/{result['action_id']}/submit", {}, a["human"], 201
)
call(
    "PATCH",
    f"/api/approvals/{approval['id']}/approve",
    {"decided_by": email},
    a["human"],
)
assert (
    call("GET", f"/api/actions/{result['action_id']}", headers=a["human"])["status"]
    == "APPROVED"
)
assert (
    len(
        call("GET", f"/api/actions/{result['action_id']}/approvals", headers=a["human"])
    )
    == 2
)
print(
    "PASS human qualification, catalog-only matches, draft/approval atomicity and revision approval history; nothing sent",
    flush=True,
)

# Catalog changes after queueing stop a paid model request and completion.
stale = queue("DRAFTING", {"product_id": a["product_id"], "channel": "LINKEDIN"})
stale = claim()
with SessionLocal(info={"workspace_id": UUID(a["workspace_id"])}) as db:
    product = db.get(Product, UUID(a["product_id"]))
    original = product.description
    product.description = "Changed capabilities"
    db.commit()
call("GET", f"/api/pipeline/{stale['id']}/context", headers=a["service"], expected=409)
finish(stale, draft, 409)
call(
    "PATCH",
    f"/api/pipeline/{stale['id']}/fail",
    {"reason": "CONTEXT_CHANGED"},
    a["service"],
)
with SessionLocal(info={"workspace_id": UUID(a["workspace_id"])}) as db:
    product = db.get(Product, UUID(a["product_id"]))
    product.description = original
    db.commit()
changed_match = queue("DRAFTING", queue_args)
changed_match = claim()
with SessionLocal(info={"workspace_id": UUID(a["workspace_id"])}) as db:
    match_row = db.scalar(
        select(ProductMatch).where(ProductMatch.lead_id == UUID(a["lead_id"]))
    )
    match_id, previous_fit = match_row.id, match_row.fit_score
    match_row.fit_score = 0
    db.commit()
call(
    "GET",
    f"/api/pipeline/{changed_match['id']}/context",
    headers=a["service"],
    expected=409,
)
call(
    "PATCH",
    f"/api/pipeline/{changed_match['id']}/fail",
    {"reason": "MATCH_CHANGED"},
    a["service"],
)
with SessionLocal(info={"workspace_id": UUID(a["workspace_id"])}) as db:
    db.get(ProductMatch, match_id).fit_score = previous_fit
    db.commit()
with SessionLocal(info={"workspace_id": UUID(a["workspace_id"])}) as db:
    row = db.get(Contact, UUID(contact["id"]))
    previous_email = row.email
    row.email = "changed-" + suffix + "@acme.com"
    db.commit()
assert not call("GET", path + "/pipeline-state", headers=a["human"])["contact_reviewed"]
call("POST", path + "/pipeline", {"stage": "SCORING"}, a["human"], 409)
with SessionLocal(info={"workspace_id": UUID(a["workspace_id"])}) as db:
    db.get(Contact, UUID(contact["id"])).email = previous_email
    db.commit()
timeout = queue("SCORING")
timeout = claim()
with SessionLocal(info={"workspace_id": UUID(a["workspace_id"])}) as db:
    row = db.get(PipelineRun, UUID(timeout["id"]))
    row.started_at = datetime.now(timezone.utc) - timedelta(minutes=31)
    db.commit()
assert claim() is None
assert (
    call("GET", path + "/pipeline", headers=a["human"])[0]["failure_reason"]
    == "WORKER_TIMEOUT"
)
print("PASS stale-context rejection and workspace timeout recovery", flush=True)

jar = http.cookiejar.CookieJar()
browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def page(path):
    with browser.open(DASHBOARD + path, timeout=30) as response:
        return response.read().decode()


def form(path, values):
    return browser.open(
        urllib.request.Request(
            DASHBOARD + path, data=urllib.parse.urlencode(values).encode()
        ),
        timeout=30,
    )


csrf = re.search(r'name="csrf_token" value="([^"]+)"', page("/login"))[1]
with form("/login", {"csrf_token": csrf, "email": email, "password": password}):
    pass
csrf = re.search(r'name="csrf_token" value="([^"]+)"', page("/workspaces"))[1]
with form(
    "/workspaces/switch", {"csrf_token": csrf, "workspace_id": a["workspace_id"]}
):
    pass
html = page("/leads/" + a["lead_id"])
for text in (
    "Lead preparation stages",
    "Contact reviewed",
    "ICP fit",
    "90/100",
    "Prepare outreach",
    "APPROVED",
):
    assert text in html, text
count = len(call("GET", path + "/pipeline", headers=a["human"]))
with form("/leads/" + a["lead_id"] + "/pipeline", {"csrf": "bad", "stage": "SCORING"}):
    pass
assert len(call("GET", path + "/pipeline", headers=a["human"])) == count
with ControlSession() as db:
    member = db.get(Membership, (UUID(a["workspace_id"]), user_id))
    member.role = "VIEWER"
    db.commit()
call(
    "POST",
    path + "/contact-review",
    {"contact_id": contact["id"], "confirmed": True},
    a["human"],
    403,
)
html = page("/leads/" + a["lead_id"])
assert (
    "Confirm primary contact</button>" not in html
    and "Prepare draft for approval</button>" not in html
)
try:
    form("/leads/" + a["lead_id"] + "/pipeline", {"csrf": csrf, "stage": "SCORING"})
    raise AssertionError("Viewer queued a stage")
except urllib.error.HTTPError as error:
    assert error.code == 403
with ControlSession() as db:
    member = db.get(Membership, (UUID(a["workspace_id"]), user_id))
    member.role = "ADMIN"
    db.commit()
print(
    "PASS dashboard stage controls, score criteria, CSRF and viewer boundaries",
    flush=True,
)
if os.getenv("EXPORT_PIPELINE_FIXTURE") == "true":
    Path("/tmp/pipeline-fixtures.json").write_text(
        json.dumps(
            {
                "fixtures": fixtures,
                "email": email,
                "password": password,
                "draft": draft,
                "score": score,
                "match": match,
            }
        ),
        encoding="utf-8",
    )
print("Lead pipeline regression PASSED", flush=True)
