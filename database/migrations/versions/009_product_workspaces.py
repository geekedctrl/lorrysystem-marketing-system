"""Private product workspaces, accounts and database isolation.

All pre-existing business records belong to LorrySystem. This migration
requires a database owner able to create the restricted runtime role.
"""
from uuid import UUID as PyUUID
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None

LEGACY_ID = '00000000-0000-0000-0000-000000000001'
TABLES = (
    'products', 'icp_profiles', 'companies', 'contacts', 'leads',
    'lead_research', 'research_sources', 'lead_scores', 'product_matches',
    'marketing_actions', 'approval_requests', 'events', 'lead_candidates',
    'lead_candidate_sources',
)
CONTROL = ('workspaces', 'users', 'workspace_memberships', 'login_sessions',
           'workspace_invitations', 'service_credentials', 'access_audit', 'login_attempts')


def identifier():
    return sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()'))


def timestamp():
    return sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def workspace_column(**kwargs):
    return sa.Column('workspace_id', UUID(as_uuid=True), sa.ForeignKey('workspaces.id', ondelete='RESTRICT'), **kwargs)


def upgrade():
    op.create_table('workspaces', identifier(), sa.Column('name', sa.Text, nullable=False),
                    sa.Column('slug', sa.Text, nullable=False, unique=True),
                    sa.Column('active', sa.Boolean, nullable=False, server_default=sa.true()),
                    sa.Column('settings', JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")), timestamp())
    op.execute(sa.text("INSERT INTO workspaces(id,name,slug) VALUES (:id,'LorrySystem','lorrysystem')").bindparams(id=PyUUID(LEGACY_ID)))
    op.create_table('users', identifier(), sa.Column('email', sa.Text, nullable=False, unique=True),
                    sa.Column('password_hash', sa.Text, nullable=False),
                    sa.Column('active', sa.Boolean, nullable=False, server_default=sa.true()),
                    sa.Column('platform_admin', sa.Boolean, nullable=False, server_default=sa.false()), timestamp())
    op.create_table('workspace_memberships', workspace_column(primary_key=True),
                    sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), primary_key=True),
                    sa.Column('role', sa.Text, nullable=False),
                    sa.CheckConstraint("role IN ('ADMIN','OPERATOR','REVIEWER','VIEWER')", name='ck_membership_role'))
    op.create_table('login_sessions', sa.Column('token_hash', sa.Text, primary_key=True),
                    sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
                    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('workspace_invitations', sa.Column('token_hash', sa.Text, primary_key=True),
                    workspace_column(nullable=False), sa.Column('email', sa.Text, nullable=False),
                    sa.Column('role', sa.Text, nullable=False), sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('used_at', sa.DateTime(timezone=True)))
    op.create_table('service_credentials', identifier(), workspace_column(nullable=False),
                    sa.Column('name', sa.Text, nullable=False), sa.Column('token_hash', sa.Text, unique=True, nullable=False),
                    sa.Column('active', sa.Boolean, nullable=False, server_default=sa.true()), timestamp())
    op.create_table('access_audit', identifier(), workspace_column(nullable=True),
                    sa.Column('actor', sa.Text, nullable=False), sa.Column('action', sa.Text, nullable=False),
                    sa.Column('detail', JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")), timestamp())
    op.create_table('login_attempts', sa.Column('key', sa.Text, primary_key=True),
                    sa.Column('failures', sa.Integer, nullable=False),
                    sa.Column('window_started_at', sa.DateTime(timezone=True), nullable=False))
    for table in TABLES:
        op.add_column(table, workspace_column(nullable=True))
        op.execute(sa.text(f'UPDATE {table} SET workspace_id = :id').bindparams(id=PyUUID(LEGACY_ID)))
        op.alter_column(table, 'workspace_id', nullable=False)
        op.create_index(f'ix_{table}_workspace_id', table, ['workspace_id'])
        op.create_unique_constraint(f'uq_{table}_workspace_id_id', table, ['workspace_id', 'id'])
    # Preserve existing delete behaviour; additional composite references reject
    # links across workspaces even when a caller knows another record's UUID.
    inspector = sa.inspect(op.get_bind())
    for table in TABLES:
        for fk in inspector.get_foreign_keys(table):
            parent = fk['referred_table']
            columns = fk['constrained_columns']
            if parent in TABLES and len(columns) == 1:
                op.create_foreign_key(f'fk_{table}_{columns[0]}_workspace', table, parent,
                                      ['workspace_id'] + columns, ['workspace_id'] + fk['referred_columns'],
                                      deferrable=True, initially='DEFERRED')
    for table in ('products', 'icp_profiles'):
        op.drop_constraint(f'{table}_code_key', table, type_='unique')
        op.create_unique_constraint(f'uq_{table}_workspace_code', table, ['workspace_id', 'code'])
    for table, index, expression, condition in (
        ('companies', 'idx_companies_domain_unique', 'lower(domain)', 'domain IS NOT NULL'),
        ('contacts', 'idx_contacts_email_unique', 'lower(email)', 'email IS NOT NULL'),
        ('lead_candidates', 'idx_lead_candidates_active_domain_unique', 'domain',
         "domain IS NOT NULL AND status IN ('NEW','READY_FOR_REVIEW','NEEDS_REVIEW')"),
        ('lead_candidates', 'idx_lead_candidates_active_website_unique', 'normalized_website',
         "normalized_website IS NOT NULL AND status IN ('NEW','READY_FOR_REVIEW','NEEDS_REVIEW')"),
    ):
        op.drop_index(index, table_name=table)
        op.execute(f'CREATE UNIQUE INDEX {index} ON {table} (workspace_id, {expression}) WHERE {condition}')
    op.execute("""DO $$ BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='marketing_workspace_runtime') THEN
            CREATE ROLE marketing_workspace_runtime NOLOGIN NOSUPERUSER NOBYPASSRLS;
        END IF;
        EXECUTE format('GRANT marketing_workspace_runtime TO %I', current_user);
    END $$""")
    op.execute('GRANT USAGE ON SCHEMA public TO marketing_workspace_runtime')
    for table in TABLES:
        op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO marketing_workspace_runtime')
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        predicate = "workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid"
        op.execute(f'CREATE POLICY workspace_isolation ON {table} USING ({predicate}) WITH CHECK ({predicate})')


def downgrade():
    # Never silently merge separate teams' data into the legacy global schema.
    workspaces = op.get_bind().execute(sa.text('SELECT id FROM workspaces')).scalars().all()
    if len(workspaces) != 1 or str(workspaces[0]) != LEGACY_ID:
        raise RuntimeError('Downgrade requires exactly the original LorrySystem workspace. Restore a verified backup instead.')
    for table in TABLES:
        op.execute(f'ALTER TABLE {table} DISABLE ROW LEVEL SECURITY')
        op.execute(f'DROP POLICY workspace_isolation ON {table}')
    inspector = sa.inspect(op.get_bind())
    for table in TABLES:
        for fk in inspector.get_foreign_keys(table):
            if len(fk['constrained_columns']) == 2 and 'workspace_id' in fk['constrained_columns']:
                op.drop_constraint(fk['name'], table, type_='foreignkey')
    for table in ('products', 'icp_profiles'):
        op.drop_constraint(f'uq_{table}_workspace_code', table, type_='unique')
        op.create_unique_constraint(f'{table}_code_key', table, ['code'])
    for table, index, expression, condition in (
        ('companies', 'idx_companies_domain_unique', 'lower(domain)', 'domain IS NOT NULL'),
        ('contacts', 'idx_contacts_email_unique', 'lower(email)', 'email IS NOT NULL'),
        ('lead_candidates', 'idx_lead_candidates_active_domain_unique', 'domain',
         "domain IS NOT NULL AND status IN ('NEW','READY_FOR_REVIEW','NEEDS_REVIEW')"),
        ('lead_candidates', 'idx_lead_candidates_active_website_unique', 'normalized_website',
         "normalized_website IS NOT NULL AND status IN ('NEW','READY_FOR_REVIEW','NEEDS_REVIEW')"),
    ):
        op.drop_index(index, table_name=table)
        op.execute(f'CREATE UNIQUE INDEX {index} ON {table} ({expression}) WHERE {condition}')
    for table in TABLES:
        op.drop_constraint(f'uq_{table}_workspace_id_id', table, type_='unique')
        op.drop_column(table, 'workspace_id')
    for table in reversed(CONTROL):
        op.drop_table(table)
