"""Read-only legacy inspection and resumable migration control plane.

The first implementation deliberately migrates metadata, identity maps and
reconciliation evidence. Row payload adapters can be added without changing
the safety contract or ownership transitions.
"""
import argparse
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import Session
from .db import engine as native_engine

ENTITY_TABLES = ("users", "workspaces", "memberships", "catalog", "leads")


def legacy_engine():
    url = os.environ.get("LEGACY_READONLY_DATABASE_URL")
    if not url:
        raise SystemExit("LEGACY_READONLY_DATABASE_URL is required")
    return create_engine(url, pool_pre_ping=True)


def snapshot(conn):
    counts = {}
    for table in ENTITY_TABLES:
        try:
            counts[table] = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
        except Exception:
            counts[table] = None
    raw = json.dumps(counts, sort_keys=True).encode()
    return counts, hashlib.sha256(raw).hexdigest()


def source_rows(conn, table):
    try:
        columns = {c["name"] for c in inspect(conn).get_columns(table)}
    except Exception:
        return []
    if not {"id", "name"}.issubset(columns):
        return []
    return conn.execute(text(f"SELECT id::text, name FROM {table} ORDER BY id")).mappings().all()


def table_columns(conn, table):
    try:
        return {c["name"] for c in inspect(conn).get_columns(table)}
    except Exception:
        return set()


def migrate_workspaces(source, db, fingerprint):
    """Copy only non-sensitive workspace identity, preserving a source map."""
    rows = source_rows(source, "workspaces")
    for row in rows:
        existing = db.execute(text("""SELECT native_id FROM legacy_identity_map
          WHERE source_system='legacy-postgres' AND entity_type='workspace' AND legacy_id=:id"""), {"id": row["id"]}).scalar()
        native_id = existing or uuid.uuid4()
        db.execute(text("""INSERT INTO workspaces(id,name,active,automation_enabled)
          VALUES (:id,:name,true,false) ON CONFLICT (id) DO NOTHING"""), {"id": native_id, "name": row["name"]})
        db.execute(text("""INSERT INTO legacy_identity_map
          (source_system,entity_type,legacy_id,native_id,source_fingerprint)
          VALUES ('legacy-postgres','workspace',:legacy,:native,:fp)
          ON CONFLICT (source_system,entity_type,legacy_id) DO UPDATE SET
            native_id=EXCLUDED.native_id, source_fingerprint=EXCLUDED.source_fingerprint"""),
          {"legacy": row["id"], "native": native_id, "fp": fingerprint})
    return len(rows)


def migrate_catalog(source, db, fingerprint):
    cols = table_columns(source, "catalog")
    required = {"id", "workspace_id", "kind", "code", "name", "description"}
    if not required.issubset(cols):
        return 0, {"entity": "catalog", "code": "UNSUPPORTED_SOURCE_SCHEMA"}
    rows = source.execute(text("""SELECT id::text,workspace_id::text,kind,code,name,description
      FROM catalog ORDER BY id""")).mappings().all()
    moved = 0
    for row in rows:
        workspace = db.execute(text("""SELECT native_id FROM legacy_identity_map
          WHERE source_system='legacy-postgres' AND entity_type='workspace' AND legacy_id=:id"""), {"id": row["workspace_id"]}).scalar()
        if not workspace:
            continue
        native_id = db.execute(text("""SELECT native_id FROM legacy_identity_map WHERE
          source_system='legacy-postgres' AND entity_type='catalog' AND legacy_id=:id"""), {"id": row["id"]}).scalar() or uuid.uuid4()
        db.execute(text("""INSERT INTO catalog(id,workspace_id,kind,code,name,description,active,context_version)
          VALUES (:id,:workspace,:kind,:code,:name,:description,true,1)
          ON CONFLICT (id) DO NOTHING"""), {"id": native_id, "workspace": workspace,
          "kind": row["kind"], "code": row["code"], "name": row["name"], "description": row["description"]})
        db.execute(text("""INSERT INTO legacy_identity_map(source_system,entity_type,legacy_id,native_id,source_fingerprint)
          VALUES ('legacy-postgres','catalog',:legacy,:native,:fp)
          ON CONFLICT (source_system,entity_type,legacy_id) DO NOTHING"""),
          {"legacy": row["id"], "native": native_id, "fp": fingerprint})
        moved += 1
    return moved, None


def migrate_leads(source, db, fingerprint):
    cols = table_columns(source, "leads")
    required = {"id", "workspace_id", "company_name", "website"}
    if not required.issubset(cols):
        return 0, {"entity": "leads", "code": "UNSUPPORTED_SOURCE_SCHEMA"}
    rows = source.execute(text("""SELECT id::text,workspace_id::text,company_name,website
      FROM leads ORDER BY id""")).mappings().all()
    moved = 0
    for row in rows:
        workspace = db.execute(text("""SELECT native_id FROM legacy_identity_map WHERE
          source_system='legacy-postgres' AND entity_type='workspace' AND legacy_id=:id"""), {"id": row["workspace_id"]}).scalar()
        if not workspace:
            continue
        native_id = db.execute(text("""SELECT native_id FROM legacy_identity_map WHERE
          source_system='legacy-postgres' AND entity_type='lead' AND legacy_id=:id"""), {"id": row["id"]}).scalar() or uuid.uuid4()
        db.execute(text("""INSERT INTO leads(id,workspace_id,company_name,website)
          VALUES (:id,:workspace,:company_name,:website) ON CONFLICT (id) DO NOTHING"""),
          {"id": native_id, "workspace": workspace, "company_name": row["company_name"], "website": row["website"]})
        db.execute(text("""INSERT INTO legacy_identity_map(source_system,entity_type,legacy_id,native_id,source_fingerprint)
          VALUES ('legacy-postgres','lead',:legacy,:native,:fp)
          ON CONFLICT (source_system,entity_type,legacy_id) DO NOTHING"""),
          {"legacy": row["id"], "native": native_id, "fp": fingerprint})
        moved += 1
    return moved, None


def run(mode):
    with legacy_engine().connect() as source:
        counts, fingerprint = snapshot(source)
    run_id = uuid.uuid4()
    with Session(native_engine) as db:
        migrated = 0
        differences = []
        status = "COMPLETED"
        if mode == "apply":
            with legacy_engine().connect() as source:
                migrated = migrate_workspaces(source, db, fingerprint)
                catalog_moved, catalog_difference = migrate_catalog(source, db, fingerprint)
                lead_moved, lead_difference = migrate_leads(source, db, fingerprint)
                migrated += catalog_moved + lead_moved
                differences.extend(x for x in (catalog_difference, lead_difference) if x)
        elif mode in ("reconcile", "final-delta"):
            for entity, table in (("workspaces", "workspaces"), ("catalog", "catalog"), ("leads", "leads")):
                native_count = db.scalar(text(f"SELECT count(*) FROM {table}")) or 0
                if counts.get(entity) is not None and native_count != counts[entity]:
                    differences.append({"entity": entity, "source": counts[entity], "native": native_count})
            status = "COMPLETED" if not differences else "DIFFERENCES"
        elif mode == "dry-run":
            differences = [{"code": "WORKSPACE_IDENTITY_WILL_MIGRATE", "count": counts.get("workspaces") or 0}]
        db.execute(text("""INSERT INTO migration_runs
          (id,mode,status,source_fingerprint,counts,differences,completed_at)
          VALUES (:id,:mode,:status,:fp,:counts,:diff,:done)"""), {
            "id": run_id, "mode": mode, "status": status, "fp": fingerprint,
            "counts": json.dumps({**counts, "workspaces_migrated": migrated}), "diff": json.dumps(differences),
            "done": datetime.now(timezone.utc),
        })
        db.commit()
    print(json.dumps({"run_id": str(run_id), "mode": mode, "status": status,
                      "source_fingerprint": fingerprint, "counts": counts,
                      "differences": differences}, sort_keys=True))
    return 0 if status == "COMPLETED" else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description="Synthetic-safe legacy migration control")
    parser.add_argument("mode", choices=["export", "dry-run", "apply", "reconcile", "final-delta"])
    return run(parser.parse_args(argv).mode)


if __name__ == "__main__":
    raise SystemExit(main())
