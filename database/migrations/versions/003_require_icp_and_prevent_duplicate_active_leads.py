"""require icp and prevent duplicate active leads

Revision ID: 003
Revises: 002
Create Date: 2026-09-18 11:25:45.972865
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ACTIVE_LEAD_STATUSES = """
status IN (
    'DISCOVERED',
    'RESEARCHING',
    'QUALIFIED',
    'READY_FOR_OUTREACH',
    'CONTACTED',
    'REPLIED'
)
"""


def upgrade() -> None:
    # --------------------------------------------------------
    # 1. Replace ICP foreign key
    #
    # Old:
    # ON DELETE SET NULL
    #
    # New:
    # ON DELETE RESTRICT
    # --------------------------------------------------------

    op.drop_constraint(
        "leads_icp_profile_id_fkey",
        "leads",
        type_="foreignkey",
    )

    # --------------------------------------------------------
    # 2. Make ICP mandatory for every lead
    # --------------------------------------------------------

    op.alter_column(
        "leads",
        "icp_profile_id",
        existing_type=sa.UUID(),
        nullable=False,
    )

    # --------------------------------------------------------
    # 3. Recreate ICP foreign key using RESTRICT
    # --------------------------------------------------------

    op.create_foreign_key(
        "leads_icp_profile_id_fkey",
        "leads",
        "icp_profiles",
        ["icp_profile_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # --------------------------------------------------------
    # 4. Prevent duplicate active leads
    #
    # Only one active opportunity may exist for:
    #
    # company_id + icp_profile_id
    #
    # Terminal statuses are intentionally excluded.
    # --------------------------------------------------------

    op.create_index(
        "idx_leads_active_company_icp_unique",
        "leads",
        [
            "company_id",
            "icp_profile_id",
        ],
        unique=True,
        postgresql_where=sa.text(
            ACTIVE_LEAD_STATUSES
        ),
    )


def downgrade() -> None:
    # --------------------------------------------------------
    # 1. Remove active-lead unique index
    # --------------------------------------------------------

    op.drop_index(
        "idx_leads_active_company_icp_unique",
        table_name="leads",
    )

    # --------------------------------------------------------
    # 2. Remove RESTRICT foreign key
    # --------------------------------------------------------

    op.drop_constraint(
        "leads_icp_profile_id_fkey",
        "leads",
        type_="foreignkey",
    )

    # --------------------------------------------------------
    # 3. Restore nullable ICP
    # --------------------------------------------------------

    op.alter_column(
        "leads",
        "icp_profile_id",
        existing_type=sa.UUID(),
        nullable=True,
    )

    # --------------------------------------------------------
    # 4. Restore original SET NULL foreign key
    # --------------------------------------------------------

    op.create_foreign_key(
        "leads_icp_profile_id_fkey",
        "leads",
        "icp_profiles",
        ["icp_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )
