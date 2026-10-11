"""Enforce pending initial approvals and immutable snapshots in PostgreSQL."""

from alembic import op

revision = "004_approval_snapshot_guard"
down_revision = "003_native_preparation"
branch_labels = depends_on = None


def upgrade():
    op.execute(
        """CREATE FUNCTION guard_approval_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='INSERT' AND NEW.status <> 'PENDING' THEN
        RAISE EXCEPTION 'Approval must start pending human review';
      END IF;
      IF TG_OP='UPDATE' AND (NEW.snapshot IS DISTINCT FROM OLD.snapshot OR NEW.run_id IS DISTINCT FROM OLD.run_id OR NEW.workspace_id IS DISTINCT FROM OLD.workspace_id) THEN
        RAISE EXCEPTION 'Approval snapshot and ownership are immutable';
      END IF;
      RETURN NEW;
    END $$"""
    )
    op.execute(
        "CREATE TRIGGER immutable_approval_snapshot BEFORE INSERT OR UPDATE ON approvals FOR EACH ROW EXECUTE FUNCTION guard_approval_snapshot()"
    )


def downgrade():
    op.execute("DROP TRIGGER immutable_approval_snapshot ON approvals")
    op.execute("DROP FUNCTION guard_approval_snapshot()")
