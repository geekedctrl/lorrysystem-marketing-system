"""Separate runtime roles and forced workspace row-level policies."""

import os
from alembic import op
from psycopg import sql

revision = "002_runtime_roles"
down_revision = "c5c7e417476d"
branch_labels = None
depends_on = None


def upgrade():
    for role, bypass, variable in [
        ("backend_api", False, "API_DB_PASSWORD"),
        ("backend_worker", True, "WORKER_DB_PASSWORD"),
    ]:
        password = os.environ.get(variable)
        if not password or len(password) < 24:
            raise RuntimeError(
                "Set strong API_DB_PASSWORD and WORKER_DB_PASSWORD for migrations"
            )
        op.execute(
            f"DO $$ BEGIN CREATE ROLE {role} NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
        )
        op.execute(
            "ALTER ROLE "
            + role
            + " LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT "
            + ("BYPASSRLS" if bypass else "NOBYPASSRLS")
            + " PASSWORD "
            + sql.Literal(password).as_string()
        )
        op.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
        op.execute(f"GRANT SELECT ON alembic_version, workspaces TO {role}")
    op.execute("GRANT SELECT ON users,memberships TO backend_api")
    op.execute(
        "GRANT SELECT,INSERT,DELETE ON login_sessions,login_attempts TO backend_api"
    )
    op.execute("GRANT INSERT ON workspaces,memberships TO backend_api")
    op.execute("GRANT SELECT,INSERT,UPDATE ON catalog,leads,jobs TO backend_api")
    op.execute("GRANT SELECT,UPDATE ON jobs TO backend_worker")
    for table in ("catalog", "leads", "jobs"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY workspace_boundary ON {table} TO backend_api USING (workspace_id::text = current_setting('app.workspace_id',true)) WITH CHECK (workspace_id::text = current_setting('app.workspace_id',true))"
        )


def downgrade():
    for table in ("jobs", "leads", "catalog"):
        op.execute(f"DROP POLICY workspace_boundary ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    # Shared Postgres roles are not dropped; another database may use them.
