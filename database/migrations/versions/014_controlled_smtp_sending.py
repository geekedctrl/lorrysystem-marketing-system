"""Workspace sender credentials, explicit delivery attempts and suppressions."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def base():
    return [
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    ]


def upgrade():
    op.create_table(
        "sender_accounts",
        *base(),
        *[
            sa.Column(name, sa.Text, nullable=False)
            for name in (
                "name",
                "from_email",
                "from_name",
                "host",
                "security",
                "username",
                "password_ciphertext",
            )
        ],
        sa.Column("port", sa.Integer, nullable=False),
        sa.Column(
            "enabled", sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("security IN ('STARTTLS','TLS')", name="ck_sender_security"),
        sa.CheckConstraint("port IN (465,587)", name="ck_sender_port"),
    )
    op.create_table(
        "delivery_attempts",
        *base(),
        sa.Column(
            "action_id",
            UUID(as_uuid=True),
            sa.ForeignKey("marketing_actions.id"),
            nullable=False,
        ),
        sa.Column(
            "sender_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sender_accounts.id"),
            nullable=False,
        ),
        sa.Column("idempotency_key", UUID(as_uuid=True), nullable=False),
        *[
            sa.Column(name, sa.Text, nullable=False)
            for name in ("recipient", "message_id", "status", "requested_by")
        ],
        sa.Column("failure_reason", sa.Text),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("action_id"),
        sa.UniqueConstraint("workspace_id", "idempotency_key"),
        sa.CheckConstraint(
            "status IN ('SENDING','ACCEPTED','FAILED','UNCERTAIN')",
            name="ck_delivery_status",
        ),
    )
    op.create_table(
        "email_suppressions",
        *base(),
        sa.Column("email", sa.Text, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.UniqueConstraint("workspace_id", "email"),
    )
    for table in ("sender_accounts", "delivery_attempts", "email_suppressions"):
        op.create_unique_constraint(
            f"uq_{table}_workspace_id_id", table, ["workspace_id", "id"]
        )
        op.create_index(f"ix_{table}_workspace_id", table, ["workspace_id"])
        op.execute(
            f"GRANT SELECT,INSERT,UPDATE,DELETE ON {table} TO marketing_workspace_runtime"
        )
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        predicate = (
            "workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid"
        )
        op.execute(
            f"CREATE POLICY workspace_isolation ON {table} USING ({predicate}) WITH CHECK ({predicate})"
        )
    for column, parent in (
        ("action_id", "marketing_actions"),
        ("sender_id", "sender_accounts"),
    ):
        op.create_foreign_key(
            f"fk_delivery_attempts_{column}_workspace",
            "delivery_attempts",
            parent,
            ["workspace_id", column],
            ["workspace_id", "id"],
            deferrable=True,
            initially="DEFERRED",
        )


def downgrade():
    for table in ("email_suppressions", "delivery_attempts", "sender_accounts"):
        op.drop_table(table)
