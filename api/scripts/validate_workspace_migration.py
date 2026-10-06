"""Exercise 008 -> 009 -> 008 -> 009 using a separate disposable database."""
import os
import secrets
import subprocess
import sys

sys.path.insert(0, '/app')
from sqlalchemy import create_engine, text
from app.db.session import DATABASE_URL, engine
from app.auth import verify_password

if os.getenv('APP_ENV') not in ('workspace-test', 'ci'):
    raise SystemExit('Refusing to run outside a disposable test environment.')

name = 'workspace_migration_' + secrets.token_hex(6)
url = DATABASE_URL.set(database=name)
env = {**os.environ, 'POSTGRES_DB': name}
tables = ('products', 'icp_profiles', 'companies', 'contacts', 'leads', 'lead_research',
          'research_sources', 'lead_scores', 'product_matches', 'marketing_actions',
          'approval_requests', 'events', 'lead_candidates', 'lead_candidate_sources')


def migrate(revision):
    subprocess.run(['alembic', 'upgrade' if revision == 'head' or revision == '008' and not migrated else 'downgrade', revision],
                   env=env, check=True, stdout=subprocess.DEVNULL)


with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
    connection.execute(text(f'CREATE DATABASE {name}'))
scratch = create_engine(url)
migrated = False
try:
    migrate('008')
    with scratch.begin() as connection:
        connection.execute(text("INSERT INTO companies(id,name,domain) VALUES ('11111111-1111-1111-1111-111111111111','Preserve company','preserve.example.test')"))
        connection.execute(text("INSERT INTO contacts(id,company_id,email) VALUES ('22222222-2222-2222-2222-222222222222','11111111-1111-1111-1111-111111111111','preserve@example.test')"))
        connection.execute(text("INSERT INTO leads(company_id,primary_contact_id,icp_profile_id) SELECT '11111111-1111-1111-1111-111111111111','22222222-2222-2222-2222-222222222222',id FROM icp_profiles LIMIT 1"))
        connection.execute(text("INSERT INTO events(event_type,entity_type,entity_id,metadata) VALUES ('migration_fixture','COMPANY','11111111-1111-1111-1111-111111111111',jsonb_build_object('preserve',true))"))
        before = {table: connection.execute(text(f'SELECT * FROM {table} ORDER BY id')).mappings().all() for table in tables}
    # Reproduce API startup racing an explicit CI/operator migration.
    upgrades = [subprocess.Popen(['alembic', 'upgrade', 'head'], env=env,
                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    for upgrade in upgrades:
        _, errors = upgrade.communicate(timeout=60)
        assert upgrade.returncode == 0, errors
    print('PASS concurrent upgrades serialize and both succeed')
    migrated = True
    with scratch.connect() as connection:
        for table in tables:
            after = connection.execute(text(f'SELECT * FROM {table} ORDER BY id')).mappings().all()
            assert [dict((k, v) for k, v in r.items() if k != 'workspace_id') for r in after] == [dict(r) for r in before[table]], table
            assert all(str(r['workspace_id']) == '00000000-0000-0000-0000-000000000001' for r in after), table
    print('PASS migration preserves existing values, identifiers and history in all 14 tables')
    password = secrets.token_urlsafe(24)
    command = [sys.executable, '-m', 'app.manage', 'bootstrap-admin', '--email', 'bootstrap@example.test', '--password-stdin']
    result = subprocess.run(command, env=env, input=password + '\n', text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    with scratch.begin() as connection:
        account = connection.execute(text("SELECT id,password_hash,platform_admin FROM users WHERE email='bootstrap@example.test'")).first()
        assert account[2] and verify_password(password, account[1])
        assert connection.scalar(text("SELECT role FROM workspace_memberships WHERE user_id=:id"), {'id': account[0]}) == 'ADMIN'
        connection.execute(text("INSERT INTO login_sessions(token_hash,user_id,expires_at) VALUES ('test-session',:id,now()+interval '1 hour')"), {'id': account[0]})
    assert subprocess.run(command, env=env, input=password + '\n', text=True, capture_output=True).returncode != 0
    print('PASS first administrator bootstrap succeeds once and creates explicit membership')
    reset = [sys.executable, '-m', 'app.manage', 'reset-password', '--email', 'bootstrap@example.test', '--password-stdin']
    assert subprocess.run(reset, env=env, input=password + '-changed\n', text=True, capture_output=True).returncode == 0
    with scratch.connect() as connection:
        encoded = connection.scalar(text("SELECT password_hash FROM users WHERE email='bootstrap@example.test'"))
        assert verify_password(password + '-changed', encoded) and not verify_password(password, encoded)
        assert connection.scalar(text('SELECT count(*) FROM login_sessions')) == 0
    print('PASS administrator password recovery revokes old sessions')
    migrate('008')
    with scratch.connect() as connection:
        for table in tables:
            after = connection.execute(text(f'SELECT * FROM {table} ORDER BY id')).mappings().all()
            assert [dict(r) for r in after] == [dict(r) for r in before[table]], table
    print('PASS single-workspace downgrade preserves all legacy records')
    migrate('head')
    with scratch.begin() as connection:
        connection.execute(text("INSERT INTO workspaces(name,slug) VALUES ('Second workspace','second')"))
    result = subprocess.run(['alembic', 'downgrade', '008'], env=env, capture_output=True, text=True)
    assert result.returncode != 0 and 'Downgrade requires' in result.stderr
    with scratch.connect() as connection:
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '009'
        assert connection.scalar(text('SELECT count(*) FROM workspaces')) == 2
    print('PASS unsafe multi-workspace downgrade is rejected atomically')
    print('Migration regression PASSED')
finally:
    scratch.dispose()
    with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        connection.execute(text(f'DROP DATABASE {name} WITH (FORCE)'))
