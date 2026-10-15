"""Independent native dashboard BFF. Run from dashboard: uvicorn app.native:app.

Bearer credentials stay in server memory; the browser receives an opaque session ID.
Single-process local integration only: use a shared session store before scaling.
"""
import asyncio
import ipaddress
import json
import os
import re
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).parent
READ_ROUTES = re.compile(r"^(catalog|catalog/all|candidates|candidates/[\w-]+|leads|leads/page|leads/[\w-]+|leads/[\w-]+/preparation|preparation/[\w-]+|approvals|jobs|jobs/[\w-]+|operations|senders|deliveries|deliveries/[\w-]+|email-suppressions|profile|members|connections)$")
RUN_STATUSES = {"PREPARING", "NEEDS_REVIEW", "PENDING_APPROVAL", "APPROVED", "REJECTED", "CHANGES_REQUESTED", "FAILED", "STALE"}
WRITE_ROUTES = {
    "PUT": [(r"catalog", {"ADMIN"}), (r"profile", {"ADMIN"}), (r"automation/preferences", {"ADMIN"}), (r"provider-connections/(MODEL|SEARCH)", {"ADMIN"})],
    "PATCH": [(r"catalog/[\w-]+", {"ADMIN"}), (r"members/[\w-]+", {"ADMIN"})],
    "POST": [
        (r"candidates/[\w-]+/(accept|reject|retry)", {"ADMIN", "OPERATOR", "REVIEWER"}),
        (r"automation/(activate|pause|resume)", {"ADMIN"}),
        (r"discovery|leads|leads/[\w-]+/prepare|preparation/[\w-]+/(contact|retry-contact-search)|jobs/[\w-]+/retry", {"ADMIN", "OPERATOR"}),
        (r"approvals/[\w-]+/decision", {"ADMIN", "REVIEWER"}),
        (r"approvals/[\w-]+/revision", {"ADMIN", "OPERATOR"}),
        (r"senders", {"ADMIN"}),
        (r"senders/[\w-]+/verify", {"ADMIN"}),
        (r"deliveries", {"ADMIN", "OPERATOR"}),
        (r"deliveries/[\w-]+/(approve-send|retry)", {"ADMIN", "OPERATOR"}),
        (r"email-suppressions", {"ADMIN", "OPERATOR"}),
    ],
}


def safe_url(value):
    try:
        parsed = urlsplit(str(value))
        host = parsed.hostname or ""
        if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
            return None
        if host.lower() == "localhost" or host.lower().endswith((".local", ".localhost", ".internal")) or "." not in host:
            return None
        try:
            if not ipaddress.ip_address(host).is_global:
                return None
        except ValueError:
            pass
        return str(value)
    except ValueError:
        return None


def create_app(transport=None):
    app = FastAPI(title="Native Marketing Dashboard", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.sessions = {}
    app.state.transport = transport
    templates = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape())
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
    secure = os.getenv("DASHBOARD_SECURE_COOKIES", "false").lower() == "true"

    async def upstream(method, path, token=None, payload=None, params=None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            async with httpx.AsyncClient(base_url=os.getenv("NATIVE_API_BASE_URL", "http://127.0.0.1:8020"), transport=app.state.transport, timeout=20) as client:
                response = await client.request(method, path, headers=headers, json=payload, params=params)
            if response.status_code == 204:
                return 204, None
            return response.status_code, response.json()
        except (httpx.RequestError, ValueError):
            return 503, {"detail": "The service is unavailable. Please try again; your form is preserved."}

    def current(request):
        sid = request.cookies.get("native_session")
        session = app.state.sessions.get(sid)
        if session and session["expires"] > time.time():
            return session
        app.state.sessions.pop(sid, None)
        return None

    def check_csrf(request, session):
        return secrets.compare_digest(request.headers.get("x-csrf-token", ""), session["csrf"])

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        return response

    @app.get("/health")
    async def health():
        return {"status": "ok", "frontend": "native"}

    @app.get("/")
    async def root():
        return RedirectResponse("/dashboard", status_code=302)

    @app.get("/dashboard", response_class=HTMLResponse)
    async def shell():
        return templates.get_template("native.html").render()

    @app.post("/session/login")
    async def login(request: Request):
        # Require a same-origin custom header even before authentication.
        if request.headers.get("x-native-request") != "1":
            return JSONResponse({"detail": "Reload the sign-in page."}, 403)
        body = await request.json()
        status, result = await upstream("POST", "/auth/login", payload=body)
        if status >= 400:
            return JSONResponse(result, status)
        old = current(request)
        if old:
            await upstream("POST", "/auth/logout", old["token"])
        app.state.sessions.pop(request.cookies.get("native_session"), None)
        for key, value in list(app.state.sessions.items()):
            if value["expires"] <= time.time():
                app.state.sessions.pop(key, None)
        sid = secrets.token_urlsafe(32)
        app.state.sessions[sid] = {"token": result["token"], "csrf": secrets.token_urlsafe(32), "expires": time.time() + 43200, "lock": asyncio.Lock()}
        response = JSONResponse({"signed_in": True})
        response.set_cookie("native_session", sid, httponly=True, secure=secure, samesite="strict", max_age=43200)
        return response

    @app.get("/session")
    async def session_info(request: Request):
        session = current(request)
        if not session:
            return JSONResponse({"detail": "Sign in to continue."}, 401)
        status, workspaces = await upstream("GET", "/workspaces", session["token"])
        if status >= 400:
            if status == 401:
                app.state.sessions.pop(request.cookies.get("native_session"), None)
            return JSONResponse(workspaces, status)
        status, profile = await upstream("GET", "/auth/me", session["token"])
        if status >= 400:
            if status == 401:
                app.state.sessions.pop(request.cookies.get("native_session"), None)
            return JSONResponse(profile, status)
        # Explicit public projection: no upstream credentials are browser data.
        profile = {"id": profile["id"], "email": profile["email"], "expires_at": profile["expires_at"], "capabilities": {"create_workspace": bool(profile.get("capabilities", {}).get("create_workspace"))}}
        status, organizations = await upstream("GET", "/organizations", session["token"])
        if status >= 400:
            return JSONResponse(organizations, status)
        return {"csrf": session["csrf"], "workspaces": workspaces, "organizations": organizations, "organization_id": session.get("oid"), "workspace_id": session.get("wid"), "user": profile}

    @app.api_route("/settings/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def settings(request: Request, path: str):
        session = current(request)
        if not session:
            return JSONResponse({"detail": "Session expired."}, 401)
        allowed = ((request.method == "GET" and (path in {"organizations", "auth/sessions"} or re.fullmatch(r"organizations/[\w-]+/(workspaces|members)", path)))
                   or (request.method == "POST" and (path in {"organizations", "auth/password", "invitations/accept"} or re.fullmatch(r"organizations/[\w-]+/(workspaces|invitations)", path) or re.fullmatch(r"workspaces/[\w-]+/invitations", path)))
                   or (request.method == "PUT" and re.fullmatch(r"organizations/[\w-]+", path))
                   or (request.method == "PATCH" and (re.fullmatch(r"organizations/[\w-]+/members/[\w-]+", path) or re.fullmatch(r"organizations/[\w-]+/workspaces/[\w-]+/status", path)))
                   or (request.method == "DELETE" and path == "auth/sessions/other"))
        if not allowed:
            return JSONResponse({"detail": "This feature is not available."}, 404)
        if request.method != "GET" and not check_csrf(request, session):
            return JSONResponse({"detail": "Reload before submitting."}, 403)
        payload = None
        if request.method in {"POST", "PUT", "PATCH"}:
            try:
                payload = await request.json()
            except ValueError:
                return JSONResponse({"detail": "Check the submitted fields."}, 422)
        status, result = await upstream(request.method, f"/{path}", session["token"], payload)
        return JSONResponse(result, 200 if status == 204 else status)

    @app.post("/session/logout")
    async def logout(request: Request):
        session = current(request)
        if not session:
            return JSONResponse({"detail": "Session expired."}, 401)
        if not check_csrf(request, session):
            return JSONResponse({"detail": "Reload before submitting."}, 403)
        status, result = await upstream("POST", "/auth/logout", session["token"])
        if status not in (200, 204, 401):
            return JSONResponse(result, status)
        app.state.sessions.pop(request.cookies.get("native_session"), None)
        response = JSONResponse({"signed_in": False})
        response.delete_cookie("native_session")
        return response

    @app.post("/session/workspace")
    async def switch(request: Request):
        session = current(request)
        if not session:
            return JSONResponse({"detail": "Session expired."}, 401)
        if not check_csrf(request, session):
            return JSONResponse({"detail": "Reload before submitting."}, 403)
        async with session["lock"]:
            status, workspaces = await upstream("GET", "/workspaces", session["token"])
            if status >= 400:
                return JSONResponse(workspaces, status)
            body = await request.json()
            workspace = next((w for w in workspaces if w["id"] == body.get("workspace_id")), None)
            if not workspace:
                return JSONResponse({"detail": "You do not have access to this workspace."}, 403)
            session["wid"] = workspace["id"]
            session["oid"] = workspace.get("organization_id")
            session["csrf"] = secrets.token_urlsafe(32)
            return {"workspace": workspace, "csrf": session["csrf"]}

    @app.post("/session/organization")
    async def switch_organization(request: Request):
        session = current(request)
        if not session:
            return JSONResponse({"detail": "Session expired."}, 401)
        if not check_csrf(request, session):
            return JSONResponse({"detail": "Reload before submitting."}, 403)
        body = await request.json()
        async with session["lock"]:
            status, organizations = await upstream("GET", "/organizations", session["token"])
            if status >= 400:
                return JSONResponse(organizations, status)
            org = next((o for o in organizations if o["id"] == body.get("organization_id")), None)
            if not org:
                return JSONResponse({"detail": "You do not have access to this organization."}, 403)
            status, workspaces = await upstream("GET", "/workspaces", session["token"])
            if status >= 400:
                return JSONResponse(workspaces, status)
            selected = next((w for w in workspaces if w.get("organization_id") == org["id"]), None)
            session["oid"] = org["id"]
            session["wid"] = selected["id"] if selected else None
            session["csrf"] = secrets.token_urlsafe(32)
            return {"organization": org, "workspace": selected, "csrf": session["csrf"]}

    @app.api_route("/gateway/{wid}/{path:path}", methods=["GET", "POST", "PUT", "PATCH"])
    async def gateway(request: Request, wid: str, path: str):
        session = current(request)
        if not session:
            return JSONResponse({"detail": "Session expired. Sign in again."}, 401)
        async with session["lock"]:
            if wid != session.get("wid"):
                return JSONResponse({"detail": "Workspace changed. Refresh this page."}, 409)
            if request.method == "GET":
                if not READ_ROUTES.fullmatch(path):
                    return JSONResponse({"detail": "This feature is not available."}, 404)
            else:
                if not check_csrf(request, session):
                    return JSONResponse({"detail": "Workspace changed. Reload before submitting."}, 403)
                permission = next((roles for pattern, roles in WRITE_ROUTES.get(request.method, []) if re.fullmatch(pattern, path)), None)
                if permission is None:
                    return JSONResponse({"detail": "This action is not available."}, 404)
                status, workspaces = await upstream("GET", "/workspaces", session["token"])
                if status >= 400:
                    return JSONResponse(workspaces, status)
                workspace = next((w for w in workspaces if w["id"] == wid), {})
                if workspace.get("role") not in permission:
                    return JSONResponse({"detail": "Your workspace role does not permit this action."}, 403)
            params = None
            if request.query_params:
                if request.method != "GET" or path not in {"leads/page", "candidates", "deliveries"}:
                    return JSONResponse({"detail": "Query parameters are not supported for this route."}, 422)
                pairs = list(request.query_params.multi_items())
                params = dict(pairs)
                allowed = {"q", "status", "limit", "cursor"} if path == "leads/page" else ({"status", "limit", "offset"} if path == "candidates" else {"approval_id"})
                if len(pairs) != len(params) or set(params) - allowed:
                    return JSONResponse({"detail": "Unsupported lead filters."}, 422)
                try:
                    valid = (1 <= int(params.get("limit", "25")) <= 100)
                    if path == "leads/page":
                        valid = valid and len(params.get("q", "")) <= 200 and len(params.get("cursor", "")) <= 1500 and ("status" not in params or params["status"] in RUN_STATUSES)
                    elif path == "candidates":
                        valid = valid and 0 <= int(params.get("offset", "0")) <= 100000 and len(params.get("status", "")) <= 24
                    else:
                        valid = len(params.get("approval_id", "")) <= 36
                except ValueError:
                    valid = False
                if not valid:
                    return JSONResponse({"detail": "Check the search, status, page size or cursor."}, 422)
            payload = None
            if request.method != "GET":
                raw = await request.body()
                if raw:
                    try:
                        payload = json.loads(raw)
                    except ValueError:
                        return JSONResponse({"detail": "Check the submitted fields."}, 422)
            status, result = await upstream(request.method, f"/workspaces/{wid}/{path}", session["token"], payload, params)
            if status == 401:
                app.state.sessions.pop(request.cookies.get("native_session"), None)
            return JSONResponse(result, status if status != 204 else 200)

    return app


app = create_app()
