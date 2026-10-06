"""Workspace-scoped dashboard discovery configuration and runs."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def base_columns():
    return [sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
            sa.Column('workspace_id', UUID(as_uuid=True), sa.ForeignKey('workspaces.id', ondelete='RESTRICT'), nullable=False)]


def upgrade():
    op.create_table('discovery_automations', *base_columns(),
        sa.Column('webhook_url', sa.Text, nullable=False), sa.Column('default_query', sa.Text, nullable=False),
        sa.Column('enabled', sa.Boolean, nullable=False, server_default=sa.true()),
        sa.UniqueConstraint('workspace_id', name='uq_discovery_automations_workspace'))
    op.create_table('discovery_runs', *base_columns(),
        sa.Column('status', sa.Text, nullable=False, server_default='QUEUED'),
        sa.Column('query', sa.Text, nullable=False), sa.Column('target_new_companies', sa.Integer, nullable=False),
        sa.Column('token_hash', sa.Text, nullable=False), sa.Column('requested_by', sa.Text, nullable=False),
        sa.Column('claimed_by', sa.Text), sa.Column('summary', JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('error_code', sa.Text), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('started_at', sa.DateTime(timezone=True)), sa.Column('finished_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('QUEUED','RUNNING','COMPLETED','FAILED','TIMED_OUT')", name='ck_discovery_runs_status'),
        sa.CheckConstraint('target_new_companies BETWEEN 1 AND 10', name='ck_discovery_runs_target'))
    op.create_index('ix_discovery_runs_one_active', 'discovery_runs', ['workspace_id'], unique=True,
        postgresql_where=sa.text("status IN ('QUEUED','RUNNING')"))
    for table in ('discovery_automations', 'discovery_runs'):
        op.create_index(f'ix_{table}_workspace_id', table, ['workspace_id'])
        op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO marketing_workspace_runtime')
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        predicate = "workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid"
        op.execute(f'CREATE POLICY workspace_isolation ON {table} USING ({predicate}) WITH CHECK ({predicate})')


def downgrade():
    op.drop_table('discovery_runs')
    op.drop_table('discovery_automations')
