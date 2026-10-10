"""Mock-first workspace-scoped campaign strategy proposals and human review."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '015'
down_revision = '014'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('campaign_proposals',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('workspace_id', UUID(as_uuid=True), sa.ForeignKey('workspaces.id', ondelete='CASCADE'), nullable=False),
        sa.Column('lead_id', UUID(as_uuid=True), sa.ForeignKey('leads.id', ondelete='CASCADE'), nullable=False),
        sa.Column('research_id', UUID(as_uuid=True), sa.ForeignKey('lead_research.id'), nullable=False),
        sa.Column('idempotency_key', UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.Text, nullable=False, server_default='DRAFT'),
        sa.Column('version', sa.Integer, nullable=False, server_default='1'),
        sa.Column('provider', sa.Text, nullable=False, server_default='mock'),
        sa.Column('strategy', JSONB, nullable=False),
        sa.Column('context_hash', sa.Text, nullable=False),
        sa.Column('review_notes', sa.Text),
        sa.Column('reviewed_by', sa.Text),
        sa.Column('reviewed_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('workspace_id', 'id'),
        sa.UniqueConstraint('workspace_id', 'idempotency_key'),
        sa.CheckConstraint("status IN ('DRAFT','REVIEWED','REJECTED')", name='ck_campaign_proposal_status'),
        sa.CheckConstraint('version > 0', name='ck_campaign_proposal_version'),
        sa.CheckConstraint("provider = 'mock'", name='ck_campaign_proposal_provider'),
    )
    op.create_index('ix_campaign_proposals_workspace_id', 'campaign_proposals', ['workspace_id'])
    op.create_index('ix_campaign_proposals_lead_id', 'campaign_proposals', ['lead_id'])
    for column, parent in [('lead_id', 'leads'), ('research_id', 'lead_research')]:
        op.create_foreign_key(f'fk_campaign_proposals_{column}_workspace', 'campaign_proposals', parent,
            ['workspace_id', column], ['workspace_id', 'id'], deferrable=True, initially='DEFERRED')
    op.execute('GRANT SELECT,INSERT,UPDATE,DELETE ON campaign_proposals TO marketing_workspace_runtime')
    op.execute('ALTER TABLE campaign_proposals ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE campaign_proposals FORCE ROW LEVEL SECURITY')
    predicate = "workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid"
    op.execute(f'CREATE POLICY workspace_isolation ON campaign_proposals USING ({predicate}) WITH CHECK ({predicate})')


def downgrade():
    op.drop_table('campaign_proposals')
