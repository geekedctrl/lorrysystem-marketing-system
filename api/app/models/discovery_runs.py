from datetime import datetime
from uuid import UUID as PyUUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.workspaces import WorkspaceOwned


class DiscoveryAutomation(WorkspaceOwned, Base):
    __tablename__ = 'discovery_automations'
    __table_args__ = (UniqueConstraint('workspace_id', name='uq_discovery_automations_workspace'),)
    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()'))
    webhook_url: Mapped[str] = mapped_column(Text, nullable=False)
    default_query: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class DiscoveryRun(WorkspaceOwned, Base):
    __tablename__ = 'discovery_runs'
    __table_args__ = (
        CheckConstraint("status IN ('QUEUED','RUNNING','COMPLETED','FAILED','TIMED_OUT')", name='ck_discovery_runs_status'),
        CheckConstraint('target_new_companies BETWEEN 1 AND 10', name='ck_discovery_runs_target'),
        Index('ix_discovery_runs_one_active', 'workspace_id', unique=True, postgresql_where=text("status IN ('QUEUED','RUNNING')")),
    )
    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()'))
    status: Mapped[str] = mapped_column(Text, nullable=False, default='QUEUED')
    query: Mapped[str] = mapped_column(Text, nullable=False)
    target_new_companies: Mapped[int] = mapped_column(Integer, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by: Mapped[str] = mapped_column(Text, nullable=False)
    claimed_by: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
