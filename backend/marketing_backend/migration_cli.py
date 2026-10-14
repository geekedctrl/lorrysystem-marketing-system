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
from sqlalchemy import create_engine, text
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


def run(mode):
    with legacy_engine().connect() as source:
        counts, fingerprint = snapshot(source)
    run_id = uuid.uuid4()
    status = "COMPLETED" if mode in ("export", "dry-run") else "BLOCKED"
    differences = [] if mode in ("export", "dry-run") else [{"code": "APPLY_REQUIRES_APPROVED_ADAPTERS"}]
    with Session(native_engine) as db:
        db.execute(text("""INSERT INTO migration_runs
          (id,mode,status,source_fingerprint,counts,differences,completed_at)
          VALUES (:id,:mode,:status,:fp,:counts,:diff,:done)"""), {
            "id": run_id, "mode": mode, "status": status, "fp": fingerprint,
            "counts": json.dumps(counts), "diff": json.dumps(differences),
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
