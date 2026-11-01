"""Add product-line ownership anchors and immutable contract/event storage.

Only jobs are line-scoped in this first foundation migration. Catalog and
pipeline state remain legacy workspace-scoped until the product-line patch.
Historical results and approvals are neither rewritten nor relabelled.
"""

from alembic import op

revision = "014_contract_foundation"
down_revision = "013_provider_connections"
branch_labels = depends_on = None


def upgrade():
    op.execute("""CREATE TABLE product_lines (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      code varchar(80) NOT NULL, name varchar(120) NOT NULL,
      settings jsonb NOT NULL DEFAULT '{}', paused boolean NOT NULL DEFAULT true,
      context_version integer NOT NULL DEFAULT 1 CHECK(context_version >= 1),
      context_hash varchar(64) NOT NULL CHECK(context_hash ~ '^[0-9a-f]{64}$'),
      limits jsonb NOT NULL DEFAULT jsonb_build_object('per_pool_concurrency', 1),
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(workspace_id,id), UNIQUE(workspace_id,code))""")
    op.execute("""INSERT INTO product_lines(workspace_id,code,name,settings,paused,context_hash)
      SELECT id,'DEFAULT','Default product line',automation,NOT automation_enabled,
        encode(sha256(convert_to(automation::text,'UTF8')),'hex') FROM workspaces""")
    # Legacy inserts, including fresh test fixtures, receive a default owner.
    # Security definer has a fixed search_path and is not directly executable
    # by runtime roles. It creates only the NEW workspace's default line.
    op.execute("""CREATE FUNCTION worker_default_product_line() RETURNS trigger
      LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
      BEGIN
        INSERT INTO public.product_lines(workspace_id,code,name,settings,paused,context_hash)
        VALUES(NEW.id,'DEFAULT','Default product line',NEW.automation,
          NOT NEW.automation_enabled,
          encode(sha256(convert_to(NEW.automation::text,'UTF8')),'hex'));
        RETURN NEW;
      END $$""")
    op.execute("REVOKE ALL ON FUNCTION worker_default_product_line() FROM PUBLIC")
    op.execute("""CREATE TRIGGER worker_workspace_default_line AFTER INSERT ON workspaces
      FOR EACH ROW EXECUTE FUNCTION worker_default_product_line()""")
    op.execute("ALTER TABLE jobs ADD COLUMN product_line_id uuid")
    op.execute("""UPDATE jobs j SET product_line_id=l.id FROM product_lines l
      WHERE l.workspace_id=j.workspace_id AND l.code='DEFAULT'""")
    op.execute("ALTER TABLE jobs ALTER COLUMN product_line_id SET NOT NULL")
    op.execute("""ALTER TABLE jobs ADD CONSTRAINT job_product_line_scope
      FOREIGN KEY(workspace_id,product_line_id) REFERENCES product_lines(workspace_id,id),
      ADD CONSTRAINT job_line_identity UNIQUE(workspace_id,product_line_id,id)""")
    op.execute("""CREATE FUNCTION worker_job_default_line() RETURNS trigger
      LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
      BEGIN
        IF NEW.product_line_id IS NULL THEN
          SELECT id INTO NEW.product_line_id FROM public.product_lines
          WHERE workspace_id=NEW.workspace_id AND code='DEFAULT';
        END IF;
        RETURN NEW;
      END $$""")
    op.execute("REVOKE ALL ON FUNCTION worker_job_default_line() FROM PUBLIC")
    op.execute("""CREATE TRIGGER worker_job_default_line BEFORE INSERT ON jobs
      FOR EACH ROW EXECUTE FUNCTION worker_job_default_line()""")
    op.execute("""CREATE TABLE stage_artifacts (
      id uuid PRIMARY KEY, workspace_id uuid NOT NULL, product_line_id uuid NOT NULL,
      job_id uuid NOT NULL, artifact_key varchar(120) NOT NULL,
      contract_name varchar(80) NOT NULL CHECK(contract_name IN ('discovery.candidate','research.output')),
      schema_version integer NOT NULL CHECK(schema_version IN (1,2)),
      producer_version varchar(80) NOT NULL, context_version integer NOT NULL CHECK(context_version >= 1),
      context_hash varchar(64) NOT NULL CHECK(context_hash ~ '^[0-9a-f]{64}$'),
      content_hash varchar(64) NOT NULL CHECK(content_hash ~ '^[0-9a-f]{64}$'),
      envelope jsonb NOT NULL, payload jsonb NOT NULL,
      evidence_refs jsonb NOT NULL, strategy_versions jsonb NOT NULL, input_hashes jsonb NOT NULL,
      created_at timestamptz NOT NULL,
      UNIQUE(job_id,artifact_key),
      FOREIGN KEY(workspace_id,product_line_id,job_id)
        REFERENCES jobs(workspace_id,product_line_id,id),
      CHECK(envelope->>'workspace_id'=workspace_id::text),
      CHECK(envelope->>'product_line_id'=product_line_id::text),
      CHECK(envelope->>'job_id'=job_id::text))""")
    op.execute("CREATE INDEX stage_artifact_line ON stage_artifacts(workspace_id,product_line_id,created_at)")
    op.execute("""CREATE TABLE job_stage_events (
      id uuid PRIMARY KEY, workspace_id uuid NOT NULL, product_line_id uuid NOT NULL,
      job_id uuid NOT NULL, event varchar(24) NOT NULL CHECK(event IN
        ('CLAIM','CHECKPOINT','RETRY','COMPLETION','FAILURE','LEASE_LOSS','QUARANTINE','REPLAY')),
      stage varchar(30) NOT NULL CHECK(stage IN
        ('SETUP','DISCOVERY','RESEARCH','CONTACT_SEARCH','SCORING','MATCHING','DRAFTING')),
      pool varchar(30) NOT NULL, attempt integer NOT NULL CHECK(attempt BETWEEN 0 AND 5),
      schema_version integer NOT NULL CHECK(schema_version IN (1,2)), trace_id uuid NOT NULL,
      error_code varchar(80) CHECK(error_code ~ '^[A-Z][A-Z0-9_]{0,79}$'),
      duration_ms integer CHECK(duration_ms >= 0), created_at timestamptz NOT NULL,
      FOREIGN KEY(workspace_id,product_line_id,job_id)
        REFERENCES jobs(workspace_id,product_line_id,id))""")
    op.execute("CREATE INDEX job_stage_event_history ON job_stage_events(workspace_id,job_id,created_at)")
    for table in ("product_lines", "stage_artifacts", "job_stage_events"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""CREATE POLICY workspace_boundary ON {table} TO backend_api
          USING(workspace_id::text=current_setting('app.workspace_id',true))
          WITH CHECK(workspace_id::text=current_setting('app.workspace_id',true))""")
    op.execute("GRANT SELECT ON product_lines TO backend_api,backend_worker")
    # Lock context without granting workers permission to change line settings.
    op.execute("""CREATE FUNCTION worker_lock_product_line(wid uuid,lid uuid) RETURNS boolean
      LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
      BEGIN
        PERFORM id FROM public.product_lines WHERE workspace_id=wid AND id=lid FOR SHARE;
        RETURN FOUND;
      END $$""")
    op.execute("REVOKE ALL ON FUNCTION worker_lock_product_line(uuid,uuid) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION worker_lock_product_line(uuid,uuid) TO backend_worker")
    op.execute("GRANT SELECT ON stage_artifacts,job_stage_events TO backend_api")
    op.execute("GRANT SELECT,INSERT ON stage_artifacts,job_stage_events TO backend_worker")
    # Runtime roles cannot mutate history. Also stop accidental owner UPDATEs;
    # test/maintenance owners retain DELETE for disposable database cleanup.
    op.execute("""CREATE FUNCTION worker_history_immutable() RETURNS trigger
      LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
      BEGIN RAISE EXCEPTION 'WORKER_HISTORY_IMMUTABLE'; END $$""")
    op.execute("REVOKE ALL ON FUNCTION worker_history_immutable() FROM PUBLIC")
    for table in ("stage_artifacts", "job_stage_events"):
        op.execute(f"""CREATE TRIGGER {table}_immutable BEFORE UPDATE ON {table}
          FOR EACH ROW EXECUTE FUNCTION worker_history_immutable()""")


def downgrade():
    raise RuntimeError("Preserve product-line and worker audit history; use an explicit recovery migration.")
