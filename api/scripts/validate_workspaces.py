"""Disposable database integration regression. Never run against customer data.

Run inside the API container with APP_ENV=workspace-test or APP_ENV=ci.
The suite creates isolated workspaces and accounts; credentials are never logged.
"""
import csv
import io
import http.cookiejar
import json
import os
import re
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from uuid import UUID

sys.path.insert(0, '/app')
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.auth import password_hash, token_hash
from app.db.session import ControlSession, SessionLocal
from app.models import Company, Contact, Lead, LeadCandidate, Product
from app.models.workspaces import LoginSession, Membership, User
from app.workspace_context import LORRYSYSTEM_WORKSPACE_ID

if os.getenv('APP_ENV') not in ('workspace-test', 'ci'):
    raise SystemExit('Refusing to run: APP_ENV must be workspace-test or ci.')

BASE = os.getenv('API_BASE_URL', 'http://127.0.0.1:8000')
DASHBOARD = os.getenv('DASHBOARD_BASE_URL', 'http://workspace-test-dashboard:8080')
passed = 0


def check(label, condition):
    global passed
    if not condition:
        raise AssertionError(label)
    passed += 1
    print(f'PASS {label}', flush=True)


def request(method, path, data=None, headers=None, expected=200):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(BASE + path, data=body, method=method,
                                 headers={'Content-Type': 'application/json', **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            status = response.status
            result = json.loads(response.read() or b'null')
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read()
        try:
            result = json.loads(raw)
        except ValueError:
            result = {'detail': raw[:160].decode(errors='replace')}
    if status != expected:
        # Do not log data or headers; those may contain credentials.
        raise AssertionError(f'{method} {path}: expected {expected}, got {status}: {result.get("detail", "") if isinstance(result, dict) else ""}')
    check(f'{method} {path}: {expected}', True)
    return result


def auth(token, workspace=None):
    return {'Authorization': 'Bearer ' + token, **({'X-Workspace-ID': str(workspace)} if workspace else {})}


def signin(email, password):
    return request('POST', '/api/auth/login', {'email': email, 'password': password})['token']


suffix = secrets.token_hex(5)
password = secrets.token_urlsafe(24)
admin_email = f'workspace-admin-{suffix}@example.test'
with ControlSession() as db:
    admin = User(email=admin_email, password_hash=password_hash(password), platform_admin=True)
    db.add(admin)
    db.flush()
    db.add(Membership(workspace_id=LORRYSYSTEM_WORKSPACE_ID, user_id=admin.id, role='ADMIN'))
    db.commit()
    admin_id = str(admin.id)

request('GET', '/health')
request('GET', '/api/companies', expected=401)
request('POST', '/api/auth/login', {'email': admin_email, 'password': 'wrong'}, expected=401)
admin_token = signin(admin_email, password)
request('GET', '/api/companies', headers=auth(admin_token), expected=400)
legacy = {'X-API-Key': os.environ['MARKETING_API_KEY']}
request('GET', '/api/products', headers=legacy)
request('GET', '/api/auth/me', headers=legacy, expected=401)
request('POST', '/api/workspaces', {'name': 'Forbidden', 'slug': 'forbidden'}, legacy, expected=401)

a = request('POST', '/api/workspaces', {'name': 'Product Alpha', 'slug': 'alpha-' + suffix}, auth(admin_token), 201)['id']
b = request('POST', '/api/workspaces', {'name': 'Product Beta', 'slug': 'beta-' + suffix}, auth(admin_token), 201)['id']
ha, hb = auth(admin_token, a), auth(admin_token, b)
request('GET', '/api/companies', headers={**legacy, 'X-Workspace-ID': b}, expected=403)
request('GET', '/api/companies', headers=auth('invalid', a), expected=401)

icps, products = {}, {}
for workspace, headers in ((a, ha), (b, hb)):
    check('new workspace has empty catalog', request('GET', '/api/products', headers=headers) == [])
    icps[workspace] = request('POST', f'/api/workspaces/{workspace}/catalog/icps',
        {'code': 'GENERAL', 'name': 'General customers', 'qualification_rules': {'sector': 'any'}}, headers, 201)['id']
    products[workspace] = request('POST', f'/api/workspaces/{workspace}/catalog/products',
        {'code': 'MAIN', 'name': 'Main offering'}, headers, 201)['id']
    request('POST', f'/api/workspaces/{workspace}/catalog/products', {'code': 'MAIN', 'name': 'Duplicate'}, headers, 409)
    request('PATCH', f'/api/workspaces/{workspace}/settings',
        {'description': 'Distinct product', 'brand_voice': 'Clear', 'monthly_budget_usd': 50}, headers)
    context = request('GET', '/api/workspace-context', headers=headers)
    check('worker receives matching workspace configuration', context['workspace']['id'] == workspace and context['icps'][0]['id'] == icps[workspace])
    check('automation contract namespaces discovery and requires human decisions',
          context['automation'] == {'contract_version': 1, 'credential_kind': 'user',
            'registry_namespace': f'workspace:{workspace}:discovery',
            'human_candidate_review_required': True, 'human_marketing_approval_required': True})

companies, contacts, leads = {}, {}, {}
for workspace, headers in ((a, ha), (b, hb)):
    companies[workspace] = request('POST', '/api/companies',
        {'name': 'Shared Prospect', 'domain': 'shared-' + suffix + '.example.test'}, headers, 201)['id']
    contacts[workspace] = request('POST', '/api/contacts',
        {'company_id': companies[workspace], 'email': 'contact-' + suffix + '@example.test', 'full_name': 'Pat'}, headers, 201)['id']
    leads[workspace] = request('POST', '/api/leads',
        {'company_id': companies[workspace], 'primary_contact_id': contacts[workspace], 'icp_profile_id': icps[workspace]}, headers, 201)['id']
    request('POST', '/api/leads', {'company_id': companies[workspace], 'icp_profile_id': icps[workspace]}, headers, 409)
    check('list contains only own company', [c['id'] for c in request('GET', '/api/companies', headers=headers)] == [companies[workspace]])

request('GET', '/api/companies/' + companies[b], headers=ha, expected=404)
request('GET', '/api/contacts/' + contacts[b], headers=ha, expected=404)
request('GET', '/api/leads/' + leads[b], headers=ha, expected=404)
request('POST', '/api/leads', {'company_id': companies[a], 'icp_profile_id': icps[b]}, ha, 404)
request('POST', '/api/contacts', {'company_id': companies[b], 'full_name': 'Wrong workspace'}, ha, 404)
request('GET', f'/api/leads/{leads[b]}/research', headers=ha, expected=404)

roles = {}
for role in ('ADMIN', 'OPERATOR', 'REVIEWER', 'VIEWER'):
    member_email = f'{role.lower()}-{suffix}@example.test'
    invitation = request('POST', f'/api/workspaces/{a}/invitations', {'email': member_email, 'role': role}, ha, 201)
    request('POST', '/api/auth/invitations/accept', {'token': invitation['token'], 'password': password})
    request('POST', '/api/auth/invitations/accept', {'token': invitation['token'], 'password': password}, expected=400)
    token = signin(member_email, password)
    info = request('GET', '/api/auth/me', headers=auth(token))
    roles[role] = {'token': token, 'id': info['id'], 'headers': auth(token, a), 'email': member_email}
    check('member sees only its workspace', [w['id'] for w in info['workspaces']] == [a])
    request('GET', '/api/companies', headers=auth(token, b), expected=403)
    request('GET', f'/api/workspaces/{b}/members', headers=auth(token, b), expected=403)
    request('GET', '/api/companies', headers=auth(token, a))
    if role != 'ADMIN':
        request('POST', f'/api/workspaces/{a}/credentials', {'name': 'Forbidden'}, auth(token, a), 403)

request('POST', '/api/companies', {'name': 'Viewer denied'}, roles['VIEWER']['headers'], 403)
request('POST', '/api/companies', {'name': 'Reviewer denied'}, roles['REVIEWER']['headers'], 403)
request('POST', '/api/workspaces', {'name': 'Forbidden', 'slug': 'not-platform-' + suffix}, roles['ADMIN']['headers'], 403)
request('PATCH', f'/api/workspaces/{b}/members/{admin_id}', {'role': 'ADMIN'}, hb)
request('DELETE', f'/api/workspaces/{b}/members/{admin_id}', headers=hb, expected=409)

# An existing account invitation must not overwrite its password or role.
invitation = request('POST', f'/api/workspaces/{b}/invitations', {'email': roles['VIEWER']['email'], 'role': 'VIEWER'}, hb, 201)
request('POST', '/api/auth/invitations/accept', {'token': invitation['token'], 'password': 'different-password'}, expected=401)
request('POST', '/api/auth/invitations/accept', {'token': invitation['token'], 'password': password})
request('DELETE', f'/api/workspaces/{b}/members/{roles["VIEWER"]["id"]}', headers=hb)

credential = request('POST', f'/api/workspaces/{a}/credentials', {'name': 'Alpha worker'}, ha, 201)
machine = {'X-API-Key': credential['token']}
machine_context = request('GET', '/api/workspace-context', headers=machine)
check('named automation credential receives only its workspace catalog',
      machine_context['workspace']['id'] == a and machine_context['automation']['credential_kind'] == 'workspace'
      and [p['id'] for p in machine_context['products']] == [products[a]]
      and [i['id'] for i in machine_context['icps']] == [icps[a]])
check('legacy credential is explicitly marked for migration',
      request('GET', '/api/workspace-context', headers=legacy)['automation']['credential_kind'] == 'legacy')
request('GET', '/api/leads', headers=machine)
request('GET', '/api/leads', headers={**machine, 'X-Workspace-ID': b}, expected=403)
request('GET', f'/api/workspaces/{a}/members', headers=machine, expected=401)

research = {}
for workspace, headers in ((a, ha), (b, hb)):
    research[workspace] = request('POST', f'/api/leads/{leads[workspace]}/research', headers=headers, expected=201)['id']
claim = request('POST', '/api/research/claim', headers=machine)
check('worker claims only its workspace queue', claim['id'] == research[a])
request('GET', '/api/research/' + research[b], headers=machine, expected=404)
request('POST', f'/api/research/{research[a]}/sources',
    {'source_type': 'WEBSITE', 'url': 'https://example.com', 'evidence': 'Public business evidence'}, machine, 201)
request('PATCH', f'/api/research/{research[a]}/complete', {'summary': 'Research complete', 'confidence': 90}, machine)
score = request('POST', f'/api/leads/{leads[a]}/scores',
    {'total_score': 85, 'score_breakdown': {'fit': 85}, 'scoring_version': 'workspace-v1', 'rationale': 'Strong fit'}, machine, 201)
request('GET', f'/api/scoring/{score["id"]}', headers=hb, expected=404)
request('POST', f'/api/leads/{leads[a]}/product-matches',
    {'product_id': products[b], 'fit_score': 85, 'rationale': 'Wrong workspace'}, ha, 404)
match = request('POST', f'/api/leads/{leads[a]}/product-matches',
    {'product_id': products[a], 'fit_score': 85, 'rationale': 'Matches needs'}, machine, 201)
request('GET', '/api/product-matches/' + match['id'], headers=hb, expected=404)
request('PATCH', '/api/leads/' + leads[a] + '/status', {'status': 'QUALIFIED'}, ha)
action = request('POST', f'/api/leads/{leads[a]}/actions',
    {'contact_id': contacts[a], 'channel': 'EMAIL', 'action_type': 'EMAIL', 'subject': 'Hello',
     'content': 'A useful introduction', 'created_by': 'forged-person'}, roles['OPERATOR']['headers'], 201)
check('draft actor is authenticated user', action['created_by'] == roles['OPERATOR']['email'])
approval = request('POST', '/api/actions/' + action['id'] + '/submit', headers=roles['OPERATOR']['headers'], expected=201)
decision = '/api/approvals/' + approval['id'] + '/approve'
for headers in (machine, roles['OPERATOR']['headers'], roles['VIEWER']['headers']):
    request('PATCH', decision, {'decided_by': 'forged-person'}, headers, 403)
request('GET', '/api/approvals/' + approval['id'], headers=hb, expected=404)
approved = request('PATCH', decision, {'decided_by': 'forged-person'}, roles['REVIEWER']['headers'])
check('review actor is authenticated reviewer', approved['decided_by'] == roles['REVIEWER']['email'])
request('PATCH', decision, {'decided_by': 'forged-person'}, roles['REVIEWER']['headers'], 409)
request('PATCH', '/api/leads/' + leads[a] + '/status',
    {'status': 'LOST', 'reason': 'NO_RESPONSE', 'closed_by': 'forged-person'}, ha)
with SessionLocal(info={'workspace_id': UUID(a)}) as db:
    event = db.execute(text("SELECT metadata,actor_id FROM events WHERE event_type='lead_closed' ORDER BY created_at DESC LIMIT 1")).first()
    check('closure audit cannot spoof actor', event[0]['closed_by'] == admin_email and event[1] == admin_email)

# Candidate and source paths, including relation loading under RLS.
candidate_data = {'company_name': 'New Candidate ' + suffix, 'domain': 'candidate-' + suffix + '.example.test',
    'suggested_icp_profile_id': icps[a], 'icp_confidence': 0.9, 'icp_reasoning': 'Relevant public evidence',
    'source': {'source_type': 'COMPANY_WEBSITE', 'url': 'https://example.com/' + suffix}}
candidate_result = request('POST', '/api/candidates', candidate_data, ha, 201)
candidate = candidate_result.get('candidate', candidate_result)
candidate_id = candidate.get('id') or candidate_result.get('candidate_id')
check('candidate created with source evidence', bool(candidate_id))
request('GET', '/api/candidates/' + candidate_id, headers=hb, expected=404)
request('GET', '/api/candidates/' + candidate_id, headers=ha)
request('POST', '/api/candidates/' + candidate_id + '/accept', {'reviewed_by': 'forged-person'}, machine, 403)
request('POST', '/api/candidates/' + candidate_id + '/accept', {'reviewed_by': 'forged-person'}, ha)

# Raw SQL must still obey RLS. Reusing a pooled connection must not retain context.
with SessionLocal(info={'workspace_id': UUID(a)}) as db:
    check('restricted database role used', db.scalar(text('SELECT current_user')) == 'marketing_workspace_runtime')
    check('raw SQL cannot read beta', db.scalar(text('SELECT count(*) FROM companies WHERE workspace_id=:b'), {'b': b}) == 0)
    try:
        db.execute(text('SELECT * FROM users'))
        raise AssertionError('Runtime role read account table')
    except Exception as exc:
        check('runtime role cannot read account table', 'permission denied' in str(exc))
        db.rollback()
    try:
        db.add(Contact(company_id=UUID(companies[b]), full_name='Invalid link'))
        db.commit()
        raise AssertionError('Cross-workspace relation accepted')
    except IntegrityError:
        db.rollback()
        check('database rejects cross-workspace relation', True)
    try:
        db.execute(text('INSERT INTO companies(name,workspace_id) VALUES (:name,:workspace)'), {'name': 'Forbidden insert', 'workspace': b})
        db.commit()
        raise AssertionError('RLS accepted wrong workspace write')
    except Exception as exc:
        check('RLS rejects wrong workspace write', 'row-level security' in str(exc))
        db.rollback()
with SessionLocal(info={'workspace_id': UUID(b)}) as db:
    check('pool does not leak alpha context', db.scalar(text('SELECT count(*) FROM companies WHERE workspace_id=:a'), {'a': a}) == 0)
with ControlSession() as db:
    rls = db.execute(text("SELECT count(*) FROM pg_tables WHERE schemaname='public' AND rowsecurity")).scalar()
    check('all 22 business, discovery, pipeline, automation and sending tables have RLS', rls == 22)
    stored = db.get(LoginSession, token_hash(admin_token))
    check('session stored as token hash', stored is not None and stored.token_hash != admin_token)

request('DELETE', f'/api/workspaces/{a}/credentials/{credential["id"]}', headers=ha)
request('GET', '/api/leads', headers=machine, expected=401)
request('GET', '/api/workspace-context', headers=machine, expected=401)
request('PATCH', f'/api/workspaces/{a}/members/{roles["OPERATOR"]["id"]}', {'role': 'VIEWER'}, ha)
request('POST', '/api/companies', {'name': 'Revoked write'}, roles['OPERATOR']['headers'], 403)
request('DELETE', f'/api/workspaces/{a}/members/{roles["OPERATOR"]["id"]}', headers=ha)
request('GET', '/api/leads', headers=roles['OPERATOR']['headers'], expected=403)

# Browser authentication, workspace switching and role-aware API forwarding.
jar = http.cookiejar.CookieJar()
browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
def html(path, fields=None):
    req = urllib.request.Request(DASHBOARD + path, data=urllib.parse.urlencode(fields).encode() if fields else None)
    with browser.open(req, timeout=30) as response:
        return response.read().decode(), response.geturl(), response.headers

page, url, headers = html('/dashboard')
check('anonymous dashboard redirects to login', url.endswith('/login'))
csrf = re.search(r'name="csrf_token" value="([^"]+)"', page)[1]
page, url, headers = html('/login', {'email': admin_email, 'password': password, 'csrf_token': csrf})
check('browser sign in loads dashboard', url.endswith('/dashboard') and 'Sign out' in page)
check('dashboard response does not cache private data', headers['Cache-Control'] == 'no-store')
page, _, _ = html('/workspaces')
check('browser shows permitted workspaces', 'Product Alpha' in page and 'Product Beta' in page)
csrf = re.search(r'name="csrf_token" value="([^"]+)"', page)[1]
page, url, _ = html('/workspaces/switch', {'workspace_id': b, 'csrf_token': csrf})
check('workspace switch updates page branding', 'Product Beta' in page)
page, _, _ = html('/leads/new/manual')
check('manual entry uses workspace ICP configuration', 'General customers' in page)
template, _, _ = html('/leads/import/csv/template')
check('CSV template uses current workspace ICP', 'GENERAL' in template and 'LOGISTICS_HAULAGE' not in template)
columns = next(csv.reader(io.StringIO(template)))
out = io.StringIO()
writer = csv.DictWriter(out, fieldnames=columns)
writer.writeheader()
import_name = 'Workspace CSV ' + suffix
writer.writerow({'company_name': import_name, 'domain': 'csv-' + suffix + '.example.test',
                 'email': 'nameless-' + suffix + '@example.test', 'icp': 'GENERAL'})
writer.writerow({'company_name': '', 'icp': 'GENERAL'})
boundary = 'workspace-' + secrets.token_hex(12)
multipart = (f'--{boundary}\r\nContent-Disposition: form-data; name="csrf"\r\n\r\n{csrf}\r\n'
             f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="leads.csv"\r\n'
             f'Content-Type: text/csv\r\n\r\n{out.getvalue()}\r\n--{boundary}--\r\n').encode()
with browser.open(urllib.request.Request(DASHBOARD + '/leads/import/csv/preview', data=multipart,
        headers={'Content-Type': 'multipart/form-data; boundary=' + boundary}), timeout=30) as response:
    preview = response.read().decode()
check('CSV preview accepts custom ICP and nameless contact', 'Import 1 Ready Row' in preview)
import_token = re.search(r'name="import_token" value="([^"]+)"', preview)[1]
error_csv, _, _ = html('/leads/import/csv/errors/' + import_token)
check('own error-row export works', 'company_name is required' in error_csv)
html('/workspaces/switch', {'workspace_id': a, 'csrf_token': csrf})
try:
    html('/leads/import/csv/errors/' + import_token)
    raise AssertionError('Import leaked across workspaces')
except urllib.error.HTTPError as exc:
    check('CSV export rejects another workspace', exc.code == 410)
html('/workspaces/switch', {'workspace_id': b, 'csrf_token': csrf})
result, _, _ = html('/leads/import/csv/commit', {'csrf': csrf, 'import_token': import_token})
check('CSV commit creates lead in selected workspace', import_name in result and 'Created as DISCOVERED' in result)
beta_leads = request('GET', '/api/leads', headers=hb)
check('blank CSV priority defaults to MEDIUM', any(l['priority'] == 'MEDIUM' and l['id'] != leads[b] for l in beta_leads))
check('CSV company stays private to beta', not any(c['name'] == import_name for c in request('GET', '/api/companies', headers=ha)))
try:
    html('/leads/import/csv/commit', {'csrf': csrf, 'import_token': import_token})
    raise AssertionError('Import committed twice')
except urllib.error.HTTPError as exc:
    check('consumed CSV preview cannot be reused', exc.code == 410)
try:
    html('/workspaces/switch', {'workspace_id': a, 'csrf_token': 'wrong'})
    raise AssertionError('CSRF accepted')
except urllib.error.HTTPError as exc:
    check('workspace switch requires CSRF', exc.code == 403)
page, url, _ = html('/logout', {'csrf_token': csrf})
check('browser logout returns login', url.endswith('/login'))
csrf = re.search(r'name="csrf_token" value="([^"]+)"', page)[1]
page, _, _ = html('/login', {'email': roles['VIEWER']['email'], 'password': password, 'csrf_token': csrf})
check('viewer navigation hides lead intake', 'nav-add' not in page)
try:
    html('/leads/import/card/extract', {'csrf': csrf})
    raise AssertionError('Viewer could invoke OCR')
except urllib.error.HTTPError as exc:
    check('viewer cannot invoke local OCR/import mutations', exc.code == 403)

request('POST', '/api/auth/password', {'current_password': password, 'new_password': password + '-changed'}, roles['VIEWER']['headers'])
request('GET', '/api/auth/me', headers=roles['VIEWER']['headers'], expected=401)
request('POST', '/api/auth/logout', headers=auth(admin_token))
request('GET', '/api/auth/me', headers=auth(admin_token), expected=401)
for _ in range(8):
    request('POST', '/api/auth/login', {'email': 'missing-' + suffix + '@example.test', 'password': password}, expected=401)
request('POST', '/api/auth/login', {'email': 'missing-' + suffix + '@example.test', 'password': password}, expected=429)
print(f'Workspace regression PASSED: {passed} checks', flush=True)
if os.getenv('EXPORT_TEST_LOGIN') == 'true':
    # CI-only handoff to the OCR/import validator. Never log these values.
    from pathlib import Path
    os.umask(0o077)
    Path('/tmp/workspace-validation-account.json').write_text(json.dumps({'email': admin_email, 'password': password}))
