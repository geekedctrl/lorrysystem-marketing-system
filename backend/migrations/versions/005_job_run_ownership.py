"""Bind every managed lead job to the same lead as its preparation run."""

from alembic import op

revision = "005_job_run_ownership"
down_revision = "004_approval_snapshot_guard"
branch_labels = depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE preparation_runs ADD CONSTRAINT run_lead_identity UNIQUE(workspace_id,id,lead_id)"
    )
    op.execute(
        "ALTER TABLE jobs ADD CONSTRAINT job_run_lead FOREIGN KEY(workspace_id,run_id,lead_id) REFERENCES preparation_runs(workspace_id,id,lead_id)"
    )
    op.execute(
        "ALTER TABLE jobs ADD CONSTRAINT managed_stage_scope CHECK((managed AND (kind IN ('SETUP','DISCOVERY') OR run_id IS NOT NULL)) OR (NOT managed AND kind='RESEARCH' AND run_id IS NULL))"
    )


def downgrade():
    op.execute(
        "ALTER TABLE jobs DROP CONSTRAINT managed_stage_scope, DROP CONSTRAINT job_run_lead"
    )
    op.execute("ALTER TABLE preparation_runs DROP CONSTRAINT run_lead_identity")
