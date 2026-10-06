"""Workspace-scoped scoring, matching and draft automation queue."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "lead_pipeline_runs",
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
        sa.Column("lead_id", UUID(as_uuid=True), nullable=False),
        sa.Column("research_id", UUID(as_uuid=True), nullable=False),
        sa.Column("contact_id", UUID(as_uuid=True), nullable=False),
        sa.Column("stage", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="PENDING"),
        sa.Column("requested_by", sa.Text, nullable=False),
        sa.Column("claimed_by", sa.Text),
        sa.Column(
            "input_snapshot",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
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
            "stage IN ('SCORING','MATCHING','DRAFTING')", name="ck_pipeline_stage"
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','RUNNING','COMPLETED','FAILED')",
            name="ck_pipeline_status",
        ),
        *[
            sa.ForeignKeyConstraint(
                ["workspace_id", column],
                [f"{parent}.workspace_id", f"{parent}.id"],
                name=f"fk_pipeline_{column}_workspace",
                ondelete="RESTRICT",
            )
            for column, parent in [
                ("lead_id", "leads"),
                ("research_id", "lead_research"),
                ("contact_id", "contacts"),
            ]
        ],
    )
    op.create_index(
        "ix_pipeline_one_active_lead",
        "lead_pipeline_runs",
        ["workspace_id", "lead_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('PENDING','RUNNING')"),
    )
    op.create_index(
        "ix_pipeline_workspace_queue",
        "lead_pipeline_runs",
        ["workspace_id", "status", "created_at"],
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON lead_pipeline_runs TO marketing_workspace_runtime"
    )
    op.execute("ALTER TABLE lead_pipeline_runs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE lead_pipeline_runs FORCE ROW LEVEL SECURITY")
    predicate = (
        "workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid"
    )
    op.execute(
        f"CREATE POLICY workspace_isolation ON lead_pipeline_runs USING ({predicate}) WITH CHECK ({predicate})"
    )


def downgrade():
    op.drop_table("lead_pipeline_runs")
