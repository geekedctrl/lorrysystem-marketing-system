"""Human-reviewed discovery candidates; preserve existing discovery history."""

from alembic import op

revision = "008_discovery_review"
down_revision = "007_catalog_context_version"
branch_labels = depends_on = None


def upgrade():
    op.execute("""ALTER TABLE discovery_memory
        ADD CONSTRAINT discovery_identity UNIQUE(workspace_id,id),
        ADD COLUMN source_job_id uuid,
        ADD COLUMN context_hash varchar(64),
        ADD COLUMN accepted_lead_id uuid,
        ADD COLUMN reviewed_by uuid REFERENCES users(id),
        ADD COLUMN reviewed_at timestamptz,
        ADD COLUMN review_note text,
        ADD COLUMN retry_after timestamptz,
        ADD CONSTRAINT discovery_job_scope FOREIGN KEY(workspace_id,source_job_id) REFERENCES jobs(workspace_id,id),
        ADD CONSTRAINT discovery_lead_scope FOREIGN KEY(workspace_id,accepted_lead_id) REFERENCES leads(workspace_id,id)
    """)
    op.execute(
        "CREATE INDEX discovery_review_inbox ON discovery_memory(workspace_id,outcome,created_at)"
    )
    op.execute("REVOKE INSERT ON leads FROM backend_worker")


def downgrade():
    raise RuntimeError(
        "Candidate review history requires an explicit recovery migration"
    )
