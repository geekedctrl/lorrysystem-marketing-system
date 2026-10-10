import os
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from .api_client import MarketingAPIError
from .workspace_context import request_auth, request_icps

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


class WorkspaceDashboardMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, api):
        super().__init__(app)
        self.api = api

    async def dispatch(self, request, call_next):
        path = request.url.path
        public = path in ("/login", "/invitation", "/health") or path.startswith(
            "/static/"
        )
        if public:
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
            return response
        token = request.session.get("auth_token")
        if not token:
            return RedirectResponse("/login", status_code=302)
        auth_token = request_auth.set({"token": token})
        icp_token = request_icps.set([])
        try:
            try:
                user = await self.api.get("/api/auth/me")
            except MarketingAPIError as exc:
                if exc.status_code == 401:
                    request.session.clear()
                    return RedirectResponse("/login", status_code=302)
                return page(
                    request,
                    "error.html",
                    title="Account service unavailable",
                    message="Please try again shortly. Your saved work is retained.",
                    status_code=503,
                )
            requested = request.session.get("workspace_id")
            selected = next(
                (w for w in user["workspaces"] if w["id"] == requested), None
            )
            if not requested and user["workspaces"]:
                selected = user["workspaces"][0]
                request.session["workspace_id"] = selected["id"]
            request.state.user = user
            request.state.workspace = selected
            request_auth.set(
                {"token": token, "workspace_id": selected["id"] if selected else None}
            )
            if (
                selected
                and request.method == "POST"
                and not path.startswith("/workspaces/")
                and path not in ("/logout", "/account/password")
            ):
                allowed = (
                    ("ADMIN", "REVIEWER")
                    if path.startswith("/approvals/") or (path.startswith("/campaign-proposals/") and path.endswith("/review"))
                    else ("ADMIN", "OPERATOR", "REVIEWER")
                    if path.startswith("/campaign-proposals/") or path.endswith("/campaign-proposals")
                    else ("ADMIN", "OPERATOR")
                )
                if selected["role"] not in allowed:
                    return page(
                        request,
                        "error.html",
                        title="Action unavailable",
                        message="Your workspace role does not allow this action. Ask an administrator if you need different access.",
                        status_code=403,
                    )
            if selected:
                try:
                    icps = await self.api.get("/api/icp-profiles")
                    request_icps.set(
                        [
                            {"id": i["id"], "label": i["name"], "code": i["code"]}
                            for i in icps
                        ]
                    )
                except MarketingAPIError:
                    return page(
                        request,
                        "error.html",
                        title="Workspace unavailable",
                        message="Please try again shortly. Your saved work is retained.",
                        status_code=503,
                    )
            elif path not in (
                "/workspaces",
                "/logout",
                "/account/password",
            ) and not path.startswith("/workspaces/"):
                return RedirectResponse("/workspaces", status_code=302)
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
            return response
        finally:
            request_auth.reset(auth_token)
            request_icps.reset(icp_token)


def csrf(request):
    if not request.session.get("csrf_token"):
        request.session["csrf_token"] = secrets.token_urlsafe(32)
    return request.session["csrf_token"]


def valid_csrf(request, value):
    return bool(
        value and secrets.compare_digest(value, request.session.get("csrf_token", ""))
    )


def page(request, template, status_code=200, **context):
    return templates.TemplateResponse(
        request=request,
        name=template,
        status_code=status_code,
        context={
            "csrf_token": csrf(request),
            "reviewer_identity": getattr(request.state, "user", {}).get("email", ""),
            "current_user": getattr(request.state, "user", None),
            "current_workspace": getattr(request.state, "workspace", None),
            **context,
        },
    )


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return page(request, "login.html")


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
):
    if not valid_csrf(request, csrf_token):
        return HTMLResponse("Invalid form token. Reload the page.", status_code=403)
    try:
        result = await request.app.state.api.post(
            "/api/auth/login",
            json={"email": email, "password": password},
            authenticated=False,
        )
    except MarketingAPIError as exc:
        return page(request, "login.html", error=exc.message)
    request.session.clear()
    request.session["auth_token"] = result["token"]
    return RedirectResponse("/dashboard", status_code=303)


@router.post("/logout")
async def logout(request: Request, csrf_token: str = Form(...)):
    if not valid_csrf(request, csrf_token):
        return HTMLResponse("Invalid form token.", status_code=403)
    try:
        await request.app.state.api.post("/api/auth/logout")
    except MarketingAPIError:
        pass
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/invitation", response_class=HTMLResponse)
async def invitation_page(request: Request, token: str = ""):
    return page(request, "invitation.html", token=token)


@router.post("/invitation")
async def accept_invitation(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
):
    if not valid_csrf(request, csrf_token):
        return HTMLResponse("Invalid form token.", status_code=403)
    try:
        await request.app.state.api.post(
            "/api/auth/invitations/accept",
            json={"token": token, "password": password},
            authenticated=False,
        )
    except MarketingAPIError as exc:
        return page(request, "invitation.html", token=token, error=exc.message)
    return RedirectResponse("/login", status_code=303)


@router.get("/workspaces", response_class=HTMLResponse)
async def workspaces(request: Request, message: str = ""):
    return await workspace_page(request, message=message)


async def workspace_page(
    request: Request, message: str = "", submitted: dict | None = None
):
    selected = request.state.workspace
    members, credentials, audit, products, icps = [], [], [], [], []
    discovery_config = {}
    automation_plan = {"configured": False, "profile": {}, "jobs": []}
    senders, suppressions = [], []
    if selected:
        try:
            automation_plan = await request.app.state.api.get("/api/automation/plan")
        except MarketingAPIError:
            pass
        try:
            senders = await request.app.state.api.get("/api/senders")
            suppressions = await request.app.state.api.get("/api/email-suppressions")
        except MarketingAPIError:
            pass
    if selected and selected["role"] == "ADMIN":
        api = request.app.state.api
        prefix = "/api/workspaces/" + selected["id"]
        members = await api.get(prefix + "/members")
        credentials = await api.get(prefix + "/credentials")
        audit = await api.get(prefix + "/audit")
        products = await api.get("/api/products")
        icps = await api.get("/api/icp-profiles")
        discovery_config = await api.get("/api/discovery/config")
    if submitted:
        automation_plan["profile"] = submitted["profile"]
        products = submitted["products"]
    return page(
        request,
        "workspaces.html",
        members=members,
        credentials=credentials,
        audit=audit,
        products=products,
        icps=icps,
        message=message,
        discovery_config=discovery_config,
        automation_plan=automation_plan,
        senders=senders,
        suppressions=suppressions,
    )


@router.get("/workspaces/automation-status")
async def automation_status(request: Request):
    try:
        result = await request.app.state.api.get("/api/automation/plan")
        return JSONResponse(
            {
                "state": result["state"],
                "enabled": result["enabled"],
                "worker_state": result.get("operations", {}).get("worker_state"),
                "jobs": [
                    {"id": j["id"], "status": j["status"], "stalled": j.get("stalled", False)} for j in result["jobs"]
                ],
            }
        )
    except MarketingAPIError as exc:
        return JSONResponse({"error": exc.message}, status_code=exc.status_code)


@router.post("/workspaces/switch")
async def switch(
    request: Request, workspace_id: str = Form(...), csrf_token: str = Form(...)
):
    if not valid_csrf(request, csrf_token):
        return HTMLResponse("Invalid form token.", status_code=403)
    if not any(w["id"] == workspace_id for w in request.state.user["workspaces"]):
        return HTMLResponse("Workspace access denied.", status_code=403)
    request.session["workspace_id"] = workspace_id
    return RedirectResponse("/dashboard", status_code=303)


@router.post("/workspaces/manage")
async def manage(request: Request):
    form = await request.form()
    if not valid_csrf(request, str(form.get("csrf_token", ""))):
        return HTMLResponse("Invalid form token.", status_code=403)
    action = form.get("action")
    section = {
        "create": "product",
        "invite": "team",
        "role": "team",
        "remove": "team",
        "activate-product": "product",
        "pause-product": "product",
        "resume-product": "product",
        "retry-automation": "product",
        "suppress-email": "operations",
    }.get(str(action), "integrations")
    selected = request.state.workspace
    prefix = "/api/workspaces/" + selected["id"] if selected else ""
    api = request.app.state.api
    # All authorization is checked again by the API, including malicious form actions.
    try:
        if action == "create":
            import re, secrets

            slug = (
                re.sub(r"[^a-z0-9]+", "-", str(form.get("name", "")).lower()).strip(
                    "-"
                )[:60]
                or "product"
            )
            result = await api.post(
                "/api/workspaces",
                json={
                    "name": form.get("name"),
                    "slug": slug + "-" + secrets.token_hex(3),
                },
            )
            request.session["workspace_id"] = result["id"]
        elif action == "invite":
            result = await api.post(
                prefix + "/invitations",
                json={"email": form.get("email"), "role": form.get("role")},
            )
            # Show a relative link; never trust Host when generating invitation URLs.
            return page(
                request,
                "workspace_secret.html",
                heading="Invitation created",
                secret=os.getenv("DASHBOARD_PUBLIC_URL", "").rstrip("/")
                + "/invitation#"
                + urlencode({"token": result["token"]}),
                invitation=True,
            )
        elif action == "credential":
            result = await api.post(
                prefix + "/credentials", json={"name": form.get("name")}
            )
            return page(
                request,
                "workspace_secret.html",
                heading="Automation credential created",
                secret=result["token"],
            )
        elif action == "shared-worker":
            result = await api.post(
                "/api/automation/workers", json={"name": form.get("name")}
            )
            return page(
                request,
                "workspace_secret.html",
                heading="Shared worker credential created",
                secret=result["token"],
                shared_worker=True,
            )
        elif action == "revoke":
            await api.request(
                "DELETE", prefix + "/credentials/" + str(form.get("credential_id"))
            )
        elif action == "role":
            await api.patch(
                prefix + "/members/" + str(form.get("user_id")),
                json={"role": form.get("role")},
            )
        elif action == "remove":
            await api.request("DELETE", prefix + "/members/" + str(form.get("user_id")))
        elif action == "discovery":
            await api.request(
                "PUT",
                "/api/discovery/config",
                json={
                    "webhook_url": str(form.get("webhook_url", "")),
                    "default_query": str(form.get("default_query", "")),
                    "enabled": form.get("enabled") == "on",
                },
            )
        elif action == "settings":
            await api.patch(
                prefix + "/settings",
                json={
                    "description": form.get("description", ""),
                    "brand_voice": form.get("brand_voice", ""),
                    "monthly_budget_usd": form.get("monthly_budget_usd", 50),
                },
            )
        elif action == "activate-product":
            names, descriptions, ids = (
                form.getlist("offering_name"),
                form.getlist("offering_description"),
                form.getlist("offering_id"),
            )
            if len(names) != len(descriptions) or len(names) != len(ids):
                return HTMLResponse("Invalid catalog form.", status_code=422)
            products = [
                {
                    "id": ids[i] or None,
                    "name": name.strip(),
                    "description": descriptions[i].strip(),
                }
                for i, name in enumerate(names)
                if name.strip()
            ]
            await api.post(
                "/api/automation/activate",
                json={
                    "product_type": form.get("product_type"),
                    "description": form.get("description"),
                    "target_customers": form.get("target_customers", ""),
                    "country_code": form.get("country_code", "MY").upper(),
                    "language": form.get("language", "English"),
                    "brand_voice": form.get(
                        "brand_voice", "Clear, professional and helpful"
                    ),
                    "daily_new_companies": int(form.get("daily_new_companies", 5)),
                    "products": products,
                },
            )
        elif action in ("pause-product", "resume-product"):
            await api.post(
                "/api/automation/"
                + ("pause" if action == "pause-product" else "resume"),
                json={},
            )
        elif action == "retry-automation":
            await api.post(
                "/api/automation/jobs/" + str(form.get("job_id")) + "/retry", json={}
            )
        elif action == "smtp-sender":
            body = {key: str(form.get(key, "")) for key in ("name","from_email","from_name","host","username")}
            try: body["port"] = int(str(form.get("port", "587")))
            except ValueError: raise MarketingAPIError(422,"SMTP port must be 465 or 587.")
            body["security"] = str(form.get("security", "STARTTLS"))
            body["enabled"] = form.get("enabled") == "on"
            if form.get("password"): body["password"] = str(form.get("password"))
            if form.get("sender_id"):
                await api.request("PUT", "/api/senders/"+str(form.get("sender_id")), json=body)
            else: await api.post("/api/senders", json=body)
        elif action == "verify-smtp":
            result = await api.post("/api/senders/"+str(form.get("sender_id"))+"/verify", json={})
            if not result["verified"]: raise MarketingAPIError(422,"SMTP verification failed. Check host, security and credentials. No email was sent.")
        elif action == "suppress-email":
            await api.post("/api/email-suppressions", json={"email":str(form.get("email", "")),"reason":str(form.get("reason", "OPT_OUT"))})
        elif action == "catalog-import":
            import json
            try:
                payload = json.loads(str(form.get("catalog_json", "")))
            except ValueError:
                return HTMLResponse("Catalog import must be valid JSON.", status_code=422)
            await api.post("/api/automation/catalog-import", json=payload)
        elif action in ("products", "icps"):
            import json

            try:
                rules = json.loads(str(form.get("qualification_rules") or "{}"))
            except ValueError:
                return RedirectResponse(
                    "/workspaces?"
                    + urlencode({"message": "Qualification rules must be valid JSON."}),
                    status_code=303,
                )
            await api.post(
                prefix + "/catalog/" + action,
                json={
                    "code": form.get("code"),
                    "name": form.get("name"),
                    "description": form.get("description"),
                    "qualification_rules": rules,
                },
            )
        else:
            return HTMLResponse("Unknown action.", status_code=400)
    except (ValueError, TypeError):
        return RedirectResponse(
            "/workspaces?"
            + urlencode({"message": "Check the product form values and try again."}),
            status_code=303,
        )
    except MarketingAPIError as exc:
        if action == "activate-product":
            submitted = {
                "profile": {
                    key: str(form.get(key, ""))
                    for key in (
                        "product_type",
                        "description",
                        "target_customers",
                        "country_code",
                        "language",
                        "brand_voice",
                        "daily_new_companies",
                    )
                },
                "products": [
                    {"id": ids[i], "name": name, "description": descriptions[i]}
                    for i, name in enumerate(names)
                ],
            }
            return await workspace_page(
                request, message=exc.message, submitted=submitted
            )
        return RedirectResponse(
            "/workspaces?" + urlencode({"message": exc.message, "section": section}),
            status_code=303,
        )
    return RedirectResponse(
        "/workspaces?" + urlencode({"section": section, "message": "Changes saved."}),
        status_code=303,
    )


@router.post("/account/password")
async def password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    csrf_token: str = Form(...),
):
    if not valid_csrf(request, csrf_token):
        return HTMLResponse("Invalid form token.", status_code=403)
    try:
        await request.app.state.api.post(
            "/api/auth/password",
            json={"current_password": current_password, "new_password": new_password},
        )
    except MarketingAPIError as exc:
        return RedirectResponse(
            "/workspaces?" + urlencode({"message": exc.message}), status_code=303
        )
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
