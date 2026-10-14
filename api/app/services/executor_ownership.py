"""Fail-closed preflight against the native PostgreSQL ownership authority."""
import json
import os
import urllib.error
import urllib.request
from uuid import UUID

from fastapi import HTTPException


def legacy_claim_allowed(workspace_id: UUID, capability: str) -> bool:
    base = os.environ.get("OWNERSHIP_AUTHORITY_URL", "").rstrip("/")
    token = os.environ.get("OWNERSHIP_PREFLIGHT_TOKEN", "")
    if not base or not token or capability not in {"SETUP", "DISCOVERY", "PREPARATION", "SENDING"}:
        raise HTTPException(503, "Executor ownership preflight unavailable")
    request = urllib.request.Request(
        f"{base}/internal/executor-ownership/{workspace_id}/{capability}/preflight",
        headers={"X-Ownership-Token": token},
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            result = json.load(response)
        if not isinstance(result.get("allow_new_legacy_claim"), bool):
            raise ValueError("Invalid ownership response")
        return result["allow_new_legacy_claim"]
    except (OSError, ValueError, KeyError, TypeError, urllib.error.HTTPError) as exc:
        raise HTTPException(503, "Executor ownership preflight unavailable") from exc


def require_legacy_claim(workspace_id: UUID, capability: str) -> None:
    if not legacy_claim_allowed(workspace_id, capability):
        raise HTTPException(409, "Capability is draining or owned by Python")
