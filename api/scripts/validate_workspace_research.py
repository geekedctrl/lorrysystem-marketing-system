"""Research queue, workspace boundaries and dashboard regression in disposable environments."""
import http.cookiejar
import json
import os
import re
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

sys.path.insert(0, '/app')
from app.auth import password_hash
from app.db.session import ControlSession, SessionLocal
from app.models.leads import LeadResearch
from app.models.workspaces import Membership, User
from app.workspace_context import LORRYSYSTEM_WORKSPACE_ID

if os.getenv('APP_ENV') not in ('ci', 'workspace-test'):
    raise SystemExit('Refusing to run outside disposable environments')
BASE = os.getenv('API_BASE_URL', 'http://127.0.0.1:8000')
DASHBOARD = os.getenv('DASHBOARD_BASE_URL', 'http://workspace-test-dashboard:8080')


def call(method, path, data=None, headers=None, expected=200):
    request = urllib.request.Request(BASE + path, method=method,
        data=json.dumps(data).encode() if data is not None else None,
        headers={'Content-Type': 'application/json', **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status, body = response.status, json.load(response)
    except urllib.error.HTTPError as error:
        status, body = error.code, json.load(error)
    assert status == expected, f'{method} {path}: {status}, expected {expected}'
    return body


suffix, password = secrets.token_hex(5), secrets.token_urlsafe(24)
email = f'research-admin-{suffix}@example.test'
with ControlSession() as db:
    user = User(email=email, password_hash=password_hash(password), platform_admin=True)
    db.add(user); db.flush()
    db.add(Membership(workspace_id=LORRYSYSTEM_WORKSPACE_ID, user_id=user.id, role='ADMIN'))
    db.commit(); user_id = user.id
human = {'Authorization': 'Bearer ' + call('POST', '/api/auth/login', {'email': email, 'password': password})['token']}
fixtures = []
for label in ('Alpha', 'Beta'):
    workspace = call('POST', '/api/workspaces', {'name': f'Research {label}', 'slug': f'research-{label.lower()}-{suffix}'}, human, 201)['id']
    headers = {**human, 'X-Workspace-ID': workspace}
    key = call('POST', f'/api/workspaces/{workspace}/credentials', {'name': 'Research worker'}, headers, 201)['token']
    service = {'X-API-Key': key, 'X-Workspace-ID': workspace}
    icp = call('POST', f'/api/workspaces/{workspace}/catalog/icps', {'code': 'FLEET', 'name': 'Fleet operators'}, headers, 201)['id']
    call('POST', f'/api/workspaces/{workspace}/catalog/products', {'code': 'MAIN', 'name': f'{label} operations software'}, headers, 201)
    leads = []
    for index in range(2):
        domain = 'acme.com' if index == 0 else 'second-acme.com'
        candidate = call('POST', '/api/candidates', {'company_name': 'Acme Logistics' if index == 0 else 'Second Acme',
            'website_url': 'https://' + domain + '/', 'domain': domain, 'suggested_icp_profile_id': icp,
            'icp_confidence': 0.9, 'icp_reasoning': 'Public road haulage services match fleet operators.',
            'source': {'source_type': 'COMPANY_WEBSITE', 'url': 'https://' + domain + '/',
                'evidence': 'Acme Logistics provides road haulage and freight forwarding across Malaysia.'}}, service, 201)['candidate']
        call('POST', '/api/candidates/' + candidate['id'] + '/accept', {'reviewed_by': 'worker'}, service, 403)
        accepted = call('POST', '/api/candidates/' + candidate['id'] + '/accept', {'reviewed_by': email}, headers)
        lead = accepted['lead_id']
        jobs = call('GET', f'/api/leads/{lead}/research', headers=service)
        assert len(jobs) == 1 and jobs[0]['research_status'] == 'PENDING'
        call('POST', f'/api/leads/{lead}/research', {}, headers, 409)
        leads.append(lead)
    fixtures.append({'workspace_id': workspace, 'human': headers, 'service': service, 'leads': leads})
print('PASS human acceptance creates exactly one pending job; automation cannot accept or duplicate it', flush=True)
a, b = fixtures
call('POST', '/api/research/fetch-public', {'url': 'http://127.0.0.1/private'}, expected=401)
for fixture in fixtures:
    fetch = call('POST', '/api/research/fetch-public', {'url': 'http://127.0.0.1/private'}, fixture['service'])
    assert fetch['fetch_status'] != 'SUCCESS' and not fetch['body']
call('POST', '/api/research/fetch-public', {'url': 'http://127.0.0.1/private'}, {**a['service'], 'X-Workspace-ID': b['workspace_id']}, 403)
print('PASS named workspace credentials authenticate guarded fetch; private targets and workspace mismatch stay blocked', flush=True)

def claim():
    return call('POST', '/api/research/claim?max_running=1', headers=a['service'])
with ThreadPoolExecutor(max_workers=2) as pool:
    claims = list(pool.map(lambda _: claim(), range(2)))
assert sum(item is not None for item in claims) == 1
job = next(item for item in claims if item)
assert job['research_status'] == 'RUNNING'
context = call('GET', f"/api/research/{job['id']}/context", headers=a['service'])
assert context['accepted_candidate']['accepted_lead_id'] == job['lead_id']
call('GET', f"/api/research/{job['id']}/context", headers=b['service'], expected=404)
call('PATCH', f"/api/research/{job['id']}/fail", {'reason': 'FOREIGN'}, b['service'], 404)
source = {'source_type': 'WEBSITE', 'url': 'https://acme.com/', 'title': 'Acme public services',
    'evidence': 'Acme Logistics provides road haulage. Jane Tan is Operations Manager.', 'confidence': 90}
call('POST', f"/api/research/{job['id']}/sources", source, a['service'], 201)
report = {'summary': 'Acme Logistics offers road haulage services.', 'confidence': 85,
    'model_provider': 'xkiro', 'model_name': 'mistralai/mistral-large-2512',
    'company_facts': {'research_version': 'workspace-research-v1', 'facts': [
        {'category': 'SERVICES', 'fact': 'Provides road haulage services', 'evidence_status': 'OBSERVED',
            'evidence_quote': 'provides road haulage', 'source_urls': ['https://acme.com/'], 'confidence': 90}],
        'people': [{'name': 'Jane Tan', 'job_title': 'Operations Manager', 'role_classification': 'OPERATIONAL_CONTACT',
            'business_email': None, 'business_phone': None, 'linkedin_url': None, 'source_urls': ['https://acme.com/'],
            'evidence_quote': 'Jane Tan is Operations Manager', 'confidence': 85}],
        'coverage': {'official_pages_read': 1, 'pages_fetched': 1}, 'missing_information': ['Fleet count is unknown']}}
done = call('PATCH', f"/api/research/{job['id']}/complete", report, a['service'])
assert done['research_status'] == 'COMPLETED'
assert call('GET', '/api/leads/' + job['lead_id'], headers=a['service'])['status'] == 'RESEARCHING'
assert call('GET', '/api/contacts', headers=a['service']) == []
print('PASS concurrent queue capacity, cross-workspace isolation and sourced completion without automatic qualification/contacts', flush=True)
stalled = claim()
other = call('POST', '/api/research/claim?max_running=1', headers=b['service'])
with SessionLocal(info={'workspace_id': UUID(a['workspace_id'])}) as db:
    row = db.get(LeadResearch, UUID(stalled['id']))
    row.started_at = datetime.now(timezone.utc) - timedelta(minutes=31); db.commit()
assert call('POST', '/api/research/recover-stale', headers=b['service'])['recovered'] == 0
assert call('POST', '/api/research/recover-stale', headers=a['service'])['recovered'] == 1
assert call('GET', '/api/research/' + stalled['id'], headers=a['service'])['raw_output']['failure_reason'] == 'WORKER_TIMEOUT'
call('PATCH', '/api/research/' + other['id'] + '/fail', {'reason': 'FIXTURE_RESET'}, b['service'])
print('PASS stalled job recovery affects only its workspace and retains failure history', flush=True)

jar = http.cookiejar.CookieJar()
browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
def page(path):
    with browser.open(DASHBOARD + path, timeout=20) as response:
        return response.read().decode()
def form(path, values):
    return browser.open(urllib.request.Request(DASHBOARD + path, data=urllib.parse.urlencode(values).encode()), timeout=20)
csrf = re.search(r'name="csrf_token" value="([^"]+)"', page('/login'))[1]
with form('/login', {'csrf_token': csrf, 'email': email, 'password': password}): pass
csrf = re.search(r'name="csrf_token" value="([^"]+)"', page('/workspaces'))[1]
with form('/workspaces/switch', {'csrf_token': csrf, 'workspace_id': a['workspace_id']}): pass
html = page('/leads/' + job['lead_id'])
for text in ('Provides road haulage services', 'Jane Tan', 'Operations Manager', 'Source 1', 'Fleet count is unknown', 'Run research again'):
    assert text in html, text
with form('/leads/' + job['lead_id'] + '/research', {'csrf': 'invalid'}): pass
assert len(call('GET', '/api/leads/' + job['lead_id'] + '/research', headers=a['service'])) == 1
with form('/leads/' + job['lead_id'] + '/research', {'csrf': csrf}): pass
assert 'Waiting for the workspace research worker' in page('/leads/' + job['lead_id'])
with form('/workspaces/switch', {'csrf_token': csrf, 'workspace_id': b['workspace_id']}): pass
try:
    page('/leads/' + job['lead_id']); raise AssertionError('Foreign dashboard lead was visible')
except urllib.error.HTTPError as error:
    assert error.code == 404
with ControlSession() as db:
    member = db.get(Membership, (UUID(b['workspace_id']), user_id)); member.role = 'VIEWER'; db.commit()
call('POST', '/api/leads/' + b['leads'][0] + '/research', {}, b['human'], 403)
try:
    form('/leads/' + b['leads'][0] + '/research', {'csrf': csrf}); raise AssertionError('Viewer queued research')
except urllib.error.HTTPError as error:
    assert error.code == 403
print('PASS dashboard findings, people, sources, retry CSRF, pending refresh and viewer boundaries', flush=True)

if os.getenv('EXPORT_RESEARCH_FIXTURE') == 'true':
    # Local native n8n test consumes these disposable tokens privately.
    Path('/tmp/research-fixtures.json').write_text(json.dumps(fixtures))
print('Workspace research regression PASSED', flush=True)
