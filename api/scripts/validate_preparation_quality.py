"""Six labelled synthetic companies, two unrelated products, real API and RLS.

No live search, model calls or email delivery. Provider outputs are controlled fixtures.
"""

import os, json, secrets, sys, urllib.request, urllib.error
from uuid import UUID
from sqlalchemy import select

sys.path.insert(0, "/app")
from app.auth import password_hash
from app.db.session import ControlSession
from app.models.workspaces import User, Membership
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
    assert status == expected, (method, path, status, body)
    return body


suffix = secrets.token_hex(5)
password = secrets.token_urlsafe(24)
email = f"quality-{suffix}@example.test"
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
        "POST", "/api/automation/workers", {"name": "Quality " + suffix}, human, 201
    )["token"]
}


def claim():
    return call("POST", "/api/automation/worker/claim", headers=worker)


def lease(job):
    return {
        **worker,
        "X-Workspace-ID": job["workspace_id"],
        "X-Automation-Lease": job["lease_token"],
    }


def finish(job):
    return call(
        "POST",
        "/api/automation/worker/finish",
        {"job_id": job["job_id"], "lease_token": job["lease_token"], "output": {}},
        worker,
    )


products = []
companies = {}
for label, capability, operations in [
    (
        "Fleet",
        "Dispatch scheduling and vehicle visibility",
        "operates 40 delivery trucks",
    ),
    (
        "Accounting",
        "Client bookkeeping and billing workflow",
        "provides bookkeeping to 80 business clients",
    ),
]:
    wid = call(
        "POST",
        "/api/workspaces",
        {
            "name": f"Quality {label} {suffix}",
            "slug": f"quality-{label.lower()}-{suffix}",
        },
        human,
        201,
    )["id"]
    headers = {**human, "X-Workspace-ID": wid}
    call(
        "POST",
        "/api/automation/activate",
        {
            "product_type": label + " operations software",
            "description": capability + " for professional business teams.",
            "daily_new_companies": 3,
            "products": [
                {
                    "name": label + " Pro",
                    "description": capability + " for professional business teams.",
                }
            ],
        },
        headers,
        202,
    )
    products.append(
        {
            "wid": wid,
            "headers": headers,
            "label": label,
            "capability": capability,
            "operations": operations,
        }
    )
for _ in products:
    job = claim()
    assert job["kind"] == "SETUP"
    product = next(p for p in products if p["wid"] == job["workspace_id"])
    call(
        "POST",
        "/api/automation/worker/finish",
        {
            "job_id": job["job_id"],
            "lease_token": job["lease_token"],
            "output": {
                "discovery_query": product["label"]
                + " professional companies Malaysia",
                "icps": [
                    {
                        "name": product["label"] + " operations teams",
                        "description": "Businesses whose operations need "
                        + product["capability"],
                    }
                ],
            },
        },
        worker,
    )
    product["catalog"] = call(
        "GET", "/api/workspace-context", headers=product["headers"]
    )
for _ in products:
    job = claim()
    assert job["kind"] == "DISCOVERY"
    p = next(p for p in products if p["wid"] == job["workspace_id"])
    for index, scenario in enumerate(
        ("documented_need", "existing_system", "missing_contact")
    ):
        domain = f"fixture-{p['label'].lower()}-{index}-{suffix}.com"
        url = "https://" + domain + "/"
        name = p["label"] + " Fixture " + str(index)
        quote = name + " " + p["operations"] + ". "
        quote += (
            "Our manual workflow causes recurring delays; we are evaluating operational software."
            if scenario == "documented_need"
            else "We already use operational software; no replacement plans or unmet needs are published."
        )
        if scenario != "missing_contact":
            quote += (
                " Jane Tan is Operations Manager. Public business email: jane@"
                + domain
                + "."
            )
        accepted = call(
            "POST",
            "/api/automation/candidates",
            {
                "company_name": name,
                "website_url": url,
                "domain": domain,
                "suggested_icp_profile_id": p["catalog"]["icps"][0]["id"],
                "icp_confidence": 0.85,
                "icp_reasoning": "Documented operations fit the selected product customer profile.",
                "source": {
                    "source_type": "COMPANY_WEBSITE",
                    "url": url,
                    "evidence": quote,
                },
            },
            lease(job),
        )
        assert accepted["outcome"] == "ACCEPTED"
        companies[accepted["lead_id"]] = {
            "product": p,
            "scenario": scenario,
            "url": url,
            "quote": quote,
            "domain": domain,
            "name": name,
        }
    finish(job)
for _ in companies:
    job = claim()
    assert job["kind"] == "RESEARCH"
    c = companies[job["input"]["lead_id"]]
    rid = job["input"]["research_id"]
    call(
        "POST",
        f"/api/research/{rid}/sources",
        {
            "source_type": "WEBSITE",
            "url": c["url"],
            "evidence": c["quote"],
            "confidence": 90,
        },
        lease(job),
        201,
    )
    people = (
        []
        if c["scenario"] == "missing_contact"
        else [
            {
                "name": "Jane Tan",
                "job_title": "Operations Manager",
                "business_email": "jane@" + c["domain"],
                "source_urls": [c["url"]],
                "evidence_quote": c["quote"],
                "confidence": 90,
            }
        ]
    )
    call(
        "PATCH",
        f"/api/research/{rid}/complete",
        {
            "summary": c["quote"],
            "confidence": 90,
            "company_facts": {
                "company_identity_verified": True,
                "people": people,
                "facts": [
                    {
                        "category": "SERVICES",
                        "fact": c["product"]["operations"],
                        "evidence_quote": c["quote"],
                        "source_urls": [c["url"]],
                        "confidence": 90,
                    }
                ],
            },
        },
        lease(job),
    )
    assert finish(job)["status"] == (
        "NEEDS_REVIEW" if c["scenario"] == "missing_contact" else "COMPLETED"
    )
for stage, count in [("SCORING", 4), ("MATCHING", 2), ("DRAFTING", 2)]:
    for _ in range(count):
        job = claim()
        assert job["kind"] == stage, (stage, job)
        c = companies[job["input"]["lead_id"]]
        rid = job["input"]["id"]
        context = call("GET", f"/api/pipeline/{rid}/context", headers=lease(job))
        evidence = [{"source_url": c["url"], "evidence_quote": c["quote"]}]
        if stage == "SCORING":
            output = {
                "components": [
                    {
                        "criterion": r["criterion"],
                        "max_points": r["max_points"],
                        "points": (
                            r["max_points"]
                            if c["scenario"] == "documented_need"
                            or r["criterion"] in ("icp_fit", "evidence_quality")
                            else 0
                        ),
                        "rationale": (
                            "Documented need supports this criterion."
                            if c["scenario"] == "documented_need"
                            else "Current system usage does not establish an unmet need or purchase intent."
                        ),
                        "evidence": (
                            evidence
                            if c["scenario"] == "documented_need"
                            or r["criterion"] in ("icp_fit", "evidence_quality")
                            else []
                        ),
                    }
                    for r in context["rubric"]
                ],
                "rationale": "Documented need and capability fit are assessed separately; existing usage alone is not buying intent.",
                "gaps": [],
            }
        elif stage == "MATCHING":
            output = {
                "matches": [
                    {
                        "product_code": c["product"]["catalog"]["products"][0]["code"],
                        "fit_score": 80,
                        "rationale": "Published workflow delays relate to the documented catalog capability; purchase decisions require review.",
                        "evidence": evidence,
                    }
                ]
            }
        else:
            output = {
                "subject": "A question about your "
                + c["product"]["label"].lower()
                + " workflow",
                "content": "Hi Jane, your website mentions "
                + c["product"]["operations"]
                + " and recurring manual workflow delays. Our "
                + c["product"]["label"]
                + " Pro offering supports "
                + c["product"]["capability"]
                + ". Would it be useful to compare your requirements in a short conversation?",
                "evidence": evidence,
            }
            bad = {
                **output,
                "content": "Our software will improve your business and cut your costs.",
            }
            call(
                "PATCH",
                f"/api/pipeline/{rid}/complete",
                {"output": bad},
                lease(job),
                422,
            )
        result = call(
            "PATCH", f"/api/pipeline/{rid}/complete", {"output": output}, lease(job)
        )
        if stage == "DRAFTING":
            c["draft"] = result["result"]["action_id"]
        finish(job)
assert claim() is None
for lead_id, c in companies.items():
    actions = call(
        "GET", f"/api/leads/{lead_id}/actions", headers=c["product"]["headers"]
    )
    assert len(actions) == (1 if c["scenario"] == "documented_need" else 0)
    assert all(a["status"] == "PENDING_APPROVAL" for a in actions)
    other = next(p for p in products if p is not c["product"])
    call("GET", f"/api/leads/{lead_id}", headers=other["headers"], expected=404)
print(
    "PASS six synthetic companies across fleet/accounting: documented need reaches pending approval; existing-system/no-need stops below threshold; missing contact stops for review; unsupported promises and cross-product access rejected. No live providers or sends."
)
