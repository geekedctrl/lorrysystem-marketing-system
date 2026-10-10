from datetime import datetime
from uuid import UUID as PyUUID
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.models.workspaces import WorkspaceOwned


class CampaignProposal(WorkspaceOwned, Base):
    __tablename__ = 'campaign_proposals'
    __table_args__ = (
        UniqueConstraint('workspace_id', 'idempotency_key'),
        CheckConstraint("status IN ('DRAFT','REVIEWED','REJECTED')", name='ck_campaign_proposal_status'),
        CheckConstraint('version > 0', name='ck_campaign_proposal_version'),
        CheckConstraint("provider = 'mock'", name='ck_campaign_proposal_provider'),
    )
    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()'))
    lead_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey('leads.id', ondelete='CASCADE'), nullable=False)
    research_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey('lead_research.id'), nullable=False)
    idempotency_key: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default='DRAFT')
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    provider: Mapped[str] = mapped_column(Text, nullable=False, default='mock')
    strategy: Mapped[dict] = mapped_column(JSONB, nullable=False)
    context_hash: Mapped[str] = mapped_column(Text, nullable=False)
    review_notes: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    @property
    def estimated_cost_usd(self):
        return 0

    @property
    def actual_cost_usd(self):
        return 0
