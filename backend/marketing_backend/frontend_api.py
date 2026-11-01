from .product_lines import default_id, default_expr, for_run
"""Additive native frontend contracts, lead paging and audited draft revisions."""

import base64
import copy
import json
import re
from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import Field
from sqlalchemy import select, func, tuple_
from sqlalchemy.exc import IntegrityError
from . import contracts as out
from .auth import user, scope, digest
from .db import session
from .models import (
    Lead,
    PreparationRun,
    Catalog,
    Approval,
    LoginSession,
    Job,
    Workspace,
    OrganizationMembership,
    now,
)
from .pipeline import context, fingerprint
from .stages import Strict, Citation, DraftOutput, cite
from .research import ProviderFailure
from .catalog_policy import lock_catalog_change

router = APIRouter()


def latest_query(wid, lid, product_line_id=None):
    return (
        select(PreparationRun)
        .where(PreparationRun.workspace_id == wid, PreparationRun.lead_id == lid, PreparationRun.product_line_id == (product_line_id or default_expr(wid)))
        .order_by(PreparationRun.created_at.desc(), PreparationRun.id.desc())
    )


def public_run(run):
    return {
        k: getattr(run, k)
        for k in ("id", "product_line_id", "lead_id", "status", "stop_reason", "results", "created_at")
    }


def detail(lead, run):
    return {
        "id": lead.id,
        "company_name": lead.company_name,
        "website": lead.website,
        "created_at": lead.created_at,
        "current_preparation": public_run(run) if run else None,
        "primary_contact": (
            run.results.get("CONTACT_SEARCH", {}).get("selected_contact")
            if run
            else None
        ),
    }


@router.get("/auth/me", response_model=out.CurrentUser)
def me(
    actor=Depends(user), db=Depends(session), authorization: str = Header(default="")
):
    login = db.get(LoginSession, digest(authorization[7:]))
    if not login or login.expires_at <= now():
        raise HTTPException(401, "Session invalid or expired")
    return {
        "id": actor.id,
        "email": actor.email,
        "capabilities": {"create_workspace": bool(db.scalar(select(OrganizationMembership).where(
            OrganizationMembership.user_id == actor.id,
            OrganizationMembership.role.in_(["OWNER", "ADMIN"]))))},
        "expires_at": login.expires_at,
    }


@router.get(
    "/workspaces/{wid}/leads/page",
    response_model=out.LeadPage,
    response_model_exclude_unset=True,
)
def leads_page(
    wid: UUID,
    actor=Depends(user),
    db=Depends(session),
    limit: int = Query(default=25, ge=1, le=100),
    q: str = Query(default="", max_length=200),
    status: out.RunStatus | None = None,
    cursor: str | None = Query(default=None, max_length=1500),
):
    scope(wid, actor, db)
    instant, before = now(), None
    if cursor:
        try:
            value = json.loads(
                base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
            )
            if (value["wid"], value["q"], value["status"]) != (str(wid), q, status):
                raise ValueError()
            instant = datetime.fromisoformat(value["as_of"])
            before = (datetime.fromisoformat(value["created_at"]), UUID(value["id"]))
            if (
                not instant.tzinfo
                or not before[0].tzinfo
                or before[0] > instant
                or instant > now()
            ):
                raise ValueError()
        except (ValueError, KeyError, TypeError, UnicodeError):
            raise HTTPException(
                422, "Invalid cursor or changed workspace/filters"
            ) from None
    current_id = (
        select(PreparationRun.id)
        .where(PreparationRun.workspace_id == wid, PreparationRun.lead_id == Lead.id)
        .order_by(PreparationRun.created_at.desc(), PreparationRun.id.desc())
        .limit(1)
        .correlate(Lead)
        .scalar_subquery()
    )
    stmt = (
        select(Lead, PreparationRun)
        .outerjoin(PreparationRun, PreparationRun.id == current_id)
        .where(Lead.workspace_id == wid, Lead.created_at <= instant)
    )
    if q:
        literal = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(Lead.company_name.ilike("%" + literal + "%", escape="\\"))
    if status:
        stmt = stmt.where(PreparationRun.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    if before:
        stmt = stmt.where(tuple_(Lead.created_at, Lead.id) < before)
    rows = list(
        db.execute(
            stmt.order_by(Lead.created_at.desc(), Lead.id.desc()).limit(limit + 1)
        )
    )
    more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if more:
        last = rows[-1][0]
        next_cursor = (
            base64.urlsafe_b64encode(
                json.dumps(
                    {
                        "wid": str(wid),
                        "q": q,
                        "status": status,
                        "as_of": instant.isoformat(),
                        "created_at": last.created_at.isoformat(),
                        "id": str(last.id),
                    }
                ).encode()
            )
            .decode()
            .rstrip("=")
        )
    return {
        "items": [detail(l, r) for l, r in rows],
        "total": total,
        "limit": limit,
        "next_cursor": next_cursor,
        "as_of": instant,
    }


@router.get(
    "/workspaces/{wid}/leads/{lid}",
    response_model=out.LeadDetail,
    response_model_exclude_unset=True,
)
def lead_detail(wid: UUID, lid: UUID, actor=Depends(user), db=Depends(session)):
    scope(wid, actor, db)
    lead = db.scalar(select(Lead).where(Lead.workspace_id == wid, Lead.id == lid))
    if not lead:
        raise HTTPException(404, "Lead not found")
    return detail(lead, db.scalar(latest_query(wid, lid).limit(1)))


class CatalogActive(Strict):
    active: bool = Field(strict=True)


@router.get("/workspaces/{wid}/catalog/all", response_model=list[out.CatalogState])
def all_catalog(wid: UUID, actor=Depends(user), db=Depends(session)):
    scope(wid, actor, db)
    return [
        {
            **{
                k: getattr(c, k)
                for k in (
                    "id",
                    "kind",
                    "code",
                    "name",
                    "description",
                    "rules",
                    "active",
                )
            },
            "version": c.context_version,
        }
        for c in db.scalars(
            select(Catalog)
            .where(Catalog.workspace_id == wid, Catalog.product_line_id == default_id(db, wid))
            .order_by(Catalog.kind, Catalog.code)
        )
    ]


@router.patch("/workspaces/{wid}/catalog/{cid}", response_model=out.CatalogLifecycle)
def catalog_active(
    wid: UUID, cid: UUID, data: CatalogActive, actor=Depends(user), db=Depends(session)
):
    scope(wid, actor, db, ["ADMIN"])
    item = lock_catalog_change(db, wid, cid=cid, desired={"active": data.active})
    if not item:
        raise HTTPException(404, "Catalog item not found")
    if item.active != data.active:
        item.context_version += 1
    item.active = data.active
    db.flush()
    active_kinds = set(
        db.scalars(
            select(Catalog.kind).where(
                Catalog.workspace_id == wid,
                    Catalog.product_line_id == default_id(db, wid), Catalog.active.is_(True)
            )
        )
    )
    if not {"PRODUCT", "ICP"} <= active_kinds:
        workspace = db.get(Workspace, wid)
        workspace.automation_enabled = False
        workspace.next_discovery_at = None
    db.commit()
    return {"id": item.id, "code": item.code, "active": item.active}


class Revision(Strict):
    idempotency_key: str = Field(min_length=8, max_length=120)
    expected_version: int = Field(ge=1, strict=True)
    subject: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=30, max_length=3000)
    evidence: list[Citation] = Field(min_length=1, max_length=10)
    note: str = Field(min_length=5, max_length=1000)


@router.post(
    "/workspaces/{wid}/approvals/{aid}/revision",
    status_code=201,
    response_model=out.RevisionResponse,
)
def revise(
    wid: UUID, aid: UUID, data: Revision, actor=Depends(user), db=Depends(session)
):
    scope(wid, actor, db, ["ADMIN", "OPERATOR"])
    request_hash = fingerprint(
        {"parent": str(aid), "actor": str(actor.id), **data.model_dump(mode="json")}
    )
    old = db.scalar(
        select(Approval).where(
            Approval.workspace_id == wid,
            Approval.idempotency_key == data.idempotency_key,
        )
    )
    if old:
        if old.revision_hash != request_hash:
            raise HTTPException(409, "Idempotency key belongs to another revision")
        return {
            "approval_id": old.id,
            "run_id": old.run_id,
            "version": old.version,
            "status": "PENDING_APPROVAL",
            "sent": False,
        }
    parent = db.scalar(
        select(Approval)
        .where(Approval.workspace_id == wid, Approval.id == aid)
        .with_for_update()
    )
    if not parent:
        raise HTTPException(404, "Approval not found")
    if parent.version != data.expected_version or parent.status != "CHANGES_REQUESTED":
        raise HTTPException(
            409, "Revision requires the current requested-changes version"
        )
    run = db.scalar(
        select(PreparationRun)
        .where(PreparationRun.workspace_id == wid, PreparationRun.id == parent.run_id)
        .with_for_update()
    )
    # All preparation entry points lock the lead, serializing revisions with new runs.
    db.scalar(
        select(Lead)
        .where(Lead.workspace_id == wid, Lead.id == run.lead_id)
        .with_for_update()
    )
    current = db.scalar(latest_query(wid, run.lead_id,run.product_line_id).limit(1))
    if current.id != run.id or run.context_hash != fingerprint(
        for_run(db, run)
    ):
        raise HTTPException(409, "Draft context is stale; prepare a fresh draft")
    if db.scalar(
        select(Job.id).where(
            Job.workspace_id == wid,
            Job.lead_id == run.lead_id,
            Job.product_line_id == run.product_line_id,
            Job.status.in_(["PENDING", "RUNNING"]),
        )
    ):
        raise HTTPException(409, "Preparation is already active")
    draft = {
        **parent.snapshot["draft"],
        **data.model_dump(mode="json", include={"subject", "body", "evidence"}),
    }
    try:
        DraftOutput.model_validate(
            {k: draft[k] for k in ("subject", "body", "evidence")}
        )
        for evidence in draft["evidence"]:
            cite(evidence, run.results["RESEARCH"]["pages"])
        if re.search(
            r"guarantee|will reduce|will save|replace your current", draft["body"], re.I
        ):
            raise ProviderFailure("DRAFT_UNSUPPORTED_PROMISE")
    except (ValueError, ProviderFailure) as exc:
        raise HTTPException(422, getattr(exc, "code", "Invalid draft")) from None
    revision = {
        "parent_approval_id": str(parent.id),
        "version": parent.version + 1,
        "editor_id": str(actor.id),
        "at": now().isoformat(),
        "note": data.note,
        "reviewer_note": parent.decision.get("note"),
    }
    results = {**copy.deepcopy(run.results), "DRAFTING": draft}
    fresh = PreparationRun(
        workspace_id=wid,
        product_line_id=run.product_line_id,
        lead_id=run.lead_id,
        context_hash=run.context_hash,
        snapshot=copy.deepcopy(run.snapshot),
        results=results,
        status="PENDING_APPROVAL",
    )
    db.add(fresh)
    db.flush()
    approval = Approval(
        workspace_id=wid,
        run_id=fresh.id,
        version=parent.version + 1,
        parent_approval_id=parent.id,
        idempotency_key=data.idempotency_key,
        revision_hash=request_hash,
        editor_id=actor.id,
        snapshot={
            "context_hash": fresh.context_hash,
            "inputs": fresh.snapshot,
            "results": results,
            "draft": draft,
            "revision": revision,
        },
    )
    db.add(approval)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409, "Another revision was submitted; refresh review history"
        ) from None
    return {
        "approval_id": approval.id,
        "run_id": fresh.id,
        "version": approval.version,
        "status": "PENDING_APPROVAL",
        "sent": False,
    }
