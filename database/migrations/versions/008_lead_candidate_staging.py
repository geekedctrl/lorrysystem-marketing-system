"""lead candidate staging

Revision ID: 008
Revises: 007
Create Date: 2026-09-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ACTIVE_CANDIDATE_STATUSES = """
status IN (
    'NEW',
    'READY_FOR_REVIEW',
    'NEEDS_REVIEW'
)
"""


def upgrade() -> None:
    op.create_table(
        "lead_candidates",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Text(),
            server_default=sa.text("'NEW'"),
            nullable=False,
        ),
        sa.Column("company_name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column("website_url", sa.Text(), nullable=True),
        sa.Column("normalized_website", sa.Text(), nullable=True),
        sa.Column("domain", sa.Text(), nullable=True),
        sa.Column("industry", sa.Text(), nullable=True),
        sa.Column("country_code", sa.CHAR(length=2), nullable=True),
        sa.Column("state", sa.Text(), nullable=True),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("contact_name", sa.Text(), nullable=True),
        sa.Column("job_title", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("linkedin_url", sa.Text(), nullable=True),
        sa.Column(
            "suggested_icp_profile_id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "icp_confidence",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "icp_reasoning",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "fleet_clues",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "buying_signals",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("source_summary", sa.Text(), nullable=True),
        sa.Column("existing_company_id", sa.UUID(), nullable=True),
        sa.Column("accepted_lead_id", sa.UUID(), nullable=True),
        sa.Column("duplicate_lead_id", sa.UUID(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
            "icp_confidence BETWEEN 0.0 AND 1.0",
            name="ck_lead_candidates_icp_confidence_range",
        ),
        sa.ForeignKeyConstraint(
            ["suggested_icp_profile_id"],
            ["icp_profiles.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["existing_company_id"],
            ["companies.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["accepted_lead_id"],
            ["leads.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["duplicate_lead_id"],
            ["leads.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "idx_lead_candidates_status",
        "lead_candidates",
        ["status"],
        unique=False,
    )
    op.create_index(
        "idx_lead_candidates_created_at",
        "lead_candidates",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "idx_lead_candidates_normalized_name",
        "lead_candidates",
        ["normalized_name"],
        unique=False,
    )
    op.create_index(
        "idx_lead_candidates_existing_company",
        "lead_candidates",
        ["existing_company_id"],
        unique=False,
    )
    op.create_index(
        "idx_lead_candidates_active_domain_unique",
        "lead_candidates",
        ["domain"],
        unique=True,
        postgresql_where=sa.text(
            "domain IS NOT NULL AND " + ACTIVE_CANDIDATE_STATUSES
        ),
    )
    op.create_index(
        "idx_lead_candidates_active_website_unique",
        "lead_candidates",
        ["normalized_website"],
        unique=True,
        postgresql_where=sa.text(
            "normalized_website IS NOT NULL AND "
            + ACTIVE_CANDIDATE_STATUSES
        ),
    )

    op.create_table(
        "lead_candidate_sources",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("candidate_id", sa.UUID(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("source_query", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "discovered_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
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
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["lead_candidates.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_id",
            "url",
            name="uq_lead_candidate_sources_candidate_url",
        ),
    )

    op.create_index(
        "idx_lead_candidate_sources_candidate",
        "lead_candidate_sources",
        ["candidate_id"],
        unique=False,
    )
    op.create_index(
        "idx_lead_candidate_sources_discovered_at",
        "lead_candidate_sources",
        ["discovered_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_lead_candidate_sources_discovered_at",
        table_name="lead_candidate_sources",
    )
    op.drop_index(
        "idx_lead_candidate_sources_candidate",
        table_name="lead_candidate_sources",
    )
    op.drop_table("lead_candidate_sources")

    op.drop_index(
        "idx_lead_candidates_active_website_unique",
        table_name="lead_candidates",
    )
    op.drop_index(
        "idx_lead_candidates_active_domain_unique",
        table_name="lead_candidates",
    )
    op.drop_index(
        "idx_lead_candidates_existing_company",
        table_name="lead_candidates",
    )
    op.drop_index(
        "idx_lead_candidates_normalized_name",
        table_name="lead_candidates",
    )
    op.drop_index(
        "idx_lead_candidates_created_at",
        table_name="lead_candidates",
    )
    op.drop_index(
        "idx_lead_candidates_status",
        table_name="lead_candidates",
    )
    op.drop_table("lead_candidates")
