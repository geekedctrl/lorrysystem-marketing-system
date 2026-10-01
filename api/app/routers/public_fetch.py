
"""Authenticated public webpage fetching endpoint for F2."""

import hmac
import os
import threading

from fastapi import (
    APIRouter,
    Header,
    HTTPException,
)

from pydantic import BaseModel, Field

from app.services.public_fetch_guard import (
    FetchError,
    fetch_public,
)


router = APIRouter(
    tags=["Research"]
)

# Maximum two concurrent outbound fetches per API worker.
FETCH_SLOTS = threading.BoundedSemaphore(value=2)


# ============================================================
# Request Schema
# ============================================================

class PublicFetchRequest(BaseModel):

    url: str = Field(
        min_length=1,
        max_length=1500,
    )


# ============================================================
# Standard Failure Response
# ============================================================

def failed_response(
    url,
    reason,
    status=None,
):

    return {
        "url": url,
        "final_url": None,
        "http_status": status,
        "content_type": None,
        "redirect_count": 0,
        "bytes_read": 0,
        "truncated": False,

        "fetch_status": (
            "BLOCKED"
            if reason in (
                "ROBOTS_DISALLOWED",
                "HTTPS_DOWNGRADE_DENIED",
            )
            else "FAILED"
        ),

        "failure_reason": reason,
        "body": "",
    }


# ============================================================
# F2 Public Fetch Endpoint
# ============================================================

@router.post(
    "/api/research/fetch-public"
)
def fetch_public_research_page(

    payload: PublicFetchRequest,

    x_api_key: str | None = Header(
        default=None,
        alias="X-API-Key",
    ),

):

    # Reuse the existing Marketing API key.
    expected = os.environ.get(
        "MARKETING_API_KEY",
        "",
    )

    if not expected:

        raise HTTPException(
            status_code=503,
            detail="FETCH_AUTH_NOT_CONFIGURED",
        )

    if (
        not x_api_key
        or not hmac.compare_digest(
            x_api_key,
            expected,
        )
    ):

        raise HTTPException(
            status_code=401,
            detail="UNAUTHORIZED",
        )

    # Reject excessive concurrent outbound requests.
    if not FETCH_SLOTS.acquire(blocking=False):

        return failed_response(
            payload.url,
            "FETCH_CAPACITY_REACHED",
        )

    try:

        try:

            return fetch_public(
                payload.url
            )

        except FetchError as exc:

            return failed_response(
                payload.url,
                exc.reason,
                exc.status,
            )

        except Exception:

            # Do not expose internal network details,
            # environment values or tracebacks.
            return failed_response(
                payload.url,
                "FETCH_INTERNAL_ERROR",
            )

    finally:

        FETCH_SLOTS.release()
