"""approval request integrity

Revision ID: 006
Revises: 005
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006"
down_revision: Union[str, None] = "005"

branch_labels: Union[
    str,
    Sequence[str],
    None,
] = None

depends_on: Union[
    str,
    Sequence[str],
    None,
] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_approval_requests_status",
        "approval_requests",
        (
            "status IN ("
            "'PENDING', "
            "'APPROVED', "
            "'REJECTED', "
            "'CHANGES_REQUESTED'"
            ")"
        ),
    )

    op.create_index(
        "idx_approval_requests_action",
        "approval_requests",
        ["marketing_action_id"],
        unique=False,
    )

    op.create_index(
        "idx_approval_requests_requested_at",
        "approval_requests",
        ["requested_at"],
        unique=False,
    )

    op.create_index(
        "idx_approval_requests_one_pending",
        "approval_requests",
        ["marketing_action_id"],
        unique=True,
        postgresql_where=sa.text(
            "status = 'PENDING'"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "idx_approval_requests_one_pending",
        table_name="approval_requests",
    )

    op.drop_index(
        "idx_approval_requests_requested_at",
        table_name="approval_requests",
    )

    op.drop_index(
        "idx_approval_requests_action",
        table_name="approval_requests",
    )

    op.drop_constraint(
        "ck_approval_requests_status",
        "approval_requests",
        type_="check",
    )
