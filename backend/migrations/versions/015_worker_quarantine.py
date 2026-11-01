"""Persist worker quarantine, bounded audited replay and operational tracing."""
from alembic import op

revision = "015_worker_quarantine"
down_revision = "014_contract_foundation"
branch_labels = depends_on = None


def upgrade():
    op.execute("""ALTER TABLE jobs
      ADD COLUMN trace_id uuid NOT NULL DEFAULT gen_random_uuid(),
      ADD COLUMN task_envelope jsonb,
      ADD COLUMN quarantine_reason varchar(80),
      ADD COLUMN quarantined_task_hash varchar(64),
      ADD COLUMN quarantined_input_hash varchar(64),
      ADD COLUMN replay_generation integer NOT NULL DEFAULT 0 CHECK(replay_generation BETWEEN 0 AND 3)""")
    # Earlier migrations used unnamed status constraints. Match only the status
    # enumeration, never the separate RUNNING/lease equivalence check.
    op.execute("""DO $$ DECLARE c record; BEGIN
      FOR c IN SELECT conname FROM pg_constraint WHERE conrelid='jobs'::regclass
        AND contype='c' AND position('NEEDS_REVIEW' in pg_get_constraintdef(oid))>0
        AND position('COMPLETED' in pg_get_constraintdef(oid))>0
      LOOP EXECUTE format('ALTER TABLE jobs DROP CONSTRAINT %I',c.conname); END LOOP;
      END $$""")
    op.execute("""ALTER TABLE jobs ADD CONSTRAINT jobs_runtime_status CHECK(status IN
      ('PENDING','RUNNING','COMPLETED','NEEDS_REVIEW','FAILED','QUARANTINED')),
      ADD CONSTRAINT jobs_quarantine_state CHECK((status='QUARANTINED')=(quarantine_reason IS NOT NULL))""")
    # Version 0 explicitly means legacy/unparseable; unknown positive contract
    # versions must be recordable when reporting a quarantined task.
    op.execute("""DO $$ DECLARE c record; BEGIN
      FOR c IN SELECT conname FROM pg_constraint WHERE conrelid='job_stage_events'::regclass
        AND contype='c' AND position('schema_version' in pg_get_constraintdef(oid))>0
      LOOP EXECUTE format('ALTER TABLE job_stage_events DROP CONSTRAINT %I',c.conname); END LOOP;
      END $$""")
    op.execute("""ALTER TABLE job_stage_events
      ADD CONSTRAINT job_event_contract_version CHECK(schema_version>=0),
      ADD CONSTRAINT job_stage_event_scope UNIQUE(workspace_id,product_line_id,job_id,id)""")
    op.execute("""CREATE TABLE job_replays (
      id uuid PRIMARY KEY, workspace_id uuid NOT NULL, product_line_id uuid NOT NULL,
      job_id uuid NOT NULL, event_id uuid NOT NULL, actor_id uuid NOT NULL REFERENCES users(id),
      idempotency_key varchar(120) NOT NULL, generation integer NOT NULL CHECK(generation BETWEEN 1 AND 3),
      previous_attempts integer NOT NULL CHECK(previous_attempts BETWEEN 0 AND 5),
      envelope_hash varchar(64) NOT NULL CHECK(envelope_hash ~ '^[0-9a-f]{64}$'),
      input_hash varchar(64) NOT NULL CHECK(input_hash ~ '^[0-9a-f]{64}$'),
      consumer_version varchar(80) NOT NULL,
      created_at timestamptz NOT NULL,
      UNIQUE(workspace_id,job_id,idempotency_key), UNIQUE(job_id,generation),
      FOREIGN KEY(workspace_id,product_line_id,job_id,event_id)
        REFERENCES job_stage_events(workspace_id,product_line_id,job_id,id))""")
    op.execute("CREATE INDEX job_replay_history ON job_replays(workspace_id,job_id,created_at)")
    op.execute("ALTER TABLE job_replays ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE job_replays FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY workspace_boundary ON job_replays TO backend_api
      USING(workspace_id::text=current_setting('app.workspace_id',true))
      WITH CHECK(workspace_id::text=current_setting('app.workspace_id',true))""")
    op.execute("GRANT SELECT,INSERT ON job_replays TO backend_api")
    op.execute("GRANT INSERT ON job_stage_events TO backend_api")
    op.execute("""CREATE TRIGGER job_replays_immutable BEFORE UPDATE ON job_replays
      FOR EACH ROW EXECUTE FUNCTION worker_history_immutable()""")
    # Replay must validate pinned line context under a lock, without granting
    # the API the ability to edit settings as part of this checkpoint.
    op.execute("GRANT EXECUTE ON FUNCTION worker_lock_product_line(uuid,uuid) TO backend_api")


def downgrade():
    raise RuntimeError("Keep worker quarantine/replay history; use an explicit recovery migration.")
