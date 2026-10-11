"""Ordered leads and immutable human draft revisions."""

from alembic import op

revision = "006_frontend_support"
down_revision = "005_job_run_ownership"
branch_labels = depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE leads ADD COLUMN created_at timestamptz NOT NULL DEFAULT now()"
    )
    op.execute(
        "CREATE INDEX leads_workspace_order ON leads(workspace_id, created_at DESC, id DESC)"
    )
    op.execute(
        """ALTER TABLE approvals ADD COLUMN version integer NOT NULL DEFAULT 1 CHECK(version >= 1),
        ADD COLUMN parent_approval_id uuid UNIQUE, ADD COLUMN idempotency_key varchar(120),
        ADD COLUMN revision_hash varchar(64), ADD COLUMN editor_id uuid REFERENCES users(id),
        ADD CONSTRAINT approval_workspace_identity UNIQUE(workspace_id,id),
        ADD CONSTRAINT approval_revision_key UNIQUE(workspace_id,idempotency_key),
        ADD CONSTRAINT approval_revision_parent FOREIGN KEY(workspace_id,parent_approval_id) REFERENCES approvals(workspace_id,id),
        ADD CONSTRAINT revision_ownership CHECK (
          (parent_approval_id IS NULL AND version=1 AND idempotency_key IS NULL AND revision_hash IS NULL AND editor_id IS NULL)
          OR (parent_approval_id IS NOT NULL AND version>1 AND idempotency_key IS NOT NULL AND revision_hash IS NOT NULL AND editor_id IS NOT NULL))"""
    )
    op.execute("GRANT INSERT ON approvals TO backend_api")
    op.execute(
        """CREATE OR REPLACE FUNCTION guard_approval_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='INSERT' AND (NEW.status <> 'PENDING' OR NEW.decision <> '{}'::jsonb) THEN
        RAISE EXCEPTION 'Approval must start pending human review without a decision';
      END IF;
      IF TG_OP='UPDATE' AND (NEW.snapshot IS DISTINCT FROM OLD.snapshot OR NEW.run_id IS DISTINCT FROM OLD.run_id
        OR NEW.workspace_id IS DISTINCT FROM OLD.workspace_id OR NEW.version IS DISTINCT FROM OLD.version
        OR NEW.parent_approval_id IS DISTINCT FROM OLD.parent_approval_id OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
        OR NEW.revision_hash IS DISTINCT FROM OLD.revision_hash OR NEW.editor_id IS DISTINCT FROM OLD.editor_id) THEN
        RAISE EXCEPTION 'Approval snapshot, revision and ownership are immutable';
      END IF;
      RETURN NEW;
    END $$"""
    )


def downgrade():
    raise RuntimeError(
        "Export and reconcile revision history before an explicit recovery migration"
    )
