from datetime import datetime
from uuid import UUID as PyUUID
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.models.workspaces import WorkspaceOwned


class AutomationWorker(Base):
    __tablename__ = "automation_workers"
    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ProductAutomationPlan(WorkspaceOwned, Base):
    __tablename__ = "product_automation_plans"
    __table_args__ = (
        UniqueConstraint("workspace_id"),
        CheckConstraint(
            "state IN ('DRAFT','CONFIGURING','ACTIVE','NEEDS_ATTENTION')",
            name="ck_product_plan_state",
        ),
    )
    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    state: Mapped[str] = mapped_column(Text, nullable=False, default="DRAFT")
    profile: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    configuration: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    activated_by: Mapped[str | None] = mapped_column(Text)
    next_discovery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AutomationJob(WorkspaceOwned, Base):
    __tablename__ = "automation_jobs"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('SETUP','DISCOVERY','RESEARCH','SCORING','MATCHING','DRAFTING')",
            name="ck_automation_job_kind",
        ),
        CheckConstraint(
            "status IN ('PENDING','RUNNING','COMPLETED','FAILED','NEEDS_REVIEW')",
            name="ck_automation_job_status",
        ),
        Index(
            "ix_automation_job_related",
            "workspace_id",
            "kind",
            "related_id",
            unique=True,
            postgresql_where=text("related_id IS NOT NULL"),
        ),
        Index(
            "ix_automation_job_one_running",
            "workspace_id",
            unique=True,
            postgresql_where=text("status='RUNNING'"),
        ),
        Index("ix_automation_jobs_queue", "status", "created_at"),
    )
    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="PENDING")
    related_id: Mapped[PyUUID | None] = mapped_column(UUID(as_uuid=True))
    lease_hash: Mapped[str | None] = mapped_column(Text, unique=True)
    worker_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automation_workers.id")
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
