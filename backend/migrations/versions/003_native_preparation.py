"""Native discovery and staged preparation, with isolated immutable approvals."""

from alembic import op

revision = "003_native_preparation"
down_revision = "002_runtime_roles"
branch_labels = depends_on = None


def upgrade():
    statements = [
        "ALTER TABLE workspaces ADD COLUMN automation_enabled boolean NOT NULL DEFAULT false, ADD COLUMN automation jsonb NOT NULL DEFAULT '{}', ADD COLUMN next_discovery_at timestamptz",
        """CREATE TABLE preparation_runs (
            id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspaces(id),
            lead_id uuid NOT NULL, context_hash varchar(64) NOT NULL, snapshot jsonb NOT NULL,
            status varchar(24) NOT NULL, stop_reason varchar(80), results jsonb NOT NULL,
            created_at timestamptz NOT NULL,
            UNIQUE(workspace_id,id), FOREIGN KEY(workspace_id,lead_id) REFERENCES leads(workspace_id,id),
            CHECK(status IN ('PREPARING','NEEDS_REVIEW','PENDING_APPROVAL','APPROVED','REJECTED','CHANGES_REQUESTED','FAILED','STALE')))""",
        "CREATE UNIQUE INDEX one_preparing_run ON preparation_runs(workspace_id,lead_id) WHERE status='PREPARING'",
        "ALTER TABLE jobs ALTER COLUMN lead_id DROP NOT NULL, ADD COLUMN run_id uuid, ADD COLUMN managed boolean NOT NULL DEFAULT false",
        "ALTER TABLE jobs ADD UNIQUE(workspace_id,id), ADD UNIQUE(run_id,kind), ADD FOREIGN KEY(workspace_id,run_id) REFERENCES preparation_runs(workspace_id,id)",
        "ALTER TABLE jobs ADD CHECK(kind IN ('SETUP','DISCOVERY','RESEARCH','CONTACT_SEARCH','SCORING','MATCHING','DRAFTING'))",
        "ALTER TABLE jobs ADD CONSTRAINT job_scope CHECK((kind IN ('SETUP','DISCOVERY') AND lead_id IS NULL AND run_id IS NULL) OR (kind NOT IN ('SETUP','DISCOVERY') AND lead_id IS NOT NULL))",
        "CREATE UNIQUE INDEX one_workspace_stage ON jobs(workspace_id,kind) WHERE lead_id IS NULL AND status IN ('PENDING','RUNNING')",
        """CREATE TABLE discovery_memory (
            id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspaces(id),
            domain varchar(254) NOT NULL, candidate jsonb NOT NULL, outcome varchar(24) NOT NULL,
            created_at timestamptz NOT NULL, UNIQUE(workspace_id,domain))""",
        """CREATE TABLE provider_usage (
            id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspaces(id), job_id uuid NOT NULL,
            provider varchar(24) NOT NULL, operation varchar(120) NOT NULL, status varchar(24) NOT NULL,
            estimated_microusd integer NOT NULL CHECK(estimated_microusd>=0), usage jsonb NOT NULL,
            created_at timestamptz NOT NULL,
            FOREIGN KEY(workspace_id,job_id) REFERENCES jobs(workspace_id,id))""",
        """CREATE TABLE approvals (
            id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspaces(id), run_id uuid NOT NULL UNIQUE,
            snapshot jsonb NOT NULL, status varchar(24) NOT NULL CHECK(status IN ('PENDING','APPROVED','REJECTED','CHANGES_REQUESTED')),
            decision jsonb NOT NULL, created_at timestamptz NOT NULL,
            FOREIGN KEY(workspace_id,run_id) REFERENCES preparation_runs(workspace_id,id))""",
    ]
    for statement in statements:
        op.execute(statement)
    for table in (
        "preparation_runs",
        "discovery_memory",
        "provider_usage",
        "approvals",
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY workspace_boundary ON {table} TO backend_api USING (workspace_id::text=current_setting('app.workspace_id',true)) WITH CHECK (workspace_id::text=current_setting('app.workspace_id',true))"
        )
    op.execute(
        "GRANT UPDATE(automation_enabled,automation,next_discovery_at) ON workspaces TO backend_api,backend_worker"
    )
    op.execute(
        "GRANT SELECT,INSERT,UPDATE ON preparation_runs,discovery_memory TO backend_api,backend_worker"
    )
    op.execute("GRANT SELECT ON provider_usage,approvals TO backend_api")
    op.execute("GRANT UPDATE(status,decision) ON approvals TO backend_api")
    op.execute("GRANT SELECT,INSERT,UPDATE ON provider_usage TO backend_worker")
    op.execute("GRANT SELECT,INSERT ON approvals TO backend_worker")
    op.execute("GRANT SELECT,INSERT,UPDATE ON catalog,leads TO backend_worker")
    op.execute("GRANT INSERT ON jobs TO backend_worker")


def downgrade():
    raise RuntimeError(
        "Preparation/approval history must be exported before a destructive downgrade; use an explicit recovery migration."
    )
