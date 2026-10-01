"""marketing actions constraints

Revision ID: 005
Revises: d62d40479f83
"""

from typing import Sequence, Union

from alembic import op


revision: str = "005"
down_revision: Union[str, None] = (
    "d62d40479f83"
)
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
        "ck_marketing_actions_channel",
        "marketing_actions",
        (
            "channel IN ("
            "'EMAIL', "
            "'LINKEDIN', "
            "'FACEBOOK', "
            "'INSTAGRAM', "
            "'X'"
            ")"
        ),
    )

    op.create_check_constraint(
        "ck_marketing_actions_action_type",
        "marketing_actions",
        (
            "action_type IN ("
            "'EMAIL', "
            "'FOLLOW_UP', "
            "'POST', "
            "'COMMENT', "
            "'DIRECT_MESSAGE'"
            ")"
        ),
    )

    op.create_check_constraint(
        "ck_marketing_actions_status",
        "marketing_actions",
        (
            "status IN ("
            "'DRAFT', "
            "'PENDING_APPROVAL', "
            "'APPROVED', "
            "'QUEUED', "
            "'SENT', "
            "'PUBLISHED', "
            "'REJECTED', "
            "'FAILED', "
            "'CANCELLED'"
            ")"
        ),
    )

    op.create_check_constraint(
        (
            "ck_marketing_actions_"
            "channel_action_pair"
        ),
        "marketing_actions",
        (
            "("
            "channel = 'EMAIL' "
            "AND action_type IN "
            "('EMAIL', 'FOLLOW_UP')"
            ") OR ("
            "channel = 'LINKEDIN' "
            "AND action_type IN "
            "('POST', 'COMMENT', "
            "'DIRECT_MESSAGE')"
            ") OR ("
            "channel IN "
            "('FACEBOOK', "
            "'INSTAGRAM', 'X') "
            "AND action_type = 'POST'"
            ")"
        ),
    )


def downgrade() -> None:
    op.drop_constraint(
        (
            "ck_marketing_actions_"
            "channel_action_pair"
        ),
        "marketing_actions",
        type_="check",
    )

    op.drop_constraint(
        "ck_marketing_actions_status",
        "marketing_actions",
        type_="check",
    )

    op.drop_constraint(
        "ck_marketing_actions_action_type",
        "marketing_actions",
        type_="check",
    )

    op.drop_constraint(
        "ck_marketing_actions_channel",
        "marketing_actions",
        type_="check",
    )
