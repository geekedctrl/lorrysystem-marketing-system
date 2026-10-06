"""Product onboarding plans and shared workers with temporary scoped jobs."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "automation_workers",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        sa.Column("token_hash", sa.Text, nullable=False, unique=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_table(
        "product_automation_plans",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "enabled", sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        sa.Column("state", sa.Text, nullable=False, server_default="DRAFT"),
        sa.Column(
            "profile", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "configuration",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("activated_by", sa.Text),
        sa.Column("next_discovery_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "state IN ('DRAFT','CONFIGURING','ACTIVE','NEEDS_ATTENTION')",
            name="ck_product_plan_state",
        ),
    )
    op.create_table(
        "automation_jobs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="PENDING"),
        sa.Column("related_id", UUID(as_uuid=True)),
        sa.Column("lease_hash", sa.Text, unique=True),
        sa.Column(
            "worker_id", UUID(as_uuid=True), sa.ForeignKey("automation_workers.id")
        ),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "result", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("failure_reason", sa.Text),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "kind IN ('SETUP','DISCOVERY','RESEARCH','SCORING','MATCHING','DRAFTING')",
            name="ck_automation_job_kind",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','RUNNING','COMPLETED','FAILED','NEEDS_REVIEW')",
            name="ck_automation_job_status",
        ),
    )
    op.create_index(
        "ix_automation_job_related",
        "automation_jobs",
        ["workspace_id", "kind", "related_id"],
        unique=True,
        postgresql_where=sa.text("related_id IS NOT NULL"),
    )
    op.create_index(
        "ix_automation_job_one_running",
        "automation_jobs",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text("status='RUNNING'"),
    )
    op.create_index(
        "ix_automation_jobs_queue", "automation_jobs", ["status", "created_at"]
    )
    for table in ("product_automation_plans", "automation_jobs"):
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


def downgrade():
    op.drop_table("automation_jobs")
    op.drop_table("product_automation_plans")
    op.drop_table("automation_workers")
