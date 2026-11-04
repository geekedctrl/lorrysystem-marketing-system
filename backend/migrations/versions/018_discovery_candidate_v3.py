"""Allow the additive, independently corroborated discovery artifact schema."""
from alembic import op

revision = "018_discovery_candidate_v3"
down_revision = "017_worker_pools"
branch_labels = depends_on = None


def upgrade():
    # Existing v1/v2 artifacts remain byte-for-byte unchanged. This only
    # permits newly produced discovery artifacts to declare schema version 3.
    op.execute("ALTER TABLE stage_artifacts DROP CONSTRAINT stage_artifacts_schema_version_check")
    op.execute("ALTER TABLE stage_artifacts ADD CONSTRAINT stage_artifacts_schema_version_check CHECK(schema_version IN (1,2,3))")


def downgrade():
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM stage_artifacts WHERE schema_version=3) THEN
        RAISE EXCEPTION 'Cannot downgrade while v3 discovery artifacts exist';
      END IF;
    END $$""")
    op.execute("ALTER TABLE stage_artifacts DROP CONSTRAINT stage_artifacts_schema_version_check")
    op.execute("ALTER TABLE stage_artifacts ADD CONSTRAINT stage_artifacts_schema_version_check CHECK(schema_version IN (1,2))")
