"""Organization ownership for existing and new native workspaces."""
from alembic import op

revision = "012_organizations"
down_revision = "011_executor_ownership_cleanup"
branch_labels = depends_on = None


def upgrade():
    op.execute("CREATE TABLE organizations (id uuid PRIMARY KEY, name varchar(120) NOT NULL)")
    op.execute("CREATE TABLE organization_memberships (organization_id uuid NOT NULL REFERENCES organizations(id), user_id uuid NOT NULL REFERENCES users(id), role varchar(12) NOT NULL CHECK (role IN ('OWNER','ADMIN','MEMBER')), PRIMARY KEY (organization_id,user_id))")
    op.execute("ALTER TABLE workspaces ADD COLUMN organization_id uuid REFERENCES organizations(id)")
    op.execute("ALTER TABLE workspaces ADD COLUMN description text NOT NULL DEFAULT ''")
    # Each existing workspace gets its own organization. Existing workspace roles remain intact.
    op.execute("INSERT INTO organizations(id,name) SELECT id,name FROM workspaces")
    op.execute("UPDATE workspaces SET organization_id=id WHERE organization_id IS NULL")
    op.execute("""INSERT INTO organization_memberships(organization_id,user_id,role)
        SELECT w.id, COALESCE((SELECT id FROM users WHERE platform_admin AND active ORDER BY id LIMIT 1),
            (SELECT user_id FROM memberships WHERE workspace_id=w.id AND role='ADMIN' ORDER BY user_id LIMIT 1)), 'OWNER'
        FROM workspaces w WHERE EXISTS (SELECT 1 FROM users WHERE platform_admin AND active)
           OR EXISTS (SELECT 1 FROM memberships WHERE workspace_id=w.id AND role='ADMIN')""")
    op.execute("ALTER TABLE workspaces ALTER COLUMN organization_id SET NOT NULL")
    op.execute("CREATE INDEX ix_workspaces_organization_id ON workspaces(organization_id)")
    op.execute("CREATE TABLE workspace_creations (organization_id uuid NOT NULL REFERENCES organizations(id), user_id uuid NOT NULL REFERENCES users(id), idempotency_key varchar(120) NOT NULL, workspace_id uuid NOT NULL REFERENCES workspaces(id), request_hash varchar(64) NOT NULL, PRIMARY KEY (organization_id,user_id,idempotency_key))")
    op.execute("CREATE TABLE invitations (id uuid PRIMARY KEY, token_hash varchar(64) NOT NULL UNIQUE, organization_id uuid NOT NULL REFERENCES organizations(id), workspace_id uuid REFERENCES workspaces(id), email varchar(254) NOT NULL, role varchar(12) NOT NULL, expires_at timestamptz NOT NULL, accepted_at timestamptz)")
    op.execute("CREATE UNIQUE INDEX invitations_pending_unique ON invitations (organization_id,coalesce(workspace_id,organization_id),email) WHERE accepted_at IS NULL")
    op.execute("GRANT SELECT,INSERT,UPDATE ON organizations,organization_memberships TO backend_api")
    op.execute("GRANT SELECT,INSERT ON workspace_creations TO backend_api")
    op.execute("GRANT SELECT,INSERT,UPDATE ON invitations TO backend_api")
    op.execute("GRANT UPDATE ON workspaces,users TO backend_api")


def downgrade():
    op.execute("DROP TABLE invitations")
    op.execute("DROP TABLE workspace_creations")
    op.execute("DROP INDEX ix_workspaces_organization_id")
    op.execute("ALTER TABLE workspaces DROP COLUMN organization_id")
    op.execute("ALTER TABLE workspaces DROP COLUMN description")
    op.execute("DROP TABLE organization_memberships")
    op.execute("DROP TABLE organizations")
