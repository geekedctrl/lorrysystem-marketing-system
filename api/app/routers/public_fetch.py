
"""Authenticated public webpage fetching endpoint for F2."""

import threading

from fastapi import (
    APIRouter,
    HTTPException,
)

from pydantic import BaseModel, Field

from app.services.public_fetch_guard import (
    FetchError,
    fetch_public,
)
from app.workspace_context import current_principal


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

):

    # Business API middleware resolves the workspace credential and role.
    # Do not authenticate a second time with the old global key.
    if current_principal.get() is None:
        raise HTTPException(401, 'Authentication required')

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
