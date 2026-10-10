"""Synthetic HTTP/API/dashboard checks against a disposable workspace-test stack.

Run after migrations and restarting both servers with current code. Uses only
the standard library for HTTP, never calls providers or follows evidence links.
"""
import html
import http.cookiejar
import json
import os
from pathlib import Path
import re
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from uuid import uuid4
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if os.getenv('APP_ENV') not in ('workspace-test', 'ci'):
    raise SystemExit('Refusing integration writes outside workspace-test/ci')

from sqlalchemy import func, select
from app.auth import password_hash, token_hash
from app.db.session import ControlSession, SessionLocal
from app.models import Workspace, User, Membership, ServiceCredential, Company, Contact, Lead, LeadResearch, ResearchSource, Product, ICPProfile, ProductMatch, MarketingAction, ApprovalRequest

API = os.getenv('API_BASE_URL', 'http://127.0.0.1:8000')
DASHBOARD = os.getenv('DASHBOARD_BASE_URL', 'http://workspace-test-dashboard:8080')
passed = 0


def check(label, condition):
    global passed
    assert condition, label
    passed += 1
    print('PASS ' + label, flush=True)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), NoRedirect())
api_client = urllib.request.build_opener(NoRedirect())


def send(client, base, method, path, data=None, headers=None, form=False, expected=200):
    body = None if data is None else (urllib.parse.urlencode(data).encode() if form else json.dumps(data).encode())
    req = urllib.request.Request(base + path, data=body, method=method, headers={
        'Content-Type': 'application/x-www-form-urlencoded' if form else 'application/json', **(headers or {})})
    try:
        response = client.open(req, timeout=25)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        status, content, result_headers = response.code, response.read().decode(), response.headers
    # Never dump request bodies, credentials, cookies or provider responses.
    if status != expected:
        raise AssertionError(f'{method} {path}: expected {expected}, received {status}')
    check(f'{method} {path} returns {expected}', True)
    return content, result_headers


def api(method, path, data=None, headers=None, expected=200):
    content, _ = send(api_client, API, method, path, data, headers, expected=expected)
    return json.loads(content or 'null')


def web(method, path, data=None, expected=200):
    return send(browser, DASHBOARD, method, path, data=data, form=True, expected=expected)


def csrf(content):
    match = re.search(r'name="(?:csrf_token|csrf)"\s+value="([^"]+)"', content)
    if not match:
        raise AssertionError('Expected CSRF form token')
    return html.unescape(match.group(1))


suffix = secrets.token_hex(6)
password = secrets.token_urlsafe(24)
machine_key = secrets.token_urlsafe(32)
identities = {}
with ControlSession() as db:
    workspace = Workspace(name='Synthetic HTTP campaign', slug='campaign-http-' + suffix)
    other = Workspace(name='Synthetic isolated HTTP campaign', slug='campaign-http-other-' + suffix)
    db.add_all([workspace, other])
    db.flush()
    workspace_id, other_id = workspace.id, other.id
    for role in ['ADMIN', 'OPERATOR', 'REVIEWER', 'VIEWER']:
        user = User(email=f'campaign-http-{role.lower()}-{suffix}@example.test', password_hash=password_hash(password))
        db.add(user)
        db.flush()
        db.add(Membership(workspace_id=workspace.id, user_id=user.id, role=role))
        if role == 'ADMIN':
            db.add(Membership(workspace_id=other.id, user_id=user.id, role='ADMIN'))
        identities[role] = user.email
    db.add(ServiceCredential(workspace_id=workspace.id, name='Synthetic HTTP worker', token_hash=token_hash(machine_key)))
    db.commit()

with SessionLocal(info={'workspace_id': workspace_id}) as db:
    company = Company(name='Synthetic HTTP Fleet')
    product = Product(code='HTTP', name='Synthetic HTTP Fleet Product', description='A synthetic catalogue of product functionality for test-only fleet companies. ' * 3)
    icp = ICPProfile(code='HTTP', name='Synthetic HTTP ICP')
    db.add_all([company, product, icp])
    db.flush()
    contact = Contact(company_id=company.id, full_name='Synthetic HTTP Contact', email=f'contact-{suffix}@example.test', status='ACTIVE', source_url='https://example.test/http-fleet', updated_at=datetime.now(timezone.utc))
    db.add(contact)
    db.flush()
    lead = Lead(company_id=company.id, primary_contact_id=contact.id, icp_profile_id=icp.id, status='QUALIFIED', current_score=80)
    db.add(lead)
    db.flush()
    research = LeadResearch(lead_id=lead.id, research_status='COMPLETED', completed_at=datetime.now(timezone.utc), summary='Synthetic evidence for HTTP review')
    db.add(research)
    db.flush()
    evidence_text = 'Synthetic HTTP company operates a fleet. Public contact: ' + contact.email
    db.add_all([ResearchSource(research_id=research.id, url='https://example.test/http-fleet', title='Synthetic HTTP evidence', evidence=evidence_text, observed_at=datetime.now(timezone.utc)),
                ProductMatch(lead_id=lead.id, product_id=product.id, fit_score=80)])
    db.commit()
    lead_id = str(lead.id)

auth = {}
for role, email in identities.items():
    token = api('POST', '/api/auth/login', {'email': email, 'password': password})['token']
    auth[role] = {'Authorization': 'Bearer ' + token, 'X-Workspace-ID': str(workspace_id)}
machine = {'X-API-Key': machine_key}
generate_path = f'/api/leads/{lead_id}/campaign-proposals'
payload = {'idempotency_key': str(uuid4()), 'max_estimated_cost_usd': 0}
api('POST', generate_path, payload, expected=401)
for headers in [auth['VIEWER'], machine]:
    api('POST', generate_path, payload, headers, 403)
api('POST', generate_path, {**payload, 'max_estimated_cost_usd': -1}, auth['ADMIN'], 422)
proposal = api('POST', generate_path, payload, auth['ADMIN'])
proposal_id = proposal['id']
proposal_path = '/api/campaign-proposals/' + proposal_id
check('HTTP mock strategy and unknown optional asset cost', proposal['provider'] == 'mock' and proposal['actual_cost_usd'] == 0 and proposal['strategy']['assets'][0]['estimated_cost_usd'] is None)
check('HTTP idempotency preserves proposal', api('POST', generate_path, payload, auth['ADMIN'])['id'] == proposal_id)
check('HTTP list contains persisted proposal', any(p['id'] == proposal_id for p in api('GET', generate_path, headers=auth['ADMIN'])))
check('HTTP read matches persisted evidence', api('GET', proposal_path, headers=auth['ADMIN'])['strategy']['claims'][0]['text'] == evidence_text)
api('GET', proposal_path, headers={**auth['ADMIN'], 'X-Workspace-ID': str(other_id)}, expected=404)
edited = json.loads(json.dumps(proposal['strategy']))
edited['claims'][0]['text'] = 'Fabricated urgent need'
api('PATCH', proposal_path, {'expected_version': 1, 'strategy': edited}, auth['ADMIN'], 422)
api('PATCH', proposal_path, {'expected_version': 99, 'strategy': proposal['strategy']}, auth['ADMIN'], 409)
for headers in [auth['VIEWER'], machine]:
    api('PATCH', proposal_path, {'expected_version': 1, 'strategy': proposal['strategy']}, headers, 403)
for headers in [auth['OPERATOR'], auth['VIEWER'], machine]:
    api('POST', proposal_path + '/review', {'expected_version': 1, 'decision': 'REVIEWED'}, headers, 403)

# The dashboard uses the real login flow, cookie session and CSRF forms.
login_html, _ = web('GET', '/login')
web('POST', '/login', {'email': identities['ADMIN'], 'password': password, 'csrf_token': csrf(login_html)}, 303)
workspace_html, _ = web('GET', '/workspaces')
web('POST', '/workspaces/switch', {'workspace_id': str(workspace_id), 'csrf_token': csrf(workspace_html)}, 303)
lead_html, _ = web('GET', '/leads/' + lead_id)
token = csrf(lead_html)
before_count = len(api('GET', generate_path, headers=auth['ADMIN']))
bad, redirect = web('POST', f'/leads/{lead_id}/campaign-proposals', {'csrf': 'invalid', 'idempotency_key': str(uuid4())}, 303)
check('dashboard generation CSRF blocks persistence', 'error=csrf' in redirect['Location'] and len(api('GET', generate_path, headers=auth['ADMIN'])) == before_count)
_, redirect = web('POST', f'/leads/{lead_id}/campaign-proposals', {'csrf': token, 'idempotency_key': str(uuid4())}, 303)
dashboard_path = redirect['Location']
check('dashboard generation opens saved proposal', dashboard_path.startswith('/campaign-proposals/'))
dashboard_id = dashboard_path.rsplit('/', 1)[-1]
dashboard_api_path = '/api/campaign-proposals/' + dashboard_id
proposal_html, _ = web('GET', dashboard_path)
check('dashboard presents saved strategy evidence and costs', 'Synthetic HTTP company operates a fleet.' in proposal_html and 'https://example.test/http-fleet' in proposal_html and 'Not priced' in proposal_html and 'EMAIL draft' in proposal_html)
check('dashboard strategy review is separate from outbound', 'Strategy review does not approve an outbound message' in proposal_html and 'Send approved email' not in proposal_html)
token = csrf(proposal_html)
current = api('GET', dashboard_api_path, headers=auth['ADMIN'])
form = {'csrf': 'invalid', 'expected_version': current['version'], 'strategy_json': json.dumps(current['strategy']), 'objective': 'Synthetic reviewed objective', 'positioning': current['strategy']['positioning']}
for index, channel in enumerate(current['strategy']['channels']):
    for field in ['subject', 'body', 'rationale']:
        form[f'channel_{index}_{field}'] = channel[field] or ''
_, redirect = web('POST', dashboard_path + '/edit', form, 303)
check('dashboard edit CSRF blocks persistence', 'error=csrf' in redirect['Location'] and api('GET', dashboard_api_path, headers=auth['ADMIN'])['version'] == 1)
form['csrf'] = token
form['objective'] = '<script>synthetic-objective</script>'
web('POST', dashboard_path + '/edit', form, 303)
current = api('GET', dashboard_api_path, headers=auth['ADMIN'])
check('dashboard edits persist new draft version', current['version'] == 2 and current['strategy']['objective'] == form['objective'])
proposal_html, _ = web('GET', dashboard_path)
check('live HTML escapes editable content', '<script>synthetic-objective</script>' not in proposal_html and '&lt;script&gt;synthetic-objective&lt;/script&gt;' in proposal_html)
review_form = {'csrf': 'invalid', 'expected_version': 2, 'decision': 'REVIEWED', 'notes': 'Synthetic HTTP review'}
_, redirect = web('POST', dashboard_path + '/review', review_form, 303)
check('dashboard review CSRF blocks decision', 'error=csrf' in redirect['Location'] and api('GET', dashboard_api_path, headers=auth['ADMIN'])['status'] == 'DRAFT')
review_form['csrf'] = csrf(proposal_html)
web('POST', dashboard_path + '/review', review_form, 303)
current = api('GET', dashboard_api_path, headers=auth['ADMIN'])
check('dashboard human review persists', current['status'] == 'REVIEWED' and current['version'] == 3 and current['reviewed_by'] == identities['ADMIN'])
api('POST', dashboard_api_path + '/review', {'expected_version': 2, 'decision': 'REJECTED'}, auth['REVIEWER'], 409)
api('PATCH', dashboard_api_path, {'expected_version': 3, 'strategy': current['strategy']}, auth['OPERATOR'])
current = api('GET', dashboard_api_path, headers=auth['ADMIN'])
check('HTTP operator edit invalidates human review', current['status'] == 'DRAFT' and current['version'] == 4 and current['reviewed_at'] is None)
api('POST', dashboard_api_path + '/review', {'expected_version': 4, 'decision': 'REJECTED', 'notes': 'Synthetic reviewer rejection'}, auth['REVIEWER'])
check('HTTP reviewer rejection persists', api('GET', dashboard_api_path, headers=auth['ADMIN'])['status'] == 'REJECTED')
with SessionLocal(info={'workspace_id': workspace_id}) as db:
    check('HTTP and dashboard produce no outbound actions', db.scalar(select(func.count()).select_from(MarketingAction)) == 0)
    check('HTTP and dashboard produce no outbound approvals', db.scalar(select(func.count()).select_from(ApprovalRequest)) == 0)
print(f'{passed} campaign HTTP/dashboard integration checks passed')
