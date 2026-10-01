"""research lifecycle

Revision ID: d62d40479f83
Revises: 003
Create Date: 2026-09-18 14:13:01.930642

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d62d40479f83"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --------------------------------------------------------
    # Research lifecycle timestamps
    # --------------------------------------------------------

    op.add_column(
        "lead_research",
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.add_column(
        "lead_research",
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # --------------------------------------------------------
    # New research runs begin as PENDING
    # --------------------------------------------------------

    op.alter_column(
        "lead_research",
        "research_status",
        existing_type=sa.Text(),
        existing_nullable=False,
        server_default=sa.text("'PENDING'"),
    )

    # --------------------------------------------------------
    # Legacy researched_at
    #
    # Keep the column for compatibility, but new PENDING
    # research runs must not appear to have already been
    # researched.
    # --------------------------------------------------------

    op.alter_column(
        "lead_research",
        "researched_at",
        existing_type=postgresql.TIMESTAMP(
            timezone=True
        ),
        nullable=True,
        server_default=None,
        existing_server_default=sa.text("now()"),
    )

    # --------------------------------------------------------
    # Restrict research_status to supported lifecycle values
    # --------------------------------------------------------

    op.create_check_constraint(
        "ck_lead_research_status",
        "lead_research",
        """
        research_status IN (
            'PENDING',
            'RUNNING',
            'COMPLETED',
            'PARTIAL',
            'FAILED'
        )
        """,
    )

    # --------------------------------------------------------
    # Research status lookup index
    # --------------------------------------------------------

    op.create_index(
        "idx_lead_research_status",
        "lead_research",
        ["research_status"],
        unique=False,
    )


def downgrade() -> None:
    # --------------------------------------------------------
    # Remove new status index and constraint
    # --------------------------------------------------------

    op.drop_index(
        "idx_lead_research_status",
        table_name="lead_research",
    )

    op.drop_constraint(
        "ck_lead_research_status",
        "lead_research",
        type_="check",
    )

    # --------------------------------------------------------
    # Restore legacy research_status behavior
    # --------------------------------------------------------

    op.alter_column(
        "lead_research",
        "research_status",
        existing_type=sa.Text(),
        existing_nullable=False,
        server_default=sa.text("'COMPLETED'"),
    )

    # --------------------------------------------------------
    # Ensure researched_at can safely become NOT NULL again
    # --------------------------------------------------------

    op.execute(
        """
        UPDATE lead_research
        SET researched_at = COALESCE(
            researched_at,
            completed_at,
            started_at,
            created_at,
            now()
        )
        WHERE researched_at IS NULL
        """
    )

    op.alter_column(
        "lead_research",
        "researched_at",
        existing_type=postgresql.TIMESTAMP(
            timezone=True
        ),
        nullable=False,
        server_default=sa.text("now()"),
    )

    # --------------------------------------------------------
    # Remove lifecycle timestamps
    # --------------------------------------------------------

    op.drop_column(
        "lead_research",
        "completed_at",
    )

    op.drop_column(
        "lead_research",
        "started_at",
    )
