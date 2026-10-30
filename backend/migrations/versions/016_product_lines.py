"""Line ownership, default compatibility, context versions and execution bounds."""
from alembic import op

revision = "016_product_lines"
down_revision = "015_worker_quarantine"
branch_labels = depends_on = None


def upgrade():
    op.execute("ALTER TABLE product_lines ADD COLUMN next_discovery_at timestamptz, ADD COLUMN versioned boolean NOT NULL DEFAULT false")
    op.execute("""UPDATE product_lines l SET settings=w.automation,paused=NOT w.automation_enabled,
      next_discovery_at=w.next_discovery_at FROM workspaces w
      WHERE l.workspace_id=w.id AND l.code='DEFAULT'""")
    # Never rewrite saved results, snapshots or approval decisions.
    for table in ("catalog", "preparation_runs", "discovery_memory", "approvals", "deliveries", "native_delivery_attempts", "provider_usage"):
        op.execute(f"ALTER TABLE {table} ADD COLUMN product_line_id uuid")
        op.execute(f"""UPDATE {table} r SET product_line_id=l.id FROM product_lines l
          WHERE l.workspace_id=r.workspace_id AND l.code='DEFAULT'""")
        op.execute(f"""ALTER TABLE {table} ALTER COLUMN product_line_id SET NOT NULL,
          ADD CONSTRAINT {table}_line_owner FOREIGN KEY(workspace_id,product_line_id)
          REFERENCES product_lines(workspace_id,id)""")
    for table in ("preparation_runs", "approvals", "deliveries"):
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {table}_line_identity UNIQUE(workspace_id,product_line_id,id)")
    for table, parent, key in (("jobs", "preparation_runs", "run_id"), ("approvals", "preparation_runs", "run_id"),
        ("deliveries", "approvals", "approval_id"), ("native_delivery_attempts", "deliveries", "delivery_id"),
        ("provider_usage", "jobs", "job_id"), ("discovery_memory", "jobs", "source_job_id")):
        op.execute(f"""ALTER TABLE {table} ADD CONSTRAINT {table}_line_parent
          FOREIGN KEY(workspace_id,product_line_id,{key}) REFERENCES {parent}(workspace_id,product_line_id,id)""")
    for table, columns in (("catalog", "workspace_id, kind, code"), ("discovery_memory", "workspace_id, domain")):
        op.execute(f"""DO $$ DECLARE c record; BEGIN
          FOR c IN SELECT conname FROM pg_constraint WHERE conrelid='{table}'::regclass AND contype='u'
            AND pg_get_constraintdef(oid)='UNIQUE ({columns})'
          LOOP EXECUTE format('ALTER TABLE {table} DROP CONSTRAINT %I',c.conname); END LOOP;
          END $$""")
    op.execute("ALTER TABLE catalog ADD CONSTRAINT catalog_line_code UNIQUE(workspace_id,product_line_id,kind,code)")
    op.execute("ALTER TABLE discovery_memory ADD CONSTRAINT discovery_line_domain UNIQUE(workspace_id,product_line_id,domain)")
    for index in ("one_active_lead_job", "one_preparing_run", "one_workspace_stage"):
        op.execute(f"DROP INDEX {index}")
    op.execute("""CREATE UNIQUE INDEX one_active_lead_job ON jobs(workspace_id,product_line_id,lead_id)
      WHERE status IN ('PENDING','RUNNING')""")
    op.execute("""CREATE UNIQUE INDEX one_preparing_run ON preparation_runs(workspace_id,product_line_id,lead_id)
      WHERE status='PREPARING'""")
    op.execute("""CREATE UNIQUE INDEX one_workspace_stage ON jobs(workspace_id,product_line_id,kind)
      WHERE lead_id IS NULL AND status IN ('PENDING','RUNNING')""")
    op.execute("ALTER TABLE jobs ADD COLUMN output_generation integer NOT NULL DEFAULT 0 CHECK(output_generation BETWEEN 0 AND 3)")
    op.execute("ALTER TABLE job_stage_events ADD COLUMN actor_id uuid REFERENCES users(id)")
    for table, column, replacement in (("stage_artifacts", "contract_name", "contract_name IN ('setup.output','discovery.candidate','research.output','contact.output','scoring.output','matching.output','content.output')"),
        ("job_stage_events", "event", "event IN ('CLAIM','CHECKPOINT','RETRY','COMPLETION','FAILURE','LEASE_LOSS','QUARANTINE','REPLAY','HUMAN_RESOLUTION')")):
        op.execute(f"""DO $$ DECLARE c record; BEGIN
          FOR c IN SELECT conname FROM pg_constraint WHERE conrelid='{table}'::regclass AND contype='c'
          AND position('{column}' in pg_get_constraintdef(oid))>0
          LOOP EXECUTE format('ALTER TABLE {table} DROP CONSTRAINT %I',c.conname); END LOOP;
          END $$""")
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {table}_{column}_allowed CHECK({replacement})")
    # Infer ownership from the parent, rejecting a mismatched explicitly supplied line.
    for table, parent, key in (("catalog", None, None), ("preparation_runs", None, None), ("discovery_memory", "jobs", "source_job_id"),
        ("approvals", "preparation_runs", "run_id"), ("deliveries", "approvals", "approval_id"),
        ("native_delivery_attempts", "deliveries", "delivery_id"), ("provider_usage", "jobs", "job_id")):
        lookup = (f"SELECT product_line_id INTO expected FROM public.{parent} WHERE workspace_id=NEW.workspace_id AND id=NEW.{key};" if parent else "")
        op.execute(f"""CREATE FUNCTION line_owner_{table}() RETURNS trigger LANGUAGE plpgsql
          SET search_path=pg_catalog,public AS $$ DECLARE expected uuid; BEGIN
          {lookup}
          IF expected IS NULL AND NEW.product_line_id IS NULL THEN
            SELECT id INTO expected FROM public.product_lines WHERE workspace_id=NEW.workspace_id AND code='DEFAULT';
          END IF;
          IF NEW.product_line_id IS NULL THEN NEW.product_line_id=expected;
          ELSIF expected IS NOT NULL AND NEW.product_line_id<>expected THEN RAISE EXCEPTION 'PRODUCT_LINE_PARENT_MISMATCH'; END IF;
          RETURN NEW; END $$""")
        op.execute(f"REVOKE ALL ON FUNCTION line_owner_{table}() FROM PUBLIC")
        op.execute(f"CREATE TRIGGER line_owner BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION line_owner_{table}()")
    # Authoritative line version/hash changes on catalog/configuration edits.
    op.execute("""CREATE FUNCTION line_context_changed() RETURNS trigger LANGUAGE plpgsql
      SECURITY DEFINER SET search_path=pg_catalog,public AS $$ DECLARE lid uuid; BEGIN
      IF TG_OP='UPDATE' AND OLD IS NOT DISTINCT FROM NEW THEN RETURN NEW; END IF;
      IF TG_OP='DELETE' THEN lid=OLD.product_line_id; ELSE lid=NEW.product_line_id; END IF;
      UPDATE public.product_lines SET context_version=context_version+1,
        context_hash=encode(sha256(convert_to((settings::text || limits::text ||
          COALESCE((SELECT jsonb_agg(jsonb_build_object('kind',c.kind,'code',c.code,'name',c.name,
          'description',c.description,'rules',c.rules,'active',c.active,'version',c.context_version)
          ORDER BY c.kind,c.code)::text FROM public.catalog c WHERE c.product_line_id=lid),'[]')),'UTF8')),'hex') WHERE id=lid;
      IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF; END $$""")
    op.execute("REVOKE ALL ON FUNCTION line_context_changed() FROM PUBLIC")
    op.execute("CREATE TRIGGER line_catalog_context AFTER INSERT OR UPDATE OR DELETE ON catalog FOR EACH ROW EXECUTE FUNCTION line_context_changed()")
    op.execute("""CREATE FUNCTION line_settings_changed() RETURNS trigger LANGUAGE plpgsql
      SET search_path=pg_catalog,public AS $$ BEGIN
      IF NEW.settings IS DISTINCT FROM OLD.settings OR NEW.limits IS DISTINCT FROM OLD.limits THEN
        NEW.context_version=OLD.context_version+1;
        NEW.context_hash=encode(sha256(convert_to((NEW.settings::text || NEW.limits::text ||
          COALESCE((SELECT jsonb_agg(jsonb_build_object('kind',c.kind,'code',c.code,'name',c.name,
          'description',c.description,'rules',c.rules,'active',c.active,'version',c.context_version)
          ORDER BY c.kind,c.code)::text FROM public.catalog c WHERE c.product_line_id=NEW.id),'[]')),'UTF8')),'hex');
      END IF; RETURN NEW; END $$""")
    op.execute("REVOKE ALL ON FUNCTION line_settings_changed() FROM PUBLIC")
    op.execute("CREATE TRIGGER line_settings_context BEFORE UPDATE ON product_lines FOR EACH ROW EXECUTE FUNCTION line_settings_changed()")
    op.execute("""CREATE FUNCTION mirror_default_line() RETURNS trigger LANGUAGE plpgsql
      SECURITY DEFINER SET search_path=pg_catalog,public AS $$ BEGIN
      UPDATE public.product_lines SET settings=NEW.automation,paused=NOT NEW.automation_enabled,
        next_discovery_at=NEW.next_discovery_at WHERE workspace_id=NEW.id AND code='DEFAULT';
      RETURN NEW; END $$""")
    op.execute("REVOKE ALL ON FUNCTION mirror_default_line() FROM PUBLIC")
    op.execute("CREATE TRIGGER line_workspace_compatibility AFTER UPDATE OF automation,automation_enabled,next_discovery_at ON workspaces FOR EACH ROW EXECUTE FUNCTION mirror_default_line()")
    op.execute("GRANT INSERT,UPDATE ON product_lines TO backend_api")
    op.execute("GRANT UPDATE(settings,next_discovery_at) ON product_lines TO backend_worker")
    op.execute("GRANT INSERT ON stage_artifacts TO backend_api")
    op.execute("""ALTER TABLE product_lines ADD CONSTRAINT line_limits_bounds CHECK(
      COALESCE((limits->>'per_pool_concurrency')::integer,1) BETWEEN 1 AND 5 AND
      COALESCE((limits->>'provider_requests_per_minute')::integer,60) BETWEEN 1 AND 600 AND
      COALESCE((limits->>'monthly_budget_microusd')::integer,50000000) BETWEEN 0 AND 50000000)""")
    op.execute("""CREATE TABLE company_evidence (
      id uuid PRIMARY KEY,workspace_id uuid NOT NULL,lead_id uuid NOT NULL,
      source_url text NOT NULL,input_hash varchar(64) NOT NULL,content_hash varchar(64) NOT NULL,
      payload jsonb NOT NULL,fetch_version varchar(80) NOT NULL,extract_version varchar(80) NOT NULL,
      created_at timestamptz NOT NULL,FOREIGN KEY(workspace_id,lead_id) REFERENCES leads(workspace_id,id),
      UNIQUE(workspace_id,lead_id,input_hash,content_hash))""")
    op.execute("CREATE INDEX company_evidence_lookup ON company_evidence(workspace_id,lead_id,input_hash,created_at)")
    op.execute("ALTER TABLE company_evidence ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE company_evidence FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY workspace_boundary ON company_evidence TO backend_api
      USING(workspace_id::text=current_setting('app.workspace_id',true))
      WITH CHECK(workspace_id::text=current_setting('app.workspace_id',true))""")
    op.execute("GRANT SELECT ON company_evidence TO backend_api")
    op.execute("GRANT SELECT,INSERT ON company_evidence TO backend_worker")
    op.execute("CREATE TRIGGER company_evidence_immutable BEFORE UPDATE ON company_evidence FOR EACH ROW EXECUTE FUNCTION worker_history_immutable()")


def downgrade():
    raise RuntimeError("Product-line history and decisions must be preserved; use an explicit recovery migration.")
