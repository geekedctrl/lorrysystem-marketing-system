"""Encrypted sender connections, immutable deliveries and transactional outbox."""

from alembic import op

revision = "009_native_sending"
down_revision = "008_discovery_review"
branch_labels = depends_on = None


def upgrade():
    op.execute("""CREATE TABLE sender_connections (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id uuid NOT NULL REFERENCES workspaces(id),
      name varchar(120) NOT NULL, from_email varchar(254) NOT NULL, from_name varchar(120) NOT NULL,
      host varchar(253) NOT NULL, port integer NOT NULL CHECK(port IN (465,587)),
      security varchar(12) NOT NULL CHECK(security IN ('STARTTLS','TLS')), username varchar(254) NOT NULL,
      secret_ciphertext text NOT NULL, enabled boolean NOT NULL DEFAULT false, verified_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(workspace_id,id))""")
    op.execute("""CREATE TABLE deliveries (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id uuid NOT NULL REFERENCES workspaces(id),
      approval_id uuid NOT NULL, sender_id uuid NOT NULL REFERENCES sender_connections(id), create_key varchar(120) NOT NULL,
      status varchar(24) NOT NULL DEFAULT 'PENDING_SEND_APPROVAL' CHECK(status IN ('PENDING_SEND_APPROVAL','QUEUED','SENDING','ACCEPTED','FAILED','UNCERTAIN','CANCELLED')),
      snapshot jsonb NOT NULL, requested_by uuid NOT NULL REFERENCES users(id), send_approved_by uuid REFERENCES users(id),
      send_approved_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(workspace_id,id), UNIQUE(workspace_id,approval_id), UNIQUE(workspace_id,create_key),
      FOREIGN KEY(workspace_id,approval_id) REFERENCES approvals(workspace_id,id),
      FOREIGN KEY(workspace_id,sender_id) REFERENCES sender_connections(workspace_id,id))""")
    op.execute("""CREATE TABLE native_delivery_attempts (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id uuid NOT NULL REFERENCES workspaces(id),
      delivery_id uuid NOT NULL REFERENCES deliveries(id), attempt_number integer NOT NULL CHECK(attempt_number BETWEEN 1 AND 3),
      status varchar(12) NOT NULL DEFAULT 'READY' CHECK(status IN ('READY','SENDING','ACCEPTED','FAILED','UNCERTAIN')),
      message_id varchar(320) NOT NULL, failure_code varchar(80), available_at timestamptz NOT NULL DEFAULT now(),
      lease_token varchar(64), lease_until timestamptz, created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
      UNIQUE(workspace_id,delivery_id,attempt_number), FOREIGN KEY(workspace_id,delivery_id) REFERENCES deliveries(workspace_id,id))""")
    op.execute("CREATE INDEX delivery_outbox_ready ON native_delivery_attempts(status,available_at)")
    op.execute("""CREATE TABLE native_email_suppressions (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id uuid NOT NULL REFERENCES workspaces(id),
      email varchar(254) NOT NULL, reason varchar(24) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(workspace_id,email))""")
    op.execute("""CREATE OR REPLACE FUNCTION guard_native_delivery() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP='UPDATE' AND (NEW.workspace_id IS DISTINCT FROM OLD.workspace_id OR NEW.approval_id IS DISTINCT FROM OLD.approval_id
        OR NEW.sender_id IS DISTINCT FROM OLD.sender_id OR NEW.create_key IS DISTINCT FROM OLD.create_key OR NEW.snapshot IS DISTINCT FROM OLD.snapshot
        OR NEW.requested_by IS DISTINCT FROM OLD.requested_by OR NEW.created_at IS DISTINCT FROM OLD.created_at
        OR OLD.send_approved_at IS NOT NULL AND (NEW.send_approved_at IS DISTINCT FROM OLD.send_approved_at OR NEW.send_approved_by IS DISTINCT FROM OLD.send_approved_by))
      THEN RAISE EXCEPTION 'Delivery content, recipient, sender and approvals are immutable'; END IF; RETURN NEW; END $$""")
    op.execute("CREATE TRIGGER native_delivery_immutable BEFORE UPDATE ON deliveries FOR EACH ROW EXECUTE FUNCTION guard_native_delivery()")
    for table in ("sender_connections","deliveries","native_delivery_attempts","native_email_suppressions"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY workspace_boundary ON {table} TO backend_api USING (workspace_id::text=current_setting('app.workspace_id',true)) WITH CHECK (workspace_id::text=current_setting('app.workspace_id',true))")
    op.execute("GRANT SELECT,INSERT,UPDATE ON sender_connections,deliveries,native_delivery_attempts,native_email_suppressions TO backend_api")
    op.execute("GRANT SELECT ON sender_connections TO backend_worker")
    op.execute("GRANT SELECT,UPDATE ON deliveries TO backend_worker")
    op.execute("GRANT SELECT,UPDATE ON native_delivery_attempts TO backend_worker")


def downgrade():
    raise RuntimeError("Delivery and send-approval history requires an explicit recovery migration")
