"""Keep approvals stale even when catalog edits are subsequently reverted."""

from alembic import op

revision = "007_catalog_context_version"
down_revision = "006_frontend_support"
branch_labels = depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE catalog ADD COLUMN context_version integer NOT NULL DEFAULT 1 CHECK(context_version >= 1)"
    )
    op.execute(
        "CREATE INDEX preparation_latest ON preparation_runs(workspace_id,lead_id,created_at DESC,id DESC)"
    )


def downgrade():
    raise RuntimeError(
        "Catalog versions form part of historical evidence; use an explicit recovery migration"
    )
