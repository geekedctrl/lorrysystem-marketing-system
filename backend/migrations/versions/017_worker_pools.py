"""Typed delivery routing and append-only delivery diagnostics."""
from alembic import op

revision = "017_worker_pools"
down_revision = "016_product_lines"
branch_labels = depends_on = None


def upgrade():
    # Existing deliveries are email; preserve every snapshot and decision.
    op.execute("ALTER TABLE deliveries ADD COLUMN channel varchar(24) NOT NULL DEFAULT 'EMAIL', ADD COLUMN trace_id uuid NOT NULL DEFAULT gen_random_uuid()")
    op.execute("ALTER TABLE deliveries ALTER COLUMN sender_id DROP NOT NULL")
    op.execute("""ALTER TABLE deliveries ADD CONSTRAINT delivery_channel_allowed CHECK(channel IN ('EMAIL','LINKEDIN','MESSAGING')),
      ADD CONSTRAINT email_sender_required CHECK(channel<>'EMAIL' OR sender_id IS NOT NULL),
      ADD CONSTRAINT delivery_channel_snapshot CHECK(snapshot->>'channel'=channel),
      ADD CONSTRAINT deliveries_scoped_identity UNIQUE(workspace_id,product_line_id,id)""")
    op.execute("""CREATE FUNCTION delivery_routing_immutable() RETURNS trigger LANGUAGE plpgsql
      SET search_path=pg_catalog,public AS $$ BEGIN
      IF NEW.channel IS DISTINCT FROM OLD.channel OR NEW.trace_id IS DISTINCT FROM OLD.trace_id
        OR NEW.product_line_id IS DISTINCT FROM OLD.product_line_id
      THEN RAISE EXCEPTION 'Delivery routing is immutable'; END IF; RETURN NEW; END $$""")
    op.execute("REVOKE ALL ON FUNCTION delivery_routing_immutable() FROM PUBLIC")
    op.execute("CREATE TRIGGER delivery_route_guard BEFORE UPDATE ON deliveries FOR EACH ROW EXECUTE FUNCTION delivery_routing_immutable()")
    op.execute("ALTER TABLE native_delivery_attempts ADD CONSTRAINT attempt_delivery_identity UNIQUE(workspace_id,product_line_id,delivery_id,id)")
    op.execute("""CREATE TABLE delivery_events (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id uuid NOT NULL,
      product_line_id uuid NOT NULL,delivery_id uuid NOT NULL,attempt_id uuid NOT NULL,
      event varchar(30) NOT NULL CHECK(event IN ('CLAIM','COMPLETION','FAILURE','LEASE_LOSS')),
      pool varchar(30) NOT NULL CHECK(pool IN ('EMAIL','SOCIAL','MESSAGING')),
      channel varchar(24) NOT NULL CHECK(channel IN ('EMAIL','LINKEDIN','MESSAGING')),
      trace_id uuid NOT NULL,attempt integer NOT NULL CHECK(attempt BETWEEN 1 AND 3),
      schema_version integer NOT NULL DEFAULT 1 CHECK(schema_version=1),
      error_code varchar(80),duration_ms integer CHECK(duration_ms>=0),created_at timestamptz NOT NULL DEFAULT now(),
      FOREIGN KEY(workspace_id,product_line_id,delivery_id) REFERENCES deliveries(workspace_id,product_line_id,id),
      FOREIGN KEY(workspace_id,product_line_id,delivery_id,attempt_id) REFERENCES native_delivery_attempts(workspace_id,product_line_id,delivery_id,id),
      CHECK(pool=CASE channel WHEN 'EMAIL' THEN 'EMAIL' WHEN 'LINKEDIN' THEN 'SOCIAL' ELSE 'MESSAGING' END))""")
    op.execute("CREATE INDEX delivery_events_history ON delivery_events(workspace_id,delivery_id,created_at,id)")
    op.execute("ALTER TABLE delivery_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE delivery_events FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY workspace_boundary ON delivery_events TO backend_api
      USING(workspace_id::text=current_setting('app.workspace_id',true))""")
    op.execute("GRANT SELECT ON delivery_events TO backend_api")
    op.execute("GRANT SELECT,INSERT ON delivery_events TO backend_worker")
    op.execute("CREATE TRIGGER delivery_events_immutable BEFORE UPDATE ON delivery_events FOR EACH ROW EXECUTE FUNCTION worker_history_immutable()")
    op.execute("CREATE INDEX ready_stage_pool ON jobs(kind,available_at,created_at,id) WHERE status='PENDING'")
    op.execute("CREATE INDEX queued_delivery_channel ON deliveries(channel,product_line_id,id) WHERE status IN ('QUEUED','SENDING')")


def downgrade():
    raise RuntimeError("Preserve delivery routing and audit history; use an explicit forward recovery migration")
