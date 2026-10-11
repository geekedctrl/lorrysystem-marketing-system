import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    String,
    Text,
    DateTime,
    Integer,
    Boolean,
    ForeignKey,
    UniqueConstraint,
    Index,
    CheckConstraint,
    ForeignKeyConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


def now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    identity_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    automation_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    automation: Mapped[dict] = mapped_column(JSONB, default=dict)
    next_discovery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        CheckConstraint("role IN ('ADMIN','OPERATOR','REVIEWER','VIEWER')"),
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(12))


class Catalog(Base):
    __tablename__ = "catalog"
    __table_args__ = (
        UniqueConstraint("workspace_id", "kind", "code"),
        CheckConstraint("kind IN ('PRODUCT','ICP')"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id"), index=True
    )
    kind: Mapped[str] = mapped_column(String(8))
    code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    rules: Mapped[dict] = mapped_column(JSONB, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    context_version: Mapped[int] = mapped_column(Integer, default=1)


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "website"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id"), index=True
    )
    company_name: Mapped[str] = mapped_column(String(200))
    website: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "idempotency_key"),
        ForeignKeyConstraint(
            ["workspace_id", "lead_id"], ["leads.workspace_id", "leads.id"]
        ),
        ForeignKeyConstraint(
            ["workspace_id", "run_id"],
            ["preparation_runs.workspace_id", "preparation_runs.id"],
        ),
        UniqueConstraint("run_id", "kind"),
        ForeignKeyConstraint(
            ["workspace_id", "run_id", "lead_id"],
            [
                "preparation_runs.workspace_id",
                "preparation_runs.id",
                "preparation_runs.lead_id",
            ],
            name="job_run_lead",
        ),
        CheckConstraint(
            "(managed AND (kind IN ('SETUP','DISCOVERY') OR run_id IS NOT NULL)) OR (NOT managed AND kind='RESEARCH' AND run_id IS NULL)",
            name="managed_stage_scope",
        ),
        CheckConstraint(
            "kind IN ('SETUP','DISCOVERY','RESEARCH','CONTACT_SEARCH','SCORING','MATCHING','DRAFTING')"
        ),
        CheckConstraint(
            "(kind IN ('SETUP','DISCOVERY') AND lead_id IS NULL AND run_id IS NULL) OR (kind NOT IN ('SETUP','DISCOVERY') AND lead_id IS NOT NULL)"
        ),
        CheckConstraint(
            "status IN ('PENDING','RUNNING','COMPLETED','NEEDS_REVIEW','FAILED')"
        ),
        CheckConstraint("attempts >= 0 AND max_attempts BETWEEN 1 AND 5"),
        CheckConstraint(
            "(status = 'RUNNING') = (lease_token IS NOT NULL AND lease_until IS NOT NULL)"
        ),
        Index("jobs_ready", "status", "available_at"),
        Index(
            "one_active_lead_job",
            "workspace_id",
            "lead_id",
            unique=True,
            postgresql_where=text("status IN ('PENDING','RUNNING')"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    lead_id: Mapped[uuid.UUID | None] = mapped_column(UUID)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID)
    managed: Mapped[bool] = mapped_column(Boolean, default=False)
    kind: Mapped[str] = mapped_column(String(30), default="RESEARCH")
    idempotency_key: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    payload: Mapped[dict] = mapped_column(JSONB)
    checkpoint: Mapped[dict] = mapped_column(JSONB, default=dict)
    result: Mapped[dict] = mapped_column(JSONB, default=dict)
    history: Mapped[list] = mapped_column(JSONB, default=list)
    failure_code: Mapped[str | None] = mapped_column(String(80))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    lease_token: Mapped[str | None] = mapped_column(String(64))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PreparationRun(Base):
    __tablename__ = "preparation_runs"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "id", "lead_id", name="run_lead_identity"),
        ForeignKeyConstraint(
            ["workspace_id", "lead_id"], ["leads.workspace_id", "leads.id"]
        ),
        CheckConstraint(
            "status IN ('PREPARING','NEEDS_REVIEW','PENDING_APPROVAL','APPROVED','REJECTED','CHANGES_REQUESTED','FAILED','STALE')"
        ),
        Index(
            "one_preparing_run",
            "workspace_id",
            "lead_id",
            unique=True,
            postgresql_where=text("status = 'PREPARING'"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    lead_id: Mapped[uuid.UUID] = mapped_column(UUID)
    context_hash: Mapped[str] = mapped_column(String(64))
    snapshot: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(24), default="PREPARING")
    stop_reason: Mapped[str | None] = mapped_column(String(80))
    results: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DiscoveryMemory(Base):
    __tablename__ = "discovery_memory"
    __table_args__ = (
        UniqueConstraint("workspace_id", "domain"),
        UniqueConstraint("workspace_id", "id", name="discovery_identity"),
        ForeignKeyConstraint(
            ["workspace_id", "source_job_id"],
            ["jobs.workspace_id", "jobs.id"],
            name="discovery_job_scope",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "accepted_lead_id"],
            ["leads.workspace_id", "leads.id"],
            name="discovery_lead_scope",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    domain: Mapped[str] = mapped_column(String(254))
    candidate: Mapped[dict] = mapped_column(JSONB)
    outcome: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    source_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID)
    context_hash: Mapped[str | None] = mapped_column(String(64))
    accepted_lead_id: Mapped[uuid.UUID | None] = mapped_column(UUID)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
    retry_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProviderUsage(Base):
    __tablename__ = "provider_usage"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "job_id"], ["jobs.workspace_id", "jobs.id"]
        ),
        CheckConstraint("estimated_microusd >= 0"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    job_id: Mapped[uuid.UUID] = mapped_column(UUID)
    provider: Mapped[str] = mapped_column(String(24))
    operation: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(24), default="RESERVED")
    estimated_microusd: Mapped[int] = mapped_column(Integer)
    usage: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        UniqueConstraint("run_id"),
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "idempotency_key"),
        UniqueConstraint("parent_approval_id"),
        ForeignKeyConstraint(
            ["workspace_id", "parent_approval_id"],
            ["approvals.workspace_id", "approvals.id"],
        ),
        ForeignKeyConstraint(
            ["workspace_id", "run_id"],
            ["preparation_runs.workspace_id", "preparation_runs.id"],
        ),
        CheckConstraint(
            "status IN ('PENDING','APPROVED','REJECTED','CHANGES_REQUESTED')"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    run_id: Mapped[uuid.UUID] = mapped_column(UUID)
    snapshot: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(24), default="PENDING")
    decision: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_approval_id: Mapped[uuid.UUID | None] = mapped_column(UUID)
    idempotency_key: Mapped[str | None] = mapped_column(String(120))
    revision_hash: Mapped[str | None] = mapped_column(String(64))
    editor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
