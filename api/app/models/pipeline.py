from datetime import datetime
from uuid import UUID as PyUUID
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.models.workspaces import WorkspaceOwned


class PipelineRun(WorkspaceOwned, Base):
    __tablename__ = "lead_pipeline_runs"
    __table_args__ = (
        CheckConstraint(
            "stage IN ('SCORING','MATCHING','DRAFTING')", name="ck_pipeline_stage"
        ),
        CheckConstraint(
            "status IN ('PENDING','RUNNING','COMPLETED','FAILED')",
            name="ck_pipeline_status",
        ),
        Index(
            "ix_pipeline_one_active_lead",
            "workspace_id",
            "lead_id",
            unique=True,
            postgresql_where=text("status IN ('PENDING','RUNNING')"),
        ),
        *[
            ForeignKeyConstraint(
                ["workspace_id", column],
                [f"{parent}.workspace_id", f"{parent}.id"],
                name=f"fk_pipeline_{column}_workspace",
                ondelete="RESTRICT",
            )
            for column, parent in [
                ("lead_id", "leads"),
                ("research_id", "lead_research"),
                ("contact_id", "contacts"),
            ]
        ],
    )
    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    lead_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    research_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    contact_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="PENDING")
    requested_by: Mapped[str] = mapped_column(Text, nullable=False)
    claimed_by: Mapped[str | None] = mapped_column(Text)
    input_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
