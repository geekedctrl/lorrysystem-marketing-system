"""Allow disposable workspace removal to clean ownership audit rows."""
from alembic import op

revision = "011_executor_ownership_cleanup"
down_revision = "010_executor_ownership"
branch_labels = depends_on = None


def upgrade():
    op.execute("ALTER TABLE executor_ownership DROP CONSTRAINT executor_ownership_workspace_id_fkey")
    op.execute("ALTER TABLE executor_ownership ADD CONSTRAINT executor_ownership_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE")
    op.execute("ALTER TABLE executor_ownership_events DROP CONSTRAINT executor_ownership_events_workspace_id_fkey")
    op.execute("ALTER TABLE executor_ownership_events ADD CONSTRAINT executor_ownership_events_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE")


def downgrade():
    op.execute("ALTER TABLE executor_ownership DROP CONSTRAINT executor_ownership_workspace_id_fkey")
    op.execute("ALTER TABLE executor_ownership ADD CONSTRAINT executor_ownership_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES workspaces(id)")
    op.execute("ALTER TABLE executor_ownership_events DROP CONSTRAINT executor_ownership_events_workspace_id_fkey")
    op.execute("ALTER TABLE executor_ownership_events ADD CONSTRAINT executor_ownership_events_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES workspaces(id)")
