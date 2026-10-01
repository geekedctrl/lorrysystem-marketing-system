import os
import secrets

from fastapi import Request
from fastapi.responses import JSONResponse


def install_api_key_security(app):
    expected_key = os.getenv("MARKETING_API_KEY")

    if not expected_key:
        raise RuntimeError(
            "MARKETING_API_KEY is not configured"
        )

    @app.middleware("http")
    async def api_key_guard(
        request: Request,
        call_next,
    ):
        path = request.url.path

        protected = (
            path == "/api"
            or path.startswith("/api/")
        )

        if protected:
            provided_key = request.headers.get(
                "X-API-Key",
                "",
            )

            valid = (
                bool(provided_key)
                and secrets.compare_digest(
                    provided_key,
                    expected_key,
                )
            )

            if not valid:
                return JSONResponse(
                    status_code=401,
                    content={
                        "detail":
                        "Invalid or missing API key"
                    },
                )

        return await call_next(request)
