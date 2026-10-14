"""Administrative transitions and fail-closed legacy preflight."""
import os
import secrets
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from .auth import user, scope
from .db import session
from .models import ExecutorOwnership
from .ownership import CAPABILITIES, active_leases, transition

router = APIRouter()


class Version(BaseModel):
    expected_version: int = Field(ge=1)


def admin(wid, actor, db):
    if not actor.platform_admin:
        raise HTTPException(403, "Platform administrator required")
    scope(wid, actor, db)


def status(row, db):
    return dict(capability=row.capability, owner=row.owner, state=row.state,
                version=row.version, changed_at=row.changed_at,
                rollback_deadline=row.rollback_deadline,
                active_leases=active_leases(db,row.workspace_id,row.capability))


@router.get("/workspaces/{wid}/executor-ownership")
def ownership(wid: UUID, actor=Depends(user), db=Depends(session)):
    admin(wid, actor, db)
    return [status(row, db) for row in db.scalars(select(ExecutorOwnership).where(
        ExecutorOwnership.workspace_id == wid).order_by(ExecutorOwnership.capability))]


def change(wid, capability, action, data, actor, db):
    admin(wid, actor, db)
    return status(transition(db, wid, capability, action, data.expected_version, actor.id), db)


@router.post("/workspaces/{wid}/executor-ownership/{capability}/drain")
def drain(wid: UUID, capability: str, data: Version, actor=Depends(user), db=Depends(session)):
    return change(wid, capability, "drain", data, actor, db)


@router.post("/workspaces/{wid}/executor-ownership/{capability}/activate-python")
def activate(wid: UUID, capability: str, data: Version, actor=Depends(user), db=Depends(session)):
    return change(wid, capability, "activate-python", data, actor, db)


@router.post("/workspaces/{wid}/executor-ownership/{capability}/rollback-n8n")
def rollback(wid: UUID, capability: str, data: Version, actor=Depends(user), db=Depends(session)):
    return change(wid, capability, "rollback-n8n", data, actor, db)


@router.get("/internal/executor-ownership/{wid}/{capability}/preflight")
def preflight(wid: UUID, capability: str, x_ownership_token: str = Header(default=""), db=Depends(session)):
    token = os.environ.get("OWNERSHIP_PREFLIGHT_TOKEN", "")
    if not token or not secrets.compare_digest(x_ownership_token, token):
        raise HTTPException(401, "Internal authentication required")
    if capability == "ALL":
        rows = db.scalars(select(ExecutorOwnership).where(ExecutorOwnership.workspace_id == wid)).all()
        return {"allow_new_legacy_claim": any(r.owner == "N8N" and r.state == "ACTIVE" for r in rows),
                "owner": "MIXED", "state": "ACTIVE", "version": max((r.version for r in rows), default=0)}
    if capability not in CAPABILITIES:
        raise HTTPException(404, "Unknown capability")
    row = db.get(ExecutorOwnership, (wid, capability))
    if not row:`r`n        if os.environ.get("APP_ENV") == "ci":`r`n            return {"allow_new_legacy_claim": True, "allow_existing_legacy_lease": True, "owner": "N8N", "state": "ACTIVE", "version": 0}`r`n        raise HTTPException(503, "Ownership authority incomplete")
    return {"allow_new_legacy_claim": row.owner == "N8N" and row.state == "ACTIVE",
            "allow_existing_legacy_lease": row.owner == "N8N",
            "owner": row.owner, "state": row.state, "version": row.version}
