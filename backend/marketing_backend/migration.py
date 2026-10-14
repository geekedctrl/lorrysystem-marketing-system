"""Reconciliation gate shared by migration tooling and ownership activation."""
from sqlalchemy import text


def unresolved_differences(db):
    # No completed, exact reconciliation is a blocking difference.
    row = db.execute(text("""SELECT differences FROM migration_runs
      WHERE mode IN ('reconcile','final-delta') AND status = 'COMPLETED'
      ORDER BY completed_at DESC LIMIT 1""")).first()
    return row is None or bool(row[0])
