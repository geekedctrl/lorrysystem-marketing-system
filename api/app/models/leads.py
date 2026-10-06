from datetime import datetime
from typing import Any
from uuid import UUID as PyUUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.workspaces import WorkspaceOwned


# ============================================================
# Lead
# ============================================================

class Lead(WorkspaceOwned, Base):
    __tablename__ = "leads"

    __table_args__ = (
        CheckConstraint(
            "current_score BETWEEN 0 AND 100",
            name="ck_leads_current_score_range",
        ),
    )

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    company_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "companies.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    primary_contact_id: Mapped[
        PyUUID | None
    ] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "contacts.id",
            ondelete="SET NULL",
        ),
    )

    # ICP is mandatory for every lead.
    #
    # RESTRICT is used instead of SET NULL because the
    # field is now NOT NULL.
    icp_profile_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "icp_profiles.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'DISCOVERED'"),
    )

    priority: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'MEDIUM'"),
    )

    current_score: Mapped[
        int | None
    ] = mapped_column(
        Integer
    )

    discovered_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    qualified_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True)
    )

    contacted_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True)
    )

    converted_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True)
    )

    created_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


# ============================================================
# Lead Research
# ============================================================

class LeadResearch(WorkspaceOwned, Base):
    __tablename__ = "lead_research"

    __table_args__ = (
        CheckConstraint(
            "confidence BETWEEN 0 AND 100",
            name="ck_lead_research_confidence_range",
        ),
        CheckConstraint(
            """
            research_status IN (
                'PENDING',
                'RUNNING',
                'COMPLETED',
                'PARTIAL',
                'FAILED'
            )
            """,
            name="ck_lead_research_status",
        ),
    )

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    lead_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "leads.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    summary: Mapped[
        str | None
    ] = mapped_column(
        Text
    )

    pain_points: Mapped[
        list[Any]
    ] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )

    buying_signals: Mapped[
        list[Any]
    ] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )

    company_facts: Mapped[
        dict[str, Any]
    ] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    confidence: Mapped[
        int | None
    ] = mapped_column(
        Integer
    )

    research_status: Mapped[
        str
    ] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'PENDING'"),
    )

    model_provider: Mapped[
        str | None
    ] = mapped_column(
        Text
    )

    model_name: Mapped[
        str | None
    ] = mapped_column(
        Text
    )

    raw_output: Mapped[
        dict[str, Any] | list[Any] | None
    ] = mapped_column(
        JSONB
    )

    started_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True)
    )

    completed_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True)
    )

    # Legacy field retained temporarily for migration
    # compatibility with research rows created before
    # the lifecycle API was introduced.
    researched_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True)
    )

    created_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


# ============================================================
# Research Source
# ============================================================

class ResearchSource(WorkspaceOwned, Base):
    __tablename__ = "research_sources"

    __table_args__ = (
        CheckConstraint(
            "confidence BETWEEN 0 AND 100",
            name="ck_research_sources_confidence_range",
        ),
    )

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    research_id: Mapped[
        PyUUID
    ] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "lead_research.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    source_type: Mapped[
        str | None
    ] = mapped_column(
        Text
    )

    url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    title: Mapped[
        str | None
    ] = mapped_column(
        Text
    )

    evidence: Mapped[
        str | None
    ] = mapped_column(
        Text
    )

    confidence: Mapped[
        int | None
    ] = mapped_column(
        Integer
    )

    observed_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True)
    )

    created_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


# ============================================================
# Lead Score
# ============================================================

class LeadScore(WorkspaceOwned, Base):
    __tablename__ = "lead_scores"

    __table_args__ = (
        CheckConstraint(
            "total_score BETWEEN 0 AND 100",
            name="ck_lead_scores_total_score_range",
        ),
    )

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    lead_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "leads.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    total_score: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    score_breakdown: Mapped[
        dict[str, Any]
    ] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    scoring_version: Mapped[
        str
    ] = mapped_column(
        Text,
        nullable=False,
    )

    rationale: Mapped[
        str | None
    ] = mapped_column(
        Text
    )

    is_current: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )

    created_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


# ============================================================
# Product Match
# ============================================================

class ProductMatch(WorkspaceOwned, Base):
    __tablename__ = "product_matches"

    __table_args__ = (
        CheckConstraint(
            "fit_score BETWEEN 0 AND 100",
            name="ck_product_matches_fit_score_range",
        ),
    )

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    lead_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "leads.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    product_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "products.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    fit_score: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    rationale: Mapped[
        str | None
    ] = mapped_column(
        Text
    )

    created_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


# ============================================================
# Indexes
# ============================================================

Index(
    "idx_leads_company_id",
    Lead.company_id,
)


Index(
    "idx_leads_status",
    Lead.status,
)


Index(
    "idx_leads_current_score",
    Lead.current_score.desc(),
)


# Prevent more than one active lead for the same:
#
# company_id + icp_profile_id
#
# Terminal leads are intentionally excluded.
Index(
    "idx_leads_active_company_icp_unique",
    Lead.company_id,
    Lead.icp_profile_id,
    unique=True,
    postgresql_where=text(
        """
        status IN (
            'DISCOVERED',
            'RESEARCHING',
            'QUALIFIED',
            'READY_FOR_OUTREACH',
            'CONTACTED',
            'REPLIED'
        )
        """
    ),
)


Index(
    "idx_lead_research_lead_id",
    LeadResearch.lead_id,
)


Index(
    "idx_research_sources_research_id",
    ResearchSource.research_id,
)


Index(
    "idx_lead_scores_lead_id",
    LeadScore.lead_id,
)


Index(
    "idx_lead_scores_one_current",
    LeadScore.lead_id,
    unique=True,
    postgresql_where=LeadScore.is_current.is_(True),
)


Index(
    "idx_product_matches_unique",
    ProductMatch.lead_id,
    ProductMatch.product_id,
    unique=True,
)

Index(
    "idx_lead_research_status",
    LeadResearch.research_status,
)
