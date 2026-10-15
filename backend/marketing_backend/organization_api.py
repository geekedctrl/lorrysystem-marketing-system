"""Native account, organization and workspace settings contracts."""
import hashlib
import os
from urllib.parse import urlsplit
import secrets
from datetime import timedelta
from uuid import UUID
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import select, text
from . import contracts as out
from .auth import user, scope, digest, hash_password, verify_password
from .db import session
from .models import (Organization, OrganizationMembership, Workspace,
                     WorkspaceCreation, Membership, User, LoginSession, Invitation,
                     SenderConnection, now)
from .models import ProviderConnection
from .public_fetch import checked_url, FetchError
from .sending import encrypt_secret

router = APIRouter()


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OrganizationInput(Strict):
    name: str = Field(min_length=2, max_length=120)


class CreateWorkspace(Strict):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=2000)
    idempotency_key: str = Field(min_length=8, max_length=120)


class WorkspaceProfile(Strict):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=2000)


class PasswordChange(Strict):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class InviteInput(Strict):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    role: str = Field(pattern=r"^(OWNER|ADMIN|MEMBER|OPERATOR|REVIEWER|VIEWER)$")


class AcceptInput(Strict):
    token: str = Field(min_length=32, max_length=256)


class OrganizationRoleInput(Strict):
    role: Literal["OWNER", "ADMIN", "MEMBER"]


class WorkspaceRoleInput(Strict):
    role: Literal["ADMIN", "OPERATOR", "REVIEWER", "VIEWER"]


class WorkspaceStatusInput(Strict):
    active: bool


class DiscoveryPreferences(Strict):
    batch_size: int = Field(ge=1, le=10, strict=True)


class ProviderDraftInput(Strict):
    secret: SecretStr
    base_url: str | None = Field(default=None, max_length=500)
    model_name: str | None = Field(default=None, max_length=200)


def organization_role(db, oid, actor, roles=None):
    member = db.get(OrganizationMembership, (oid, actor.id))
    if not member:
        raise HTTPException(404, "Organization not found")
    if roles and member.role not in roles:
        raise HTTPException(403, "Organization owner or administrator required")
    return member


@router.get("/organizations", response_model=list[out.OrganizationResponse])
def organizations(actor=Depends(user), db=Depends(session)):
    return [{"id": org.id, "name": org.name, "role": member.role}
            for org, member in db.execute(select(Organization, OrganizationMembership)
                .join(OrganizationMembership, Organization.id == OrganizationMembership.organization_id)
                .where(OrganizationMembership.user_id == actor.id).order_by(Organization.name))]


@router.post("/organizations", status_code=201, response_model=out.OrganizationResponse)
def create_organization(data: OrganizationInput, actor=Depends(user), db=Depends(session)):
    org = Organization(name=data.name)
    db.add(org)
    db.flush()
    db.add(OrganizationMembership(organization_id=org.id, user_id=actor.id, role="OWNER"))
    db.commit()
    return {"id": org.id, "name": org.name, "role": "OWNER"}


@router.put("/organizations/{oid}", response_model=out.OrganizationName)
def update_organization(oid: UUID, data: OrganizationInput, actor=Depends(user), db=Depends(session)):
    organization_role(db, oid, actor, {"OWNER", "ADMIN"})
    org = db.get(Organization, oid)
    org.name = data.name
    db.commit()
    return {"id": org.id, "name": org.name}


@router.get("/organizations/{oid}/workspaces", response_model=list[out.OrganizationWorkspace])
def organization_workspaces(oid: UUID, actor=Depends(user), db=Depends(session)):
    organization_role(db, oid, actor)
    return [{"id": w.id, "name": w.name, "description": w.description,
             "active": w.active, "role": m.role if m else None}
            for w, m in db.execute(select(Workspace, Membership)
                .outerjoin(Membership, (Membership.workspace_id == Workspace.id) & (Membership.user_id == actor.id))
                .where(Workspace.organization_id == oid).order_by(Workspace.name))]


@router.patch("/organizations/{oid}/workspaces/{wid}/status", response_model=out.WorkspaceStatus)
def change_workspace_status(oid: UUID, wid: UUID, data: WorkspaceStatusInput,
                            actor=Depends(user), db=Depends(session)):
    organization_role(db, oid, actor, {"OWNER", "ADMIN"})
    w = db.get(Workspace, wid)
    if not w or w.organization_id != oid:
        raise HTTPException(404, "Workspace not found")
    w.active = data.active
    db.commit()
    return {"id": w.id, "active": w.active}


@router.get("/organizations/{oid}/members", response_model=list[out.OrganizationMember])
def organization_members(oid: UUID, actor=Depends(user), db=Depends(session)):
    organization_role(db, oid, actor)
    return [{"user_id": member.user_id, "email": account.email, "role": member.role}
            for member, account in db.execute(select(OrganizationMembership, User)
                .join(User, User.id == OrganizationMembership.user_id)
                .where(OrganizationMembership.organization_id == oid))]


@router.patch("/organizations/{oid}/members/{member_id}", response_model=out.MemberRole)
def change_organization_role(oid: UUID, member_id: UUID, data: OrganizationRoleInput,
                             actor=Depends(user), db=Depends(session)):
    administrator = organization_role(db, oid, actor, {"OWNER", "ADMIN"})
    target = db.get(OrganizationMembership, (oid, member_id))
    if not target:
        raise HTTPException(404, "Organization member not found")
    if (target.role == "OWNER" or data.role == "OWNER") and administrator.role != "OWNER":
        raise HTTPException(403, "Only an owner may change owner roles")
    if target.role == "OWNER" and data.role != "OWNER":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": f"owners:{oid}"})
        owners = list(db.scalars(select(OrganizationMembership).where(
            OrganizationMembership.organization_id == oid,
            OrganizationMembership.role == "OWNER")))
        if len(owners) <= 1:
            raise HTTPException(409, "An organization needs at least one owner")
    target.role = data.role
    db.commit()
    return {"user_id": target.user_id, "role": target.role}


def issue_invitation(db, oid, wid, email, role):
    email = email.lower()
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
               {"key": f"invite:{oid}:{wid}:{email}"})
    token = secrets.token_urlsafe(32)
    existing = db.scalar(select(Invitation).where(
        Invitation.organization_id == oid, Invitation.workspace_id == wid,
        Invitation.email == email, Invitation.accepted_at.is_(None)))
    if existing and existing.expires_at > now():
        raise HTTPException(409, "An invitation is already pending for this email")
    invite = existing or Invitation(organization_id=oid, workspace_id=wid, email=email)
    invite.token_hash = digest(token)
    invite.role = role
    invite.expires_at = now() + timedelta(days=7)
    db.add(invite)
    db.commit()
    return {"id": invite.id, "token": token, "expires_at": invite.expires_at}


@router.post("/organizations/{oid}/invitations", status_code=201, response_model=out.InvitationCreated)
def invite_organization(oid: UUID, data: InviteInput, actor=Depends(user), db=Depends(session)):
    organization_role(db, oid, actor, {"OWNER", "ADMIN"})
    if data.role not in {"OWNER", "ADMIN", "MEMBER"}:
        raise HTTPException(422, "Choose an organization role")
    if data.role == "OWNER" and organization_role(db, oid, actor).role != "OWNER":
        raise HTTPException(403, "Only an owner may invite another owner")
    if db.scalar(select(User.id).join(OrganizationMembership, User.id == OrganizationMembership.user_id)
                 .where(OrganizationMembership.organization_id == oid, User.email == data.email.lower())):
        raise HTTPException(409, "This person is already a member")
    return issue_invitation(db, oid, None, data.email, data.role)


@router.post("/workspaces/{wid}/invitations", status_code=201, response_model=out.InvitationCreated)
def invite_workspace(wid: UUID, data: InviteInput, actor=Depends(user), db=Depends(session)):
    scope(wid, actor, db, ["ADMIN"])
    if data.role not in {"ADMIN", "OPERATOR", "REVIEWER", "VIEWER"}:
        raise HTTPException(422, "Choose a workspace role")
    w = db.get(Workspace, wid)
    if db.scalar(select(User.id).join(Membership, User.id == Membership.user_id)
                 .where(Membership.workspace_id == wid, User.email == data.email.lower())):
        raise HTTPException(409, "This person already has workspace access")
    return issue_invitation(db, w.organization_id, wid, data.email, data.role)


@router.post("/invitations/accept", response_model=out.InvitationAccepted)
def accept_invitation(data: AcceptInput, actor=Depends(user), db=Depends(session)):
    invite = db.scalar(select(Invitation).where(Invitation.token_hash == digest(data.token)).with_for_update())
    if not invite or invite.email != actor.email or invite.expires_at <= now():
        raise HTTPException(404, "Invitation expired or unavailable for this account")
    if invite.accepted_at:
        return {"accepted": True, "organization_id": invite.organization_id, "workspace_id": invite.workspace_id}
    if invite.workspace_id:
        if not db.get(OrganizationMembership, (invite.organization_id, actor.id)):
            db.add(OrganizationMembership(organization_id=invite.organization_id, user_id=actor.id, role="MEMBER"))
        if not db.get(Membership, (invite.workspace_id, actor.id)):
            db.add(Membership(workspace_id=invite.workspace_id, user_id=actor.id, role=invite.role))
    elif not db.get(OrganizationMembership, (invite.organization_id, actor.id)):
        db.add(OrganizationMembership(organization_id=invite.organization_id, user_id=actor.id, role=invite.role))
    invite.accepted_at = now()
    db.commit()
    return {"accepted": True, "organization_id": invite.organization_id, "workspace_id": invite.workspace_id}


@router.post("/organizations/{oid}/workspaces", status_code=201, response_model=out.NewWorkspace)
def create_workspace(oid: UUID, data: CreateWorkspace, actor=Depends(user), db=Depends(session)):
    organization_role(db, oid, actor, {"OWNER", "ADMIN"})
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
               {"key": f"workspace:{oid}:{actor.id}:{data.idempotency_key}"})
    fingerprint = hashlib.sha256(f"{data.name}\0{data.description}".encode()).hexdigest()
    old = db.get(WorkspaceCreation, (oid, actor.id, data.idempotency_key))
    if old:
        if old.request_hash != fingerprint:
            raise HTTPException(409, "This submission key was used for different workspace details")
        w = db.get(Workspace, old.workspace_id)
        return {"id": w.id, "name": w.name, "organization_id": oid, "replayed": True}
    w = Workspace(organization_id=oid, name=data.name, description=data.description)
    db.add(w)
    db.flush()
    db.add(Membership(workspace_id=w.id, user_id=actor.id, role="ADMIN"))
    db.add(WorkspaceCreation(organization_id=oid, user_id=actor.id,
                             idempotency_key=data.idempotency_key,
                             workspace_id=w.id, request_hash=fingerprint))
    db.commit()
    return {"id": w.id, "name": w.name, "organization_id": oid, "replayed": False}


@router.get("/workspaces/{wid}/profile", response_model=out.WorkspaceProfile)
def workspace_profile(wid: UUID, actor=Depends(user), db=Depends(session)):
    membership = scope(wid, actor, db)
    w = db.get(Workspace, wid)
    return {"id": w.id, "organization_id": w.organization_id, "name": w.name,
            "description": w.description, "active": w.active, "role": membership.role}


@router.put("/workspaces/{wid}/profile", response_model=out.WorkspaceProfile)
def update_workspace_profile(wid: UUID, data: WorkspaceProfile, actor=Depends(user), db=Depends(session)):
    scope(wid, actor, db, ["ADMIN"])
    w = db.get(Workspace, wid)
    w.name, w.description = data.name, data.description
    db.commit()
    return workspace_profile(wid, actor, db)


@router.get("/workspaces/{wid}/members", response_model=list[out.WorkspaceMember])
def workspace_members(wid: UUID, actor=Depends(user), db=Depends(session)):
    scope(wid, actor, db)
    return [{"user_id": member.user_id, "email": account.email, "role": member.role}
            for member, account in db.execute(select(Membership, User)
                .join(User, User.id == Membership.user_id).where(Membership.workspace_id == wid))]


@router.patch("/workspaces/{wid}/members/{member_id}", response_model=out.MemberRole)
def change_workspace_role(wid: UUID, member_id: UUID, data: WorkspaceRoleInput,
                          actor=Depends(user), db=Depends(session)):
    scope(wid, actor, db, ["ADMIN"])
    member = db.get(Membership, (wid, member_id))
    if not member:
        raise HTTPException(404, "Workspace member not found")
    if member.user_id == actor.id and data.role != "ADMIN":
        raise HTTPException(409, "Choose another administrator to change your role")
    member.role = data.role
    db.commit()
    return {"user_id": member.user_id, "role": member.role}


@router.get("/workspaces/{wid}/connections", response_model=out.ConnectionStatus)
def connection_status(wid: UUID, actor=Depends(user), db=Depends(session)):
    scope(wid, actor, db)
    workspace = db.get(Workspace, wid)
    senders = list(db.scalars(select(SenderConnection).where(SenderConnection.workspace_id == wid)))
    drafts = list(db.scalars(select(ProviderConnection).where(ProviderConnection.workspace_id == wid)))
    draft_by_kind = {draft.kind: draft for draft in drafts}
    return {
        "automation": "disabled" if not workspace.automation_enabled else "configured",
        "model": "configured" if os.getenv("MODEL_API_KEY") else ("unverified" if "MODEL" in draft_by_kind else "unavailable"),
        "search": "configured" if os.getenv("BRAVE_SEARCH_API_KEY") else ("unverified" if "SEARCH" in draft_by_kind else "unavailable"),
        "senders": [{"id": item.id, "name": item.name,
                     "status": "disabled" if not item.enabled else ("verified" if item.verified_at else "unverified")}
                    for item in senders],
        "provider_drafts": [{"kind": item.kind, "status": "unverified",
                             "settings": item.settings, "secret_present": True} for item in drafts],
    }


@router.put("/workspaces/{wid}/provider-connections/{kind}", response_model=out.ProviderDraftStatus)
def save_provider_draft(wid: UUID, kind: Literal["MODEL", "SEARCH"], data: ProviderDraftInput,
                        actor=Depends(user), db=Depends(session)):
    scope(wid, actor, db, ["ADMIN"])
    if not 8 <= len(data.secret.get_secret_value()) <= 4096:
        raise HTTPException(422, "Provider key must be 8–4096 characters")
    if kind == "MODEL":
        if not data.base_url or not data.model_name:
            raise HTTPException(422, "Model endpoint and model name are required")
        try:
            checked_url(data.base_url)
        except FetchError:
            raise HTTPException(422, "Use a public HTTPS model endpoint") from None
        if not data.base_url.startswith("https://"):
            raise HTTPException(422, "Use a public HTTPS model endpoint")
        parsed = urlsplit(data.base_url)
        if parsed.query or parsed.fragment:
            raise HTTPException(422, "Model endpoint cannot contain a query or fragment")
        settings = {"base_url": data.base_url.rstrip("/"), "model_name": data.model_name}
    else:
        if data.base_url or data.model_name:
            raise HTTPException(422, "Search uses the managed provider endpoint")
        settings = {}
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
               {"key": f"provider-draft:{wid}:{kind}"})
    row = db.get(ProviderConnection, (wid, kind))
    if not row:
        row = ProviderConnection(workspace_id=wid, kind=kind)
        db.add(row)
    row.secret_ciphertext = encrypt_secret(data.secret.get_secret_value(), wid)
    row.settings = settings
    row.enabled = False
    row.verified_at = None
    db.commit()
    return {"kind": kind, "status": "unverified", "settings": settings, "secret_present": True}


@router.put("/workspaces/{wid}/automation/preferences", response_model=out.DiscoveryBatchSize)
def save_discovery_preferences(wid: UUID, data: DiscoveryPreferences,
                               actor=Depends(user), db=Depends(session)):
    scope(wid, actor, db, ["ADMIN"])
    w = db.get(Workspace, wid)
    if not w.automation.get("product_description"):
        raise HTTPException(409, "Complete product setup before changing discovery preferences")
    w.automation = {**w.automation, "batch_size": data.batch_size}
    db.commit()
    return {"batch_size": data.batch_size}


@router.post("/auth/password", status_code=204)
def change_password(data: PasswordChange, actor=Depends(user), db=Depends(session),
                    authorization: str = Header(default="")):
    if not verify_password(data.current_password, actor.password_hash):
        raise HTTPException(403, "Current password is incorrect")
    actor.password_hash = hash_password(data.new_password)
    current = digest(authorization[7:])
    db.execute(text("DELETE FROM login_sessions WHERE user_id=:uid AND token_hash<>:current"),
               {"uid": actor.id, "current": current})
    db.commit()


@router.get("/auth/sessions", response_model=list[out.AccountSession])
def sessions(actor=Depends(user), db=Depends(session), authorization: str = Header(default="")):
    current = digest(authorization[7:])
    return [{"current": item.token_hash == current, "expires_at": item.expires_at}
            for item in db.scalars(select(LoginSession).where(
                LoginSession.user_id == actor.id, LoginSession.expires_at > now()))]


@router.delete("/auth/sessions/other", status_code=204)
def end_other_sessions(actor=Depends(user), db=Depends(session), authorization: str = Header(default="")):
    db.execute(text("DELETE FROM login_sessions WHERE user_id=:uid AND token_hash<>:current"),
               {"uid": actor.id, "current": digest(authorization[7:])})
    db.commit()
