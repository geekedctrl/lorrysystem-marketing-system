from fastapi import HTTPException
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from app.auth import check_business_permission, resolve_principal
from app.workspace_context import current_principal


def install_api_key_security(app):
    @app.middleware("http")
    async def workspace_guard(request, call_next):
        path = request.url.path
        control = path.startswith("/api/auth/") or path == "/api/workspaces" or path.startswith("/api/workspaces/")
        if not (path == "/api" or path.startswith("/api/")) or control:
            response = await call_next(request)
            if path.startswith('/api/'):
                response.headers['Cache-Control'] = 'no-store'
            return response
        try:
            principal = await run_in_threadpool(resolve_principal, request)
            check_business_permission(principal, request)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        token = current_principal.set(principal)
        try:
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            return response
        finally:
            current_principal.reset(token)
