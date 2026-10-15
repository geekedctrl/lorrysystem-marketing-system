"""Store encrypted workspace provider drafts; no worker uses these until verified."""
from alembic import op

revision = "013_provider_connections"
down_revision = "012_organizations"
branch_labels = depends_on = None


def upgrade():
    op.execute("""CREATE TABLE provider_connections (
      workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      kind varchar(8) NOT NULL CHECK (kind IN ('MODEL','SEARCH')),
      secret_ciphertext text NOT NULL,
      settings jsonb NOT NULL DEFAULT '{}'::jsonb,
      enabled boolean NOT NULL DEFAULT false,
      verified_at timestamptz,
      PRIMARY KEY (workspace_id,kind))""")
    op.execute("GRANT SELECT,INSERT,UPDATE ON provider_connections TO backend_api")
    op.execute("ALTER TABLE provider_connections ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE provider_connections FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY workspace_boundary ON provider_connections TO backend_api
      USING (workspace_id::text = current_setting('app.workspace_id',true))
      WITH CHECK (workspace_id::text = current_setting('app.workspace_id',true))""")


def downgrade():
    op.execute("DROP TABLE provider_connections")
