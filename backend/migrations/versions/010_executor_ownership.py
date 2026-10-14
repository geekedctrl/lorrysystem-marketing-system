"""Coexistence ownership and migration audit ledger."""
from alembic import op

revision = "010_executor_ownership"
down_revision = "009_native_sending"
branch_labels = depends_on = None


def upgrade():
    op.execute("""CREATE TABLE executor_ownership (
      workspace_id uuid NOT NULL REFERENCES workspaces(id),
      capability varchar(16) NOT NULL CHECK (capability IN ('SETUP','DISCOVERY','PREPARATION','SENDING')),
      owner varchar(8) NOT NULL DEFAULT 'N8N' CHECK (owner IN ('N8N','PYTHON')),
      state varchar(8) NOT NULL DEFAULT 'ACTIVE' CHECK (state IN ('ACTIVE','DRAINING')),
      version integer NOT NULL DEFAULT 1 CHECK (version > 0),
      actor_id uuid REFERENCES users(id), changed_at timestamptz NOT NULL DEFAULT now(),
      rollback_deadline timestamptz, PRIMARY KEY(workspace_id,capability))""")
    op.execute("""INSERT INTO executor_ownership(workspace_id,capability)
      SELECT id, capability FROM workspaces CROSS JOIN
      (VALUES ('SETUP'),('DISCOVERY'),('PREPARATION'),('SENDING')) AS c(capability)""")
    op.execute("""CREATE FUNCTION seed_executor_ownership() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
      BEGIN INSERT INTO executor_ownership(workspace_id,capability)
        SELECT NEW.id, capability FROM (VALUES ('SETUP'),('DISCOVERY'),('PREPARATION'),('SENDING')) c(capability);
        RETURN NEW; END $$""")
    op.execute("CREATE TRIGGER seed_executor_ownership AFTER INSERT ON workspaces FOR EACH ROW EXECUTE FUNCTION seed_executor_ownership()")
    op.execute("""CREATE TABLE executor_ownership_events (
      id bigserial PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspaces(id),
      capability varchar(16) NOT NULL, prior_owner varchar(8) NOT NULL, prior_state varchar(8) NOT NULL,
      owner varchar(8) NOT NULL, state varchar(8) NOT NULL, version integer NOT NULL,
      actor_id uuid NOT NULL REFERENCES users(id), changed_at timestamptz NOT NULL DEFAULT now())""")
    op.execute("""CREATE TABLE legacy_identity_map (
      source_system varchar(32) NOT NULL, entity_type varchar(40) NOT NULL,
      legacy_id varchar(200) NOT NULL, native_id uuid NOT NULL,
      source_fingerprint varchar(64) NOT NULL, migrated_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY(source_system,entity_type,legacy_id), UNIQUE(source_system,entity_type,native_id))""")
    op.execute("""CREATE TABLE migration_runs (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), mode varchar(16) NOT NULL,
      status varchar(16) NOT NULL, source_fingerprint varchar(64) NOT NULL,
      counts jsonb NOT NULL DEFAULT '{}'::jsonb, differences jsonb NOT NULL DEFAULT '[]'::jsonb,
      started_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz)""")
    op.execute("GRANT SELECT ON executor_ownership TO backend_api,backend_worker")
    op.execute("GRANT UPDATE ON executor_ownership TO backend_api")
    op.execute("GRANT INSERT ON executor_ownership_events TO backend_api")
    op.execute("GRANT USAGE ON SEQUENCE executor_ownership_events_id_seq TO backend_api")
    op.execute("GRANT SELECT ON migration_runs,legacy_identity_map TO backend_api")


def downgrade():
    raise RuntimeError("Ownership and migration audit history require an explicit recovery migration")
