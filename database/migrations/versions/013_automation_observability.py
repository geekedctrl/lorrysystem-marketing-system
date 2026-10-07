"""Record worker heartbeat and bounded per-job usage without provider payloads."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "automation_workers", sa.Column("last_seen_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "automation_jobs",
        sa.Column(
            "usage", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
    )


def downgrade():
    op.drop_column("automation_jobs", "usage")
    op.drop_column("automation_workers", "last_seen_at")
