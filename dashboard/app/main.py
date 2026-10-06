from __future__ import annotations

import asyncio
import os
import secrets
from datetime import datetime
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from .api_client import MarketingAPI, MarketingAPIError
from .config import Settings, icp_options
from .workspace_ui import WorkspaceDashboardMiddleware, router as workspace_router

from .import_helpers import (
    CSV_HEADERS,
    csv_template_text,
    country_to_code,
    delete_import,
    error_rows_csv,
    extract_business_card,
    load_import,
    match_company,
    parse_csv_bytes,
    save_import,
    validate_csv_rows,
)


settings = Settings.from_env()
api = MarketingAPI(settings)

app = FastAPI(
    title="LorrySystem MVP1 Dashboard",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.state.api = api
app.include_router(workspace_router)
app.add_middleware(WorkspaceDashboardMiddleware, api=api)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    same_site="lax",
    https_only=os.getenv("DASHBOARD_SECURE_COOKIES", "false").lower() == "true",
    max_age=43200,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


LEAD_STATUSES = [
    "DISCOVERED",
    "RESEARCHING",
    "QUALIFIED",
    "READY_FOR_OUTREACH",
    "CONTACTED",
    "REPLIED",
    "CONVERTED",
    "DISQUALIFIED",
    "LOST",
]
PRIORITIES = ["LOW", "MEDIUM", "HIGH"]

ACTIVE_LEAD_STATUSES = [
    "DISCOVERED",
    "RESEARCHING",
    "QUALIFIED",
    "READY_FOR_OUTREACH",
    "CONTACTED",
    "REPLIED",
]

CLOSED_LEAD_STATUSES = [
    "LOST",
    "DISQUALIFIED",
]

LEAD_VIEWS = {
    "active",
    "converted",
    "closed",
    "all",
}


CANDIDATE_REVIEWABLE_STATUSES = {
    "NEW",
    "READY_FOR_REVIEW",
    "NEEDS_REVIEW",
}

CANDIDATE_FILTERS = [
    "REVIEWABLE",
    "READY_FOR_REVIEW",
    "NEEDS_REVIEW",
    "ACCEPTED",
    "REJECTED",
    "DUPLICATE",
    "FAILED",
    "ALL",
]


def icp_label_map() -> dict[str, str]:
    return {
        item["id"]: item["label"]
        for item in icp_options()
    }


def split_lines(value: str | None) -> list[str]:
    if not value:
        return []
    return [
        line.strip()
        for line in value.splitlines()
        if line.strip()
    ]


async def enrich_candidates(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not candidates:
        return []

    details = await asyncio.gather(
        *[
            safe_get(
                f"/api/candidates/{candidate['id']}",
                candidate,
            )
            for candidate in candidates
        ]
    )

    labels = icp_label_map()
    enriched: list[dict[str, Any]] = []

    for candidate, detail in zip(candidates, details):
        item = dict(candidate)
        detail = detail if isinstance(detail, dict) else {}

        sources = detail.get("sources") or []
        item["source_count"] = len(sources)
        item["icp_label"] = labels.get(
            str(item.get("suggested_icp_profile_id")),
            str(item.get("suggested_icp_profile_id") or "—"),
        )

        location_parts = [
            item.get("city"),
            item.get("state"),
            item.get("country_code"),
        ]
        item["location"] = ", ".join(
            part
            for part in location_parts
            if part
        ) or "—"

        enriched.append(item)

    return enriched


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def verify_csrf(request: Request, token: str) -> bool:
    expected = request.session.get("csrf_token", "")
    return bool(
        expected
        and token
        and secrets.compare_digest(expected, token)
    )


def reviewer_identity(request: Request) -> str:
    return getattr(request.state, 'user', {}).get('email', '')


def render(
    request: Request,
    template: str,
    context: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
) -> HTMLResponse:
    payload = {
        "request": request,
        "csrf_token": csrf_token(request),
        "reviewer_identity": reviewer_identity(request),
        "current_user": getattr(request.state, "user", None),
        "current_workspace": getattr(request.state, "workspace", None),
    }
    if context:
        payload.update(context)
    return templates.TemplateResponse(
        template,
        payload,
        status_code=status_code,
    )


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def iso_date(value: str | None) -> str:
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%d %b %Y, %H:%M")
    except ValueError:
        return value


templates.env.filters["iso_date"] = iso_date


async def safe_get(path: str, default: Any) -> Any:
    try:
        return await api.get(path)
    except MarketingAPIError:
        return default


async def fetch_all(
    path: str,
    *,
    params: dict[str, Any] | None = None,
    page_size: int = 100,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    offset = 0
    seen_ids: set[str] = set()
    base_params = dict(params or {})

    while True:
        page = await api.get(
            path,
            params={
                **base_params,
                "limit": page_size,
                "offset": offset,
            },
        )
        if not isinstance(page, list):
            raise MarketingAPIError(
                502,
                f"Expected a list response from {path}.",
            )

        page_ids = {
            str(item.get("id"))
            for item in page
            if isinstance(item, dict) and item.get("id")
        }

        if offset > 0 and page and page_ids and page_ids.issubset(seen_ids):
            raise MarketingAPIError(
                503,
                "Marketing API pagination is not enabled yet. "
                "Apply the lead-import API enhancement first.",
            )

        results.extend(page)
        seen_ids.update(page_ids)

        if len(page) < page_size:
            break
        offset += page_size

    return results


async def fetch_all_active_leads() -> list[dict[str, Any]]:
    active_statuses = [
        "DISCOVERED",
        "RESEARCHING",
        "QUALIFIED",
        "READY_FOR_OUTREACH",
        "CONTACTED",
        "REPLIED",
    ]
    groups = await asyncio.gather(
        *[
            fetch_all("/api/leads", params={"status": status})
            for status in active_statuses
        ]
    )
    return [lead for group in groups for lead in group]


async def enrich_leads(
    leads: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    companies = await safe_get("/api/companies", [])
    contacts = await safe_get("/api/contacts", [])

    company_map = {item["id"]: item for item in companies}
    contact_map = {item["id"]: item for item in contacts}

    enriched = []
    for lead in leads:
        item = dict(lead)
        item["company"] = company_map.get(lead["company_id"])
        item["contact"] = contact_map.get(
            lead.get("primary_contact_id")
        )
        enriched.append(item)
    return enriched


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse("/dashboard", status_code=302)


@app.get("/health", response_class=JSONResponse)
async def dashboard_health() -> dict[str, str]:
    return {"status": "ok", "service": "lorrysystem-dashboard"}


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    error = None
    try:
        leads, approvals = await asyncio.gather(
            api.get("/api/leads", params={"limit": 100}),
            api.get("/api/approvals", params={"status": "PENDING"}),
        )
        leads = await enrich_leads(leads)

        draft_count = 0
        approved_count = 0
        recent_actions = []

        action_results = await asyncio.gather(
            *[
                safe_get(
                    f"/api/leads/{lead['id']}/actions",
                    [],
                )
                for lead in leads[:30]
            ]
        )

        for lead, actions in zip(leads[:30], action_results):
            for action in actions:
                action = dict(action)
                action["company"] = lead.get("company")
                recent_actions.append(action)
                if action.get("status") == "DRAFT":
                    draft_count += 1
                elif action.get("status") == "APPROVED":
                    approved_count += 1

        recent_actions.sort(
            key=lambda x: x.get("created_at", ""),
            reverse=True,
        )

        metrics = {
            "active_leads": sum(
                1
                for lead in leads
                if lead.get("status")
                not in {"CONVERTED", "DISQUALIFIED", "LOST"}
            ),
            "pending_approvals": len(approvals),
            "draft_actions": draft_count,
            "approved_actions": approved_count,
        }

        return render(
            request,
            "dashboard.html",
            {
                "metrics": metrics,
                "recent_leads": leads[:8],
                "pending_approvals": approvals[:5],
                "recent_actions": recent_actions[:6],
                "error": error,
            },
        )
    except MarketingAPIError as exc:
        return render(
            request,
            "dashboard.html",
            {
                "metrics": {
                    "active_leads": "—",
                    "pending_approvals": "—",
                    "draft_actions": "—",
                    "approved_actions": "—",
                },
                "recent_leads": [],
                "pending_approvals": [],
                "recent_actions": [],
                "error": exc.message,
            },
            status_code=503,
        )


@app.get("/leads", response_class=HTMLResponse)
async def leads_page(
    request: Request,
    view: str = "active",
    status: str | None = None,
    priority: str | None = None,
    q: str | None = None,
) -> HTMLResponse:

    selected_view = (
        view
        if view in LEAD_VIEWS
        else "active"
    )

    params: dict[str, Any] = {}

    if priority:
        params["priority"] = priority

    try:
        leads = await fetch_all(
            "/api/leads",
            params=params,
        )

        if selected_view == "active":
            allowed_statuses = ACTIVE_LEAD_STATUSES

        elif selected_view == "converted":
            allowed_statuses = ["CONVERTED"]

        elif selected_view == "closed":
            allowed_statuses = CLOSED_LEAD_STATUSES

        else:
            allowed_statuses = LEAD_STATUSES

        leads = [
            lead
            for lead in leads
            if lead.get("status") in allowed_statuses
        ]

        if status and status in allowed_statuses:
            leads = [
                lead
                for lead in leads
                if lead.get("status") == status
            ]

        leads = await enrich_leads(leads)

    except MarketingAPIError as exc:
        return render(
            request,
            "leads.html",
            {
                "leads": [],
                "statuses": (
                    ACTIVE_LEAD_STATUSES
                    if selected_view == "active"
                    else ["CONVERTED"]
                    if selected_view == "converted"
                    else CLOSED_LEAD_STATUSES
                    if selected_view == "closed"
                    else LEAD_STATUSES
                ),
                "priorities": PRIORITIES,
                "selected_view": selected_view,
                "selected_status": status or "",
                "selected_priority": priority or "",
                "query": q or "",
                "error": exc.message,
            },
            status_code=503,
        )

    if q:
        needle = q.lower().strip()

        leads = [
            lead
            for lead in leads
            if needle
            in " ".join(
                [
                    (lead.get("company") or {}).get(
                        "name",
                        "",
                    ),
                    (
                        (lead.get("company") or {}).get(
                            "domain"
                        )
                        or ""
                    ),
                    (
                        (lead.get("contact") or {}).get(
                            "full_name"
                        )
                        or ""
                    ),
                    (
                        (lead.get("contact") or {}).get(
                            "email"
                        )
                        or ""
                    ),
                ]
            ).lower()
        ]

    return render(
        request,
        "leads.html",
        {
            "leads": leads,
            "statuses": allowed_statuses,
            "priorities": PRIORITIES,
            "selected_view": selected_view,
            "selected_status": status or "",
            "selected_priority": priority or "",
            "query": q or "",
            "error": None,
        },
    )


@app.get("/leads/new", response_class=HTMLResponse)
async def new_lead_hub(
    request: Request,
) -> HTMLResponse:
    return render(
        request,
        "lead_new.html",
        {
            "error": None,
        },
    )


@app.get(
    "/leads/new/manual",
    response_class=HTMLResponse,
)
async def new_lead_manual_page(
    request: Request,
) -> HTMLResponse:
    try:
        companies = await fetch_all(
            "/api/companies"
        )

    except MarketingAPIError as exc:
        return render(
            request,
            "lead_manual.html",
            {
                "companies": [],
                "icps": icp_options(),
                "error": exc.message,
                "form": {},
            },
            status_code=503,
        )

    return render(
        request,
        "lead_manual.html",
        {
            "companies": companies,
            "icps": icp_options(),
            "error": None,
            "form": {},
        },
    )


@app.get("/ui/companies/{company_id}/contacts")
async def company_contacts(company_id: str) -> JSONResponse:
    try:
        contacts = await api.get(
            "/api/contacts",
            params={"company_id": company_id, "limit": 100},
        )
        return JSONResponse(contacts)
    except MarketingAPIError as exc:
        return JSONResponse(
            {"detail": exc.message},
            status_code=exc.status_code,
        )


@app.post("/leads/new")
async def create_lead(
    request: Request,
    csrf: str = Form(...),
    company_mode: str = Form(...),
    company_id: str = Form(""),
    company_name: str = Form(""),
    company_website_url: str = Form(""),
    company_domain: str = Form(""),
    company_industry: str = Form(""),
    company_country_code: str = Form(""),
    company_state: str = Form(""),
    company_city: str = Form(""),
    company_fleet_size: str = Form(""),
    contact_mode: str = Form("skip"),
    existing_contact_id: str = Form(""),
    contact_name: str = Form(""),
    contact_job_title: str = Form(""),
    contact_email: str = Form(""),
    contact_phone: str = Form(""),
    contact_linkedin_url: str = Form(""),
    icp_profile_id: str = Form(...),
    priority: str = Form("MEDIUM"),
):
    if not verify_csrf(request, csrf):
        return render(
            request,
            "error.html",
            {
                "title": "Invalid form token",
                "message": "Please refresh the page and try again.",
            },
            status_code=403,
        )

    if priority not in PRIORITIES:
        priority = "MEDIUM"

    if not any(
        item["id"] == icp_profile_id
        for item in icp_options()
    ):
        return render(
            request,
            "error.html",
            {
                "title": "ICP configuration error",
                "message": (
                    "The selected ICP is not configured on the "
                    "dashboard server."
                ),
            },
            status_code=422,
        )

    try:
        if company_mode == "new":
            fleet_size = clean(company_fleet_size)
            company_payload: dict[str, Any] = {
                "name": clean(company_name),
                "website_url": clean(company_website_url),
                "domain": clean(company_domain),
                "industry": clean(company_industry),
                "country_code": (
                    clean(company_country_code).upper()
                    if clean(company_country_code)
                    else None
                ),
                "state": clean(company_state),
                "city": clean(company_city),
                "fleet_size_estimate": (
                    int(fleet_size)
                    if fleet_size is not None
                    else None
                ),
                "source_type": "DASHBOARD_MANUAL",
                "metadata": {"entered_via": "mvp1_dashboard"},
            }
            if not company_payload["name"]:
                raise MarketingAPIError(
                    422,
                    "Company name is required.",
                )
            company = await api.post(
                "/api/companies",
                json=company_payload,
            )
            selected_company_id = company["id"]
        else:
            selected_company_id = clean(company_id)
            if not selected_company_id:
                raise MarketingAPIError(
                    422,
                    "Please select an existing company.",
                )

        primary_contact_id = None

        if contact_mode == "existing":
            primary_contact_id = clean(existing_contact_id)
            if not primary_contact_id:
                raise MarketingAPIError(
                    422,
                    "Please choose an existing contact.",
                )

        elif contact_mode == "new":
            if not clean(contact_name):
                raise MarketingAPIError(
                    422,
                    "Contact name is required when adding a contact.",
                )

            contact = await api.post(
                "/api/contacts",
                json={
                    "company_id": selected_company_id,
                    "full_name": clean(contact_name),
                    "job_title": clean(contact_job_title),
                    "email": clean(contact_email),
                    "phone": clean(contact_phone),
                    "linkedin_url": clean(contact_linkedin_url),
                    "is_primary": True,
                },
            )
            primary_contact_id = contact["id"]

        lead_payload = {
            "company_id": selected_company_id,
            "primary_contact_id": primary_contact_id,
            "icp_profile_id": icp_profile_id,
            "priority": priority,
        }

        lead = await api.post(
            "/api/leads",
            json=lead_payload,
        )

        return RedirectResponse(
            f"/leads/{lead['id']}?created=1",
            status_code=303,
        )

    except (ValueError, MarketingAPIError) as exc:
        message = (
            exc.message
            if isinstance(exc, MarketingAPIError)
            else "Fleet size must be a whole number."
        )
        try:
            companies = await api.get(
                "/api/companies",
                params={"limit": 100},
            )
        except MarketingAPIError:
            companies = []

        return render(
            request,
            "lead_manual.html",
            {
                "companies": companies,
                "icps": icp_options(),
                "error": message,
                "form": await request.form(),
            },
            status_code=422,
        )


@app.get("/leads/import", response_class=HTMLResponse)
async def import_leads_page(request: Request) -> HTMLResponse:
    return render(
        request,
        "lead_import.html",
        {
            "icps": icp_options(),
            "error": None,
        },
    )


@app.post("/leads/{lead_id}/close")
async def close_lead(
    request: Request,
    lead_id: str,
    csrf: str = Form(...),
    reason: str = Form(...),
    note: str = Form(""),
):
    if not verify_csrf(request, csrf):
        return RedirectResponse(
            f"/leads/{lead_id}?error=csrf",
            status_code=303,
        )

    reason = reason.strip().upper()

    reason_status_map = {
        "NO_RESPONSE": "LOST",
        "NOT_INTERESTED": "LOST",
        "OTHER": "LOST",
        "WRONG_FIT": "DISQUALIFIED",
        "DUPLICATE": "DISQUALIFIED",
    }

    new_status = reason_status_map.get(
        reason
    )

    if not new_status:
        return RedirectResponse(
            (
                f"/leads/{lead_id}"
                f"?error={quote('Invalid closure reason.')}"
            ),
            status_code=303,
        )

    try:
        await api.patch(
            f"/api/leads/{lead_id}/status",
            json={
                "status": new_status,
                "reason": reason,
                "note": clean(note),
                "closed_by": reviewer_identity(request),
            },
        )

        return RedirectResponse(
            f"/leads/{lead_id}?closed=1",
            status_code=303,
        )

    except MarketingAPIError as exc:
        return RedirectResponse(
            (
                f"/leads/{lead_id}"
                f"?error={quote(exc.message)}"
            ),
            status_code=303,
        )


@app.get("/leads/{lead_id}", response_class=HTMLResponse)
async def lead_detail(
    request: Request,
    lead_id: str,
    created: int = 0,
    closed: int = 0,
    error: str | None = None,
) -> HTMLResponse:
    try:
        lead = await api.get(f"/api/leads/{lead_id}")

        tasks = [
            api.get(f"/api/companies/{lead['company_id']}"),
            safe_get(f"/api/leads/{lead_id}/research", []),
            safe_get(f"/api/leads/{lead_id}/scores", []),
            safe_get(f"/api/leads/{lead_id}/product-matches", []),
            safe_get(f"/api/leads/{lead_id}/actions", []),
            safe_get("/api/products", []),
        ]

        if lead.get("primary_contact_id"):
            tasks.append(
                safe_get(
                    f"/api/contacts/{lead['primary_contact_id']}",
                    None,
                )
            )

        results = await asyncio.gather(*tasks)

        company = results[0]
        research = results[1]
        scores = results[2]
        matches = results[3]
        actions = results[4]
        products = results[5]
        contact = results[6] if len(results) > 6 else None

        product_map = {p["id"]: p for p in products}
        for match in matches:
            match["product"] = product_map.get(match["product_id"])

        research_details = []
        for item in research:
            detail = await safe_get(
                f"/api/research/{item['id']}",
                item,
            )
            research_details.append(detail)

        approvals_by_action = {}
        for action in actions:
            approvals_by_action[action["id"]] = await safe_get(
                f"/api/actions/{action['id']}/approvals",
                [],
            )

        return render(
            request,
            "lead_detail.html",
            {
                "lead": lead,
                "company": company,
                "contact": contact,
                "research": research_details,
                "scores": scores,
                "matches": matches,
                "actions": actions,
                "approvals_by_action": approvals_by_action,
                "created": bool(created),
                "closed": bool(closed),
                "error": error,
            },
        )

    except MarketingAPIError as exc:
        return render(
            request,
            "error.html",
            {
                "title": "Lead unavailable",
                "message": exc.message,
            },
            status_code=exc.status_code,
        )


@app.get(
    "/discovered-leads",
    response_class=HTMLResponse,
)
async def discovered_leads_page(
    request: Request,
    status: str = "REVIEWABLE",
    q: str | None = None,
) -> HTMLResponse:
    if status not in CANDIDATE_FILTERS:
        status = "REVIEWABLE"

    try:
        if status == "REVIEWABLE":
            groups = await asyncio.gather(
                *[
                    fetch_all(
                        "/api/candidates",
                        params={"status": candidate_status},
                    )
                    for candidate_status in (
                        "NEW",
                        "READY_FOR_REVIEW",
                        "NEEDS_REVIEW",
                    )
                ]
            )
            candidates = [
                candidate
                for group in groups
                for candidate in group
            ]
            candidates.sort(
                key=lambda item: item.get("created_at", ""),
                reverse=True,
            )
        elif status == "ALL":
            candidates = await fetch_all(
                "/api/candidates"
            )
        else:
            candidates = await fetch_all(
                "/api/candidates",
                params={"status": status},
            )

        if q:
            needle = q.lower().strip()
            candidates = [
                candidate
                for candidate in candidates
                if needle
                in " ".join(
                    [
                        candidate.get("company_name", ""),
                        candidate.get("domain", "") or "",
                        candidate.get("industry", "") or "",
                        candidate.get("city", "") or "",
                        candidate.get("state", "") or "",
                        candidate.get("contact_name", "") or "",
                        candidate.get("email", "") or "",
                    ]
                ).lower()
            ]

        candidates = await enrich_candidates(
            candidates
        )

        return render(
            request,
            "discovered_leads.html",
            {
                "candidates": candidates,
                "filters": CANDIDATE_FILTERS,
                "selected_status": status,
                "query": q or "",
                "error": None,
            },
        )

    except MarketingAPIError as exc:
        return render(
            request,
            "discovered_leads.html",
            {
                "candidates": [],
                "filters": CANDIDATE_FILTERS,
                "selected_status": status,
                "query": q or "",
                "error": exc.message,
            },
            status_code=503,
        )


@app.get(
    "/discovered-leads/{candidate_id}",
    response_class=HTMLResponse,
)
async def discovered_lead_detail(
    request: Request,
    candidate_id: str,
) -> HTMLResponse:
    try:
        candidate = await api.get(
            f"/api/candidates/{candidate_id}"
        )

        labels = icp_label_map()
        candidate["icp_label"] = labels.get(
            str(candidate.get("suggested_icp_profile_id")),
            str(candidate.get("suggested_icp_profile_id") or "—"),
        )

        return render(
            request,
            "discovered_lead_detail.html",
            {
                "candidate": candidate,
                "icps": icp_options(),
                "priorities": PRIORITIES,
                "reviewable": (
                    candidate.get("status")
                    in CANDIDATE_REVIEWABLE_STATUSES
                ),
                "editable": (
                    candidate.get("status")
                    in (
                        CANDIDATE_REVIEWABLE_STATUSES
                        | {"FAILED"}
                    )
                ),
                "error": None,
            },
        )

    except MarketingAPIError as exc:
        return render(
            request,
            "error.html",
            {
                "title": "Discovered lead unavailable",
                "message": exc.message,
            },
            status_code=exc.status_code,
        )


@app.post("/discovered-leads/{candidate_id}/edit")
async def edit_discovered_lead(
    request: Request,
    candidate_id: str,
    csrf: str = Form(...),
    company_name: str = Form(...),
    website_url: str = Form(""),
    domain: str = Form(""),
    industry: str = Form(""),
    country_code: str = Form(""),
    state: str = Form(""),
    city: str = Form(""),
    contact_name: str = Form(""),
    job_title: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    linkedin_url: str = Form(""),
    suggested_icp_profile_id: str = Form(...),
    icp_confidence: str = Form(...),
    icp_reasoning: str = Form(...),
    fleet_clues: str = Form(""),
    buying_signals: str = Form(""),
    source_summary: str = Form(""),
):
    if not verify_csrf(request, csrf):
        return RedirectResponse(
            f"/discovered-leads/{candidate_id}?error=csrf",
            status_code=303,
        )

    name = clean(company_name)
    icp_id = clean(suggested_icp_profile_id)
    reasoning = clean(icp_reasoning)

    if not name or not icp_id or not reasoning:
        return RedirectResponse(
            (
                f"/discovered-leads/{candidate_id}"
                f"?error={quote('Company name, ICP, and ICP reasoning are required.')}"
            ),
            status_code=303,
        )

    try:
        confidence = float(icp_confidence)
    except ValueError:
        confidence = -1.0

    if not 0.0 <= confidence <= 1.0:
        return RedirectResponse(
            (
                f"/discovered-leads/{candidate_id}"
                f"?error={quote('ICP confidence must be between 0.00 and 1.00.')}"
            ),
            status_code=303,
        )

    country = clean(country_code)
    payload = {
        "company_name": name,
        "website_url": clean(website_url),
        "domain": clean(domain),
        "industry": clean(industry),
        "country_code": country.upper() if country else None,
        "state": clean(state),
        "city": clean(city),
        "contact_name": clean(contact_name),
        "job_title": clean(job_title),
        "email": clean(email),
        "phone": clean(phone),
        "linkedin_url": clean(linkedin_url),
        "suggested_icp_profile_id": icp_id,
        "icp_confidence": confidence,
        "icp_reasoning": reasoning,
        "fleet_clues": split_lines(fleet_clues),
        "buying_signals": split_lines(buying_signals),
        "source_summary": clean(source_summary),
    }

    try:
        await api.patch(
            f"/api/candidates/{candidate_id}",
            json=payload,
        )
        return RedirectResponse(
            f"/discovered-leads/{candidate_id}?updated=1",
            status_code=303,
        )

    except MarketingAPIError as exc:
        return RedirectResponse(
            (
                f"/discovered-leads/{candidate_id}"
                f"?error={quote(exc.message)}"
            ),
            status_code=303,
        )


@app.post("/discovered-leads/{candidate_id}/accept")
async def accept_discovered_lead(
    request: Request,
    candidate_id: str,
    csrf: str = Form(...),
    priority: str = Form("MEDIUM"),
    icp_profile_id: str = Form(""),
    review_notes: str = Form(""),
):
    if not verify_csrf(request, csrf):
        return RedirectResponse(
            f"/discovered-leads/{candidate_id}?error=csrf",
            status_code=303,
        )

    if priority not in PRIORITIES:
        priority = "MEDIUM"

    payload: dict[str, Any] = {
        "reviewed_by": reviewer_identity(request),
        "priority": priority,
        "review_notes": clean(review_notes),
    }

    selected_icp = clean(icp_profile_id)
    if selected_icp:
        payload["icp_profile_id"] = selected_icp

    try:
        result = await api.post(
            f"/api/candidates/{candidate_id}/accept",
            json=payload,
        )

        lead_id = result.get("lead_id")
        if lead_id:
            suffix = (
                "?created=1"
                if result.get("outcome") == "ACCEPTED"
                else ""
            )
            return RedirectResponse(
                f"/leads/{lead_id}{suffix}",
                status_code=303,
            )

        return RedirectResponse(
            (
                f"/discovered-leads/{candidate_id}"
                f"?error={quote('Candidate decision completed but no Lead ID was returned.')}"
            ),
            status_code=303,
        )

    except MarketingAPIError as exc:
        return RedirectResponse(
            (
                f"/discovered-leads/{candidate_id}"
                f"?error={quote(exc.message)}"
            ),
            status_code=303,
        )


@app.post("/discovered-leads/{candidate_id}/reject")
async def reject_discovered_lead(
    request: Request,
    candidate_id: str,
    csrf: str = Form(...),
    review_notes: str = Form(...),
):
    if not verify_csrf(request, csrf):
        return RedirectResponse(
            f"/discovered-leads/{candidate_id}?error=csrf",
            status_code=303,
        )

    notes = clean(review_notes)
    if not notes:
        return RedirectResponse(
            (
                f"/discovered-leads/{candidate_id}"
                f"?error={quote('A rejection reason is required.')}"
            ),
            status_code=303,
        )

    try:
        await api.post(
            f"/api/candidates/{candidate_id}/reject",
            json={
                "reviewed_by": reviewer_identity(request),
                "review_notes": notes,
            },
        )

        return RedirectResponse(
            f"/discovered-leads/{candidate_id}?decision=rejected",
            status_code=303,
        )

    except MarketingAPIError as exc:
        return RedirectResponse(
            (
                f"/discovered-leads/{candidate_id}"
                f"?error={quote(exc.message)}"
            ),
            status_code=303,
        )

async def enriched_approvals(
    status: str | None = None,
) -> list[dict[str, Any]]:
    params = {"status": status} if status else None
    approvals = await api.get("/api/approvals", params=params)

    leads = await safe_get("/api/leads", [])
    companies = await safe_get("/api/companies", [])
    lead_map = {lead["id"]: lead for lead in leads}
    company_map = {company["id"]: company for company in companies}

    enriched = []
    for approval in approvals:
        item = dict(approval)
        snapshot = item.get("content_snapshot") or {}
        lead_id = snapshot.get("lead_id")
        lead = lead_map.get(lead_id)

        item["lead"] = lead
        item["company"] = (
            company_map.get(lead.get("company_id"))
            if lead
            else None
        )
        enriched.append(item)

    return enriched


@app.get("/approvals", response_class=HTMLResponse)
async def approvals_page(
    request: Request,
    status: str = "PENDING",
) -> HTMLResponse:
    allowed = {
        "PENDING",
        "APPROVED",
        "REJECTED",
        "CHANGES_REQUESTED",
        "ALL",
    }
    if status not in allowed:
        status = "PENDING"

    try:
        approvals = await enriched_approvals(
            None if status == "ALL" else status
        )
        return render(
            request,
            "approvals.html",
            {
                "approvals": approvals,
                "selected_status": status,
                "error": None,
            },
        )
    except MarketingAPIError as exc:
        return render(
            request,
            "approvals.html",
            {
                "approvals": [],
                "selected_status": status,
                "error": exc.message,
            },
            status_code=503,
        )


@app.get(
    "/approvals/{approval_id}",
    response_class=HTMLResponse,
)
async def approval_detail(
    request: Request,
    approval_id: str,
) -> HTMLResponse:
    try:
        approval = await api.get(
            f"/api/approvals/{approval_id}"
        )
        snapshot = approval.get("content_snapshot") or {}

        lead = None
        company = None
        if snapshot.get("lead_id"):
            lead = await safe_get(
                f"/api/leads/{snapshot['lead_id']}",
                None,
            )
            if lead:
                company = await safe_get(
                    f"/api/companies/{lead['company_id']}",
                    None,
                )

        return render(
            request,
            "approval_detail.html",
            {
                "approval": approval,
                "snapshot": snapshot,
                "lead": lead,
                "company": company,
                "error": None,
            },
        )
    except MarketingAPIError as exc:
        return render(
            request,
            "error.html",
            {
                "title": "Approval unavailable",
                "message": exc.message,
            },
            status_code=exc.status_code,
        )


@app.post("/approvals/{approval_id}/approve")
async def approve(
    request: Request,
    approval_id: str,
    csrf: str = Form(...),
    reviewer_notes: str = Form(""),
):
    if not verify_csrf(request, csrf):
        return RedirectResponse(
            f"/approvals/{approval_id}?error=csrf",
            status_code=303,
        )

    try:
        await api.patch(
            f"/api/approvals/{approval_id}/approve",
            json={
                "decided_by": reviewer_identity(request),
                "reviewer_notes": clean(reviewer_notes),
            },
        )
        return RedirectResponse(
            f"/approvals/{approval_id}?decision=approved",
            status_code=303,
        )
    except MarketingAPIError as exc:
        return RedirectResponse(
            f"/approvals/{approval_id}?error={quote(exc.message)}",
            status_code=303,
        )


@app.post("/approvals/{approval_id}/reject")
async def reject(
    request: Request,
    approval_id: str,
    csrf: str = Form(...),
    reviewer_notes: str = Form(...),
):
    if not verify_csrf(request, csrf):
        return RedirectResponse(
            f"/approvals/{approval_id}?error=csrf",
            status_code=303,
        )

    notes = clean(reviewer_notes)
    if not notes:
        return RedirectResponse(
            f"/approvals/{approval_id}?error={quote('Reviewer notes are required for rejection.')}",
            status_code=303,
        )

    try:
        await api.patch(
            f"/api/approvals/{approval_id}/reject",
            json={
                "decided_by": reviewer_identity(request),
                "reviewer_notes": notes,
            },
        )
        return RedirectResponse(
            f"/approvals/{approval_id}?decision=rejected",
            status_code=303,
        )
    except MarketingAPIError as exc:
        return RedirectResponse(
            f"/approvals/{approval_id}?error={quote(exc.message)}",
            status_code=303,
        )


@app.post("/approvals/{approval_id}/request-changes")
async def request_changes(
    request: Request,
    approval_id: str,
    csrf: str = Form(...),
    reviewer_notes: str = Form(...),
):
    if not verify_csrf(request, csrf):
        return RedirectResponse(
            f"/approvals/{approval_id}?error=csrf",
            status_code=303,
        )

    notes = clean(reviewer_notes)
    if not notes:
        return RedirectResponse(
            f"/approvals/{approval_id}?error={quote('Reviewer notes are required when requesting changes.')}",
            status_code=303,
        )

    try:
        await api.patch(
            f"/api/approvals/{approval_id}/request-changes",
            json={
                "decided_by": reviewer_identity(request),
                "reviewer_notes": notes,
            },
        )
        return RedirectResponse(
            f"/approvals/{approval_id}?decision=changes",
            status_code=303,
        )
    except MarketingAPIError as exc:
        return RedirectResponse(
            f"/approvals/{approval_id}?error={quote(exc.message)}",
            status_code=303,
        )


@app.get("/actions", response_class=HTMLResponse)
async def actions_page(
    request: Request,
    status: str | None = None,
    channel: str | None = None,
) -> HTMLResponse:
    try:
        leads = await api.get(
            "/api/leads",
            params={"limit": 100},
        )
        leads = await enrich_leads(leads)
        results = await asyncio.gather(
            *[
                safe_get(
                    f"/api/leads/{lead['id']}/actions",
                    [],
                )
                for lead in leads
            ]
        )

        actions = []
        for lead, lead_actions in zip(leads, results):
            for action in lead_actions:
                item = dict(action)
                item["company"] = lead.get("company")
                actions.append(item)

        if status:
            actions = [
                a for a in actions
                if a.get("status") == status
            ]
        if channel:
            actions = [
                a for a in actions
                if a.get("channel") == channel
            ]

        actions.sort(
            key=lambda x: x.get("created_at", ""),
            reverse=True,
        )

        return render(
            request,
            "actions.html",
            {
                "actions": actions,
                "selected_status": status or "",
                "selected_channel": channel or "",
                "error": None,
            },
        )
    except MarketingAPIError as exc:
        return render(
            request,
            "actions.html",
            {
                "actions": [],
                "selected_status": status or "",
                "selected_channel": channel or "",
                "error": exc.message,
            },
            status_code=503,
        )


@app.get("/system", response_class=HTMLResponse)
async def system_page(request: Request) -> HTMLResponse:
    api_status = "Offline"
    db_status = "Unknown"
    try:
        health = await api.get(
            "/health",
            authenticated=False,
        )
        if isinstance(health, dict) and health.get("status") == "ok":
            api_status = "Online"
    except MarketingAPIError:
        pass

    try:
        db = await api.get(
            "/health/db",
            authenticated=False,
        )
        if isinstance(db, dict):
            db_status = (
                "Reachable"
                if db.get("status") in {"ok", "healthy"}
                else "Error"
            )
        else:
            db_status = "Reachable"
    except MarketingAPIError:
        db_status = "Error"

    return render(
        request,
        "system.html",
        {
            "api_status": api_status,
            "db_status": db_status,
        },
    )


# ---------------------------------------------------------------------------
# MVP1 Lead Import: CSV + Business Card Smart Autofill
# ---------------------------------------------------------------------------


def icp_code_to_id() -> dict[str, str]:
    return {i['code']: i['id'] for i in icp_options()}


@app.get("/leads/import/csv/template")
async def csv_template() -> Response:
    return Response(
        content=csv_template_text(icp_options()[0]["code"] if icp_options() else ""),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                'attachment; filename="lorrysystem-lead-import-template.csv"'
            )
        },
    )


@app.post("/leads/import/csv/preview", response_class=HTMLResponse)
async def csv_preview(
    request: Request,
    csrf: str = Form(...),
    file: UploadFile = File(...),
) -> HTMLResponse:
    if not verify_csrf(request, csrf):
        return render(
            request,
            "error.html",
            {
                "title": "Invalid form token",
                "message": "Please refresh the page and try again.",
            },
            status_code=403,
        )

    if file.content_type not in {
        "text/csv",
        "application/csv",
        "application/vnd.ms-excel",
        "text/plain",
    }:
        return render(
            request,
            "lead_import.html",
            {
                "icps": icp_options(),
                "error": "Please upload a CSV file.",
            },
            status_code=422,
        )

    data = await file.read(5 * 1024 * 1024 + 1)
    if len(data) > 5 * 1024 * 1024:
        return render(
            request,
            "lead_import.html",
            {
                "icps": icp_options(),
                "error": "CSV files are limited to 5 MB.",
            },
            status_code=413,
        )

    try:
        parsed = parse_csv_bytes(data, max_rows=5000)
        companies, leads = await asyncio.gather(
            fetch_all("/api/companies"),
            fetch_all_active_leads(),
        )
        rows = validate_csv_rows(
            parsed,
            companies,
            leads,
            icp_code_to_id(),
        )
        token = save_import(rows)
    except ValueError as exc:
        return render(
            request,
            "lead_import.html",
            {
                "icps": icp_options(),
                "error": str(exc),
            },
            status_code=422,
        )
    except MarketingAPIError as exc:
        return render(
            request,
            "lead_import.html",
            {
                "icps": icp_options(),
                "error": exc.message,
            },
            status_code=503,
        )

    counts = {
        key: sum(1 for row in rows if row["result"] == key)
        for key in ["READY", "DUPLICATE", "NEEDS_REVIEW", "INVALID"]
    }

    return render(
        request,
        "csv_preview.html",
        {
            "rows": rows,
            "counts": counts,
            "import_token": token,
        },
    )


async def resolve_or_create_company_for_import(
    row: dict[str, Any],
) -> dict[str, Any]:
    if row.get("existing_company_id"):
        return await api.get(
            f"/api/companies/{row['existing_company_id']}"
        )

    return await api.post(
        "/api/companies",
        json={
            "name": clean(row.get("company_name")),
            "website_url": clean(row.get("website")),
            "domain": clean(row.get("domain")),
            "industry": clean(row.get("industry")),
            "country_code": clean(row.get("country_code")) or None,
            "state": clean(row.get("state")),
            "city": clean(row.get("city")),
            "source_type": "DASHBOARD_CSV_IMPORT",
            "metadata": {"entered_via": "mvp1_csv_import"},
        },
    )


async def resolve_or_create_contact_for_import(
    row: dict[str, Any],
    company_id: str,
) -> str | None:
    meaningful = any(
        clean(row.get(key))
        for key in [
            "contact_name",
            "job_title",
            "email",
            "phone",
            "linkedin_url",
        ]
    )
    if not meaningful:
        return None

    name = clean(row.get("contact_name"))

    contacts = await fetch_all(
        "/api/contacts",
        params={"company_id": company_id},
    )
    email = clean(row.get("email"))
    for contact in contacts:
        if email and clean(contact.get("email")):
            if contact["email"].lower() == email.lower():
                return contact["id"]
        if name and clean(contact.get("full_name")):
            if contact["full_name"].lower() == name.lower():
                return contact["id"]

    contact = await api.post(
        "/api/contacts",
        json={
            "company_id": company_id,
            "full_name": name,
            "job_title": clean(row.get("job_title")),
            "email": email,
            "phone": clean(row.get("phone")),
            "linkedin_url": clean(row.get("linkedin_url")),
            "is_primary": True,
        },
    )
    return contact["id"]


@app.get("/leads/import/csv/errors/{import_token}")
async def csv_error_rows_download(import_token: str) -> Response:
    try:
        rows = load_import(import_token)
    except ValueError as exc:
        return Response(
            content=str(exc),
            status_code=410,
            media_type="text/plain; charset=utf-8",
        )

    return Response(
        content=error_rows_csv(rows),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                'attachment; filename="lorrysystem-import-error-rows.csv"'
            )
        },
    )


@app.post("/leads/import/csv/commit", response_class=HTMLResponse)
async def csv_commit(
    request: Request,
    csrf: str = Form(...),
    import_token: str = Form(...),
) -> HTMLResponse:
    if not verify_csrf(request, csrf):
        return render(
            request,
            "error.html",
            {
                "title": "Invalid form token",
                "message": "Please refresh the page and try again.",
            },
            status_code=403,
        )

    try:
        rows = load_import(import_token)
    except ValueError as exc:
        return render(
            request,
            "error.html",
            {"title": "Import unavailable", "message": str(exc)},
            status_code=410,
        )

    imported = 0
    skipped_duplicates = sum(
        1 for row in rows if row.get("result") == "DUPLICATE"
    )
    skipped_review = sum(
        1 for row in rows if row.get("result") == "NEEDS_REVIEW"
    )
    invalid = sum(
        1 for row in rows if row.get("result") == "INVALID"
    )
    failures: list[dict[str, Any]] = []
    created_leads: list[dict[str, Any]] = []
    icps = icp_code_to_id()

    for row in rows:
        if row.get("result") != "READY":
            continue
        try:
            company = await resolve_or_create_company_for_import(row)
            contact_id = await resolve_or_create_contact_for_import(
                row,
                company["id"],
            )
            lead = await api.post(
                "/api/leads",
                json={
                    "company_id": company["id"],
                    "primary_contact_id": contact_id,
                    "icp_profile_id": icps[row["icp"]],
                    "priority": row.get("priority") or "MEDIUM",
                },
            )
            imported += 1
            created_leads.append(
                {
                    "id": lead["id"],
                    "company_name": company["name"],
                    "status": lead["status"],
                }
            )
        except (MarketingAPIError, KeyError, ValueError) as exc:
            message = (
                exc.message
                if isinstance(exc, MarketingAPIError)
                else str(exc)
            )
            failures.append(
                {
                    "row": row.get("_csv_row"),
                    "company": row.get("company_name"),
                    "message": message,
                }
            )

    delete_import(import_token)

    return render(
        request,
        "csv_result.html",
        {
            "imported": imported,
            "skipped_duplicates": skipped_duplicates,
            "skipped_review": skipped_review,
            "invalid": invalid,
            "failures": failures,
            "created_leads": created_leads,
        },
    )


@app.post("/leads/import/card/extract", response_class=HTMLResponse)
async def card_extract(
    request: Request,
    csrf: str = Form(...),
    file: UploadFile = File(...),
) -> HTMLResponse:
    if not verify_csrf(request, csrf):
        return render(
            request,
            "error.html",
            {
                "title": "Invalid form token",
                "message": "Please refresh the page and try again.",
            },
            status_code=403,
        )

    allowed = {
        "image/jpeg",
        "image/png",
        "image/webp",
    }
    if file.content_type not in allowed:
        return render(
            request,
            "lead_import.html",
            {
                "icps": icp_options(),
                "error": "Business cards must be JPG, PNG, or WEBP images.",
            },
            status_code=422,
        )

    data = await file.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        return render(
            request,
            "lead_import.html",
            {
                "icps": icp_options(),
                "error": "Business card images are limited to 10 MB.",
            },
            status_code=413,
        )

    warning = None
    try:
        extracted = await asyncio.to_thread(
            extract_business_card,
            data,
        )
    except Exception:
        extracted = {
            "raw_text": "",
            "company_name": "",
            "website": "",
            "domain": "",
            "industry": "",
            "country": "MY",
            "state": "",
            "city": "",
            "contact_name": "",
            "job_title": "",
            "email": "",
            "phone": "",
            "linkedin_url": "",
        }
        warning = (
            "Could not confidently read this card. "
            "Please enter the information manually."
        )

    try:
        companies = await fetch_all("/api/companies")
    except MarketingAPIError:
        companies = []
    pseudo_row = {
        "company_name": extracted.get("company_name", ""),
        "domain": extracted.get("domain", ""),
        "website": extracted.get("website", ""),
    }
    match_type, matched_company = match_company(
        pseudo_row,
        companies,
    )

    return render(
        request,
        "card_review.html",
        {
            "data": extracted,
            "warning": warning,
            "companies": companies,
            "match_type": match_type,
            "matched_company": matched_company,
            "icps": icp_options(),
        },
    )


@app.post("/leads/import/card/create")
async def card_create(
    request: Request,
    csrf: str = Form(...),
    company_mode: str = Form("new"),
    existing_company_id: str = Form(""),
    company_name: str = Form(""),
    website: str = Form(""),
    domain: str = Form(""),
    industry: str = Form(""),
    country: str = Form(""),
    state: str = Form(""),
    city: str = Form(""),
    contact_name: str = Form(""),
    job_title: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    linkedin_url: str = Form(""),
    icp_profile_id: str = Form(...),
    priority: str = Form("MEDIUM"),
):
    if not verify_csrf(request, csrf):
        return render(
            request,
            "error.html",
            {
                "title": "Invalid form token",
                "message": "Please refresh the page and try again.",
            },
            status_code=403,
        )

    if not clean(company_name) and company_mode != "existing":
        return render(
            request,
            "error.html",
            {
                "title": "Company required",
                "message": "Company name is required.",
            },
            status_code=422,
        )
    if not any(
        item["id"] == icp_profile_id
        for item in icp_options()
    ):
        return render(
            request,
            "error.html",
            {
                "title": "ICP required",
                "message": "Please select a valid ICP profile.",
            },
            status_code=422,
        )
    if priority not in PRIORITIES:
        priority = "MEDIUM"

    meaningful_contact = any(
        clean(value)
        for value in [contact_name, job_title, email, phone, linkedin_url]
    )
    try:
        if company_mode == "existing":
            company_id = clean(existing_company_id)
            if not company_id:
                raise MarketingAPIError(
                    422,
                    "Select the existing company to reuse.",
                )
            company = await api.get(f"/api/companies/{company_id}")
        else:
            company = await api.post(
                "/api/companies",
                json={
                    "name": clean(company_name),
                    "website_url": clean(website),
                    "domain": clean(domain),
                    "industry": clean(industry),
                    "country_code": (
                        country_to_code(clean(country))
                        if clean(country)
                        else None
                    ),
                    "state": clean(state),
                    "city": clean(city),
                    "source_type": "DASHBOARD_BUSINESS_CARD",
                    "metadata": {"entered_via": "mvp1_business_card"},
                },
            )

        primary_contact_id = None
        if meaningful_contact:
            contact = await api.post(
                "/api/contacts",
                json={
                    "company_id": company["id"],
                    "full_name": clean(contact_name),
                    "job_title": clean(job_title),
                    "email": clean(email),
                    "phone": clean(phone),
                    "linkedin_url": clean(linkedin_url),
                    "is_primary": True,
                },
            )
            primary_contact_id = contact["id"]

        lead = await api.post(
            "/api/leads",
            json={
                "company_id": company["id"],
                "primary_contact_id": primary_contact_id,
                "icp_profile_id": icp_profile_id,
                "priority": priority,
            },
        )
        return RedirectResponse(
            f"/leads/{lead['id']}?created=1",
            status_code=303,
        )
    except MarketingAPIError as exc:
        return render(
            request,
            "error.html",
            {
                "title": "Could not create lead",
                "message": exc.message,
            },
            status_code=exc.status_code,
        )
