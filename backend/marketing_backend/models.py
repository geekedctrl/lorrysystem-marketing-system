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
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    automation_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    automation: Mapped[dict] = mapped_column(JSONB, default=dict)
    next_discovery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (CheckConstraint("role IN ('OWNER','ADMIN','MEMBER')"),)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(12))


class WorkspaceCreation(Base):
    __tablename__ = "workspace_creations"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(120), primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    request_hash: Mapped[str] = mapped_column(String(64))


class Invitation(Base):
    __tablename__ = "invitations"
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workspaces.id"))
    email: Mapped[str] = mapped_column(String(254))
    role: Mapped[str] = mapped_column(String(12))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProviderConnection(Base):
    __tablename__ = "provider_connections"
    __table_args__ = (CheckConstraint("kind IN ('MODEL','SEARCH')"),)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(8), primary_key=True)
    secret_ciphertext: Mapped[str] = mapped_column(Text)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExecutorOwnership(Base):
    __tablename__ = "executor_ownership"
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), primary_key=True)
    capability: Mapped[str] = mapped_column(String(16), primary_key=True)
    owner: Mapped[str] = mapped_column(String(8), default="N8N")
    state: Mapped[str] = mapped_column(String(8), default="ACTIVE")
    version: Mapped[int] = mapped_column(Integer, default=1)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    rollback_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
        UniqueConstraint("workspace_id", "product_line_id", "kind", "code", name="catalog_line_code"),
        CheckConstraint("kind IN ('PRODUCT','ICP')"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id"), index=True
    )
    product_line_id: Mapped[uuid.UUID] = mapped_column(UUID, server_default=text("NULL"))
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
        CheckConstraint("replay_generation BETWEEN 0 AND 3"),
        CheckConstraint("(status='QUARANTINED')=(quarantine_reason IS NOT NULL)", name="jobs_quarantine_state"),
        UniqueConstraint("workspace_id", "product_line_id", "id", name="job_line_identity"),
        ForeignKeyConstraint(
            ["workspace_id", "product_line_id"],
            ["product_lines.workspace_id", "product_lines.id"],
            name="job_product_line_scope",
        ),
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
            "status IN ('PENDING','RUNNING','COMPLETED','NEEDS_REVIEW','FAILED','QUARANTINED')"
        ),
        CheckConstraint("attempts >= 0 AND max_attempts BETWEEN 1 AND 5"),
        CheckConstraint(
            "(status = 'RUNNING') = (lease_token IS NOT NULL AND lease_until IS NOT NULL)"
        ),
        Index("jobs_ready", "status", "available_at"),
        Index(
            "one_active_lead_job",
            "workspace_id",
            "product_line_id",
            "lead_id",
            unique=True,
            postgresql_where=text("status IN ('PENDING','RUNNING')"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    # The foundation migration backfills this and supplies the default line
    # for legacy inserts. Explicit product-line API selection follows later.
    product_line_id: Mapped[uuid.UUID] = mapped_column(UUID, server_default=text("NULL"))
    trace_id: Mapped[uuid.UUID] = mapped_column(UUID, server_default=text("gen_random_uuid()"))
    task_envelope: Mapped[dict | None] = mapped_column(JSONB)
    quarantine_reason: Mapped[str | None] = mapped_column(String(80))
    quarantined_task_hash: Mapped[str | None] = mapped_column(String(64))
    quarantined_input_hash: Mapped[str | None] = mapped_column(String(64))
    output_generation: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    replay_generation: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
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
            "product_line_id",
            "lead_id",
            unique=True,
            postgresql_where=text("status = 'PREPARING'"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    product_line_id: Mapped[uuid.UUID] = mapped_column(UUID, server_default=text("NULL"))
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
        UniqueConstraint("workspace_id", "product_line_id", "domain", name="discovery_line_domain"),
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
    product_line_id: Mapped[uuid.UUID] = mapped_column(UUID, server_default=text("NULL"))
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
    product_line_id: Mapped[uuid.UUID] = mapped_column(UUID, server_default=text("NULL"))
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
    product_line_id: Mapped[uuid.UUID] = mapped_column(UUID, server_default=text("NULL"))
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


class SenderConnection(Base):
    __tablename__ = "sender_connections"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        CheckConstraint("security IN ('STARTTLS','TLS')"),
        CheckConstraint("port IN (465,587)"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    from_email: Mapped[str] = mapped_column(String(254))
    from_name: Mapped[str] = mapped_column(String(120))
    host: Mapped[str] = mapped_column(String(253))
    port: Mapped[int] = mapped_column(Integer)
    security: Mapped[str] = mapped_column(String(12))
    username: Mapped[str] = mapped_column(String(254))
    secret_ciphertext: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Delivery(Base):
    __tablename__ = "deliveries"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "approval_id"),
        UniqueConstraint("workspace_id", "create_key"),
        ForeignKeyConstraint(["workspace_id", "approval_id"], ["approvals.workspace_id", "approvals.id"]),
        ForeignKeyConstraint(["workspace_id", "sender_id"], ["sender_connections.workspace_id", "sender_connections.id"]),
        CheckConstraint("status IN ('PENDING_SEND_APPROVAL','QUEUED','SENDING','ACCEPTED','FAILED','UNCERTAIN','CANCELLED')"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    product_line_id: Mapped[uuid.UUID] = mapped_column(UUID, server_default=text("NULL"))
    approval_id: Mapped[uuid.UUID] = mapped_column(UUID)
    sender_id: Mapped[uuid.UUID] = mapped_column(UUID)
    create_key: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(24), default="PENDING_SEND_APPROVAL")
    snapshot: Mapped[dict] = mapped_column(JSONB)
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    send_approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    send_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DeliveryAttempt(Base):
    __tablename__ = "native_delivery_attempts"
    __table_args__ = (
        UniqueConstraint("workspace_id", "delivery_id", "attempt_number"),
        ForeignKeyConstraint(["workspace_id", "delivery_id"], ["deliveries.workspace_id", "deliveries.id"]),
        CheckConstraint("status IN ('READY','SENDING','ACCEPTED','FAILED','UNCERTAIN')"),
        CheckConstraint("attempt_number BETWEEN 1 AND 3"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    product_line_id: Mapped[uuid.UUID] = mapped_column(UUID, server_default=text("NULL"))
    delivery_id: Mapped[uuid.UUID] = mapped_column(UUID, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), default="READY")
    message_id: Mapped[str] = mapped_column(String(320))
    failure_code: Mapped[str | None] = mapped_column(String(80))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    lease_token: Mapped[str | None] = mapped_column(String(64))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailSuppression(Base):
    __tablename__ = "native_email_suppressions"
    __table_args__ = (UniqueConstraint("workspace_id", "email"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    email: Mapped[str] = mapped_column(String(254))
    reason: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ProductLine(Base):
    """Ownership foundation; settings selection is wired in a later patch."""
    __tablename__ = "product_lines"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "code"),
        CheckConstraint("context_version >= 1"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(120))
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    paused: Mapped[bool] = mapped_column(Boolean, default=True)
    context_version: Mapped[int] = mapped_column(Integer, default=1)
    context_hash: Mapped[str] = mapped_column(String(64))
    limits: Mapped[dict] = mapped_column(JSONB, default=lambda: {"per_pool_concurrency": 1})
    next_discovery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    versioned: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class StageArtifact(Base):
    __tablename__ = "stage_artifacts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "product_line_id", "job_id"],
            ["jobs.workspace_id", "jobs.product_line_id", "jobs.id"],
        ),
        UniqueConstraint("job_id", "artifact_key"),
        CheckConstraint("schema_version IN (1,2)"),
        Index("stage_artifact_line", "workspace_id", "product_line_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID)
    product_line_id: Mapped[uuid.UUID] = mapped_column(UUID)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID)
    artifact_key: Mapped[str] = mapped_column(String(120))
    contract_name: Mapped[str] = mapped_column(String(80))
    schema_version: Mapped[int] = mapped_column(Integer)
    producer_version: Mapped[str] = mapped_column(String(80))
    context_version: Mapped[int] = mapped_column(Integer)
    context_hash: Mapped[str] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64))
    envelope: Mapped[dict] = mapped_column(JSONB)
    payload: Mapped[dict] = mapped_column(JSONB)
    evidence_refs: Mapped[list] = mapped_column(JSONB, default=list)
    strategy_versions: Mapped[dict] = mapped_column(JSONB, default=dict)
    input_hashes: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class StageEvent(Base):
    __tablename__ = "job_stage_events"
    __table_args__ = (
        UniqueConstraint("workspace_id", "product_line_id", "job_id", "id", name="job_stage_event_scope"),
        CheckConstraint("schema_version >= 0", name="job_event_contract_version"),
        ForeignKeyConstraint(
            ["workspace_id", "product_line_id", "job_id"],
            ["jobs.workspace_id", "jobs.product_line_id", "jobs.id"],
        ),
        Index("job_stage_event_history", "workspace_id", "job_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID)
    product_line_id: Mapped[uuid.UUID] = mapped_column(UUID)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID)
    event: Mapped[str] = mapped_column(String(24))
    stage: Mapped[str] = mapped_column(String(30))
    pool: Mapped[str] = mapped_column(String(30))
    attempt: Mapped[int] = mapped_column(Integer)
    schema_version: Mapped[int] = mapped_column(Integer)
    trace_id: Mapped[uuid.UUID] = mapped_column(UUID)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    error_code: Mapped[str | None] = mapped_column(String(80))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class JobReplay(Base):
    __tablename__ = "job_replays"
    __table_args__ = (
        UniqueConstraint("workspace_id", "job_id", "idempotency_key"),
        UniqueConstraint("job_id", "generation"),
        ForeignKeyConstraint(
            ["workspace_id", "product_line_id", "job_id", "event_id"],
            ["job_stage_events.workspace_id", "job_stage_events.product_line_id",
             "job_stage_events.job_id", "job_stage_events.id"],
        ),
        CheckConstraint("generation BETWEEN 1 AND 3"),
        CheckConstraint("previous_attempts BETWEEN 0 AND 5"),
        Index("job_replay_history", "workspace_id", "job_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID)
    product_line_id: Mapped[uuid.UUID] = mapped_column(UUID)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    idempotency_key: Mapped[str] = mapped_column(String(120))
    generation: Mapped[int] = mapped_column(Integer)
    previous_attempts: Mapped[int] = mapped_column(Integer)
    envelope_hash: Mapped[str] = mapped_column(String(64))
    input_hash: Mapped[str] = mapped_column(String(64))
    consumer_version: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CompanyEvidence(Base):
    __tablename__="company_evidence"
    __table_args__=(ForeignKeyConstraint(["workspace_id","lead_id"],["leads.workspace_id","leads.id"]),
                   UniqueConstraint("workspace_id","lead_id","input_hash","content_hash"))
    id: Mapped[uuid.UUID] = mapped_column(UUID,primary_key=True,default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID)
    lead_id: Mapped[uuid.UUID] = mapped_column(UUID)
    source_url: Mapped[str] = mapped_column(Text)
    input_hash: Mapped[str] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB)
    fetch_version: Mapped[str] = mapped_column(String(80))
    extract_version: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)
