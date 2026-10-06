from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID as PyUUID

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.workspaces import WorkspaceOwned


ACTIVE_CANDIDATE_STATUSES_SQL = """
status IN (
    'NEW',
    'READY_FOR_REVIEW',
    'NEEDS_REVIEW'
)
"""


class LeadCandidate(WorkspaceOwned, Base):
    __tablename__ = "lead_candidates"

    __table_args__ = (
        CheckConstraint(
            """
            status IN (
                'NEW',
                'READY_FOR_REVIEW',
                'NEEDS_REVIEW',
                'ACCEPTED',
                'REJECTED',
                'DUPLICATE',
                'FAILED'
            )
            """,
            name="ck_lead_candidates_status",
        ),
        CheckConstraint(
            "icp_confidence BETWEEN 0.0 AND 1.0",
            name="ck_lead_candidates_icp_confidence_range",
        ),
    )

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'NEW'"),
    )

    company_name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[str] = mapped_column(Text, nullable=False)
    website_url: Mapped[str | None] = mapped_column(Text)
    normalized_website: Mapped[str | None] = mapped_column(Text)
    domain: Mapped[str | None] = mapped_column(Text)
    industry: Mapped[str | None] = mapped_column(Text)
    country_code: Mapped[str | None] = mapped_column(CHAR(2))
    state: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)

    contact_name: Mapped[str | None] = mapped_column(Text)
    job_title: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    linkedin_url: Mapped[str | None] = mapped_column(Text)

    suggested_icp_profile_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("icp_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )

    icp_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    icp_reasoning: Mapped[str] = mapped_column(Text, nullable=False)

    fleet_clues: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )

    buying_signals: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )

    source_summary: Mapped[str | None] = mapped_column(Text)

    existing_company_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="SET NULL"),
    )

    accepted_lead_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="SET NULL"),
    )

    duplicate_lead_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="SET NULL"),
    )

    failure_reason: Mapped[str | None] = mapped_column(Text)
    review_notes: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    sources: Mapped[list["LeadCandidateSource"]] = relationship(
        back_populates="candidate",
        foreign_keys='LeadCandidateSource.candidate_id',
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class LeadCandidateSource(WorkspaceOwned, Base):
    __tablename__ = "lead_candidate_sources"

    __table_args__ = (
        CheckConstraint(
            """
            source_type IN (
                'SEARCH_RESULT',
                'COMPANY_WEBSITE',
                'PUBLIC_DIRECTORY',
                'NEWS',
                'RSS',
                'PUBLIC_PAGE'
            )
            """,
            name="ck_lead_candidate_sources_type",
        ),
        UniqueConstraint(
            "candidate_id",
            "url",
            name="uq_lead_candidate_sources_candidate_url",
        ),
    )

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    candidate_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lead_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )

    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    source_query: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    candidate: Mapped[LeadCandidate] = relationship(
        back_populates="sources",
        foreign_keys=[candidate_id],
    )


Index("idx_lead_candidates_status", LeadCandidate.status)
Index("idx_lead_candidates_created_at", LeadCandidate.created_at)
Index("idx_lead_candidates_normalized_name", LeadCandidate.normalized_name)
Index("idx_lead_candidates_existing_company", LeadCandidate.existing_company_id)

Index(
    "idx_lead_candidates_active_domain_unique",
    LeadCandidate.workspace_id,
    LeadCandidate.domain,
    unique=True,
    postgresql_where=text(
        "domain IS NOT NULL AND " + ACTIVE_CANDIDATE_STATUSES_SQL
    ),
)

Index(
    "idx_lead_candidates_active_website_unique",
    LeadCandidate.workspace_id,
    LeadCandidate.normalized_website,
    unique=True,
    postgresql_where=text(
        "normalized_website IS NOT NULL AND "
        + ACTIVE_CANDIDATE_STATUSES_SQL
    ),
)

Index(
    "idx_lead_candidate_sources_candidate",
    LeadCandidateSource.candidate_id,
)

Index(
    "idx_lead_candidate_sources_discovered_at",
    LeadCandidateSource.discovered_at,
)
