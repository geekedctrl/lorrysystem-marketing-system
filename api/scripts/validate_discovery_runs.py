"""Dashboard discovery boundary regression; disposable environments only.

Runs with a local webhook stub: no paid search, model calls or customer writes.
"""
import http.cookiejar
import json
import os
import queue
import re
import secrets
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import UUID

sys.path.insert(0, '/app')
from sqlalchemy import select
from app.auth import password_hash
from app.db.session import ControlSession, SessionLocal
from app.models.discovery_runs import DiscoveryRun
from app.models.workspaces import Membership, User
from app.workspace_context import LORRYSYSTEM_WORKSPACE_ID

if os.getenv('APP_ENV') not in ('ci', 'workspace-test'):
    raise SystemExit('Refusing to run outside disposable test environments')

BASE = os.getenv('API_BASE_URL', 'http://127.0.0.1:8000')
DASHBOARD = os.getenv('DASHBOARD_BASE_URL', 'http://workspace-test-dashboard:8080')
received = queue.Queue()


class Webhook(BaseHTTPRequestHandler):
    mode = 200
    def do_POST(self):
        received.put(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
        self.send_response(self.mode)
        if self.mode == 302:
            self.send_header('Location', '/should-not-follow')
        self.end_headers()
        self.wfile.write(b'{}')
    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(('127.0.0.1', 0), Webhook)
threading.Thread(target=server.serve_forever, daemon=True).start()
webhook = f'http://127.0.0.1:{server.server_port}/webhook/test-discovery'


def call(method, path, data=None, headers=None, expected=200):
    request = urllib.request.Request(BASE + path, method=method,
        data=json.dumps(data).encode() if data is not None else None,
        headers={'Content-Type': 'application/json', **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            status, body = response.status, json.load(response)
    except urllib.error.HTTPError as error:
        status, body = error.code, json.load(error)
    assert status == expected, f'{method} {path}: {status}, expected {expected}'
    return body


suffix, password = secrets.token_hex(5), secrets.token_urlsafe(24)
email = f'discovery-admin-{suffix}@example.test'
with ControlSession() as db:
    user = User(email=email, password_hash=password_hash(password), platform_admin=True)
    db.add(user); db.flush()
    db.add(Membership(workspace_id=LORRYSYSTEM_WORKSPACE_ID, user_id=user.id, role='ADMIN'))
    db.commit()
    user_id = user.id
token = call('POST', '/api/auth/login', {'email': email, 'password': password})['token']
human = {'Authorization': 'Bearer ' + token}
a = call('POST', '/api/workspaces', {'name': 'Discovery A', 'slug': 'discovery-a-' + suffix}, human, 201)['id']
b = call('POST', '/api/workspaces', {'name': 'Discovery B', 'slug': 'discovery-b-' + suffix}, human, 201)['id']
ha, hb = {**human, 'X-Workspace-ID': a}, {**human, 'X-Workspace-ID': b}
service = {}
for workspace, headers in ((a, ha), (b, hb)):
    key = call('POST', f'/api/workspaces/{workspace}/credentials', {'name': 'Discovery worker'}, headers, 201)['token']
    service[workspace] = {'X-API-Key': key}
call('POST', '/api/discovery/runs', {'query': 'New customer websites'}, ha, 409)
call('PUT', '/api/discovery/config', {'webhook_url': 'http://localhost/private', 'default_query': 'New customers'}, ha, 422)
call('PUT', '/api/discovery/config', {'webhook_url': webhook, 'default_query': 'New customer websites'}, ha)
assert not call('GET', '/api/discovery/config', headers=hb)['configured']
assert 'webhook_url' not in call('GET', '/api/discovery/config', headers=service[a])
call('POST', '/api/discovery/runs', {'query': 'New customer websites'}, service[a], 403)
call('PUT', '/api/discovery/config', {'webhook_url': webhook, 'default_query': 'New customers'}, service[a], 403)
print('PASS discovery configuration is workspace-scoped and human-controlled', flush=True)

def start(expected=202):
    return call('POST', '/api/discovery/runs', {'query': 'Fresh company websites', 'target_new_companies': 5}, ha, expected)

run = start(); payload = received.get(timeout=2)
assert payload['run_id'] == run['id'] and payload['workspace_id'] == a
assert 'run_token' not in run and 'token_hash' not in run
start(409)
proof = {'run_token': payload['run_token']}
path = '/api/discovery/runs/' + run['id']
call('POST', path + '/claim', proof, service[b], 404)
call('POST', path + '/claim', {'run_token': 'x' * 64}, service[a], 403)
call('POST', path + '/claim', proof, ha, 403)
claimed = call('POST', path + '/claim', proof, service[a])
assert claimed['query'] == run['query'] and claimed['new_only'] and claimed['max_results_scanned'] == 40
call('POST', path + '/claim', proof, service[a], 409)
start(409)
complete = {**proof, 'status': 'COMPLETED', 'summary': {'new_candidates': 4, 'websites_fetched': 5}}
call('POST', path + '/complete', {**complete, 'summary': {'new_candidates': -1}}, service[a], 422)
call('POST', path + '/complete', complete, service[a])
call('POST', path + '/complete', complete, service[a])
assert call('GET', '/api/discovery/runs', headers=ha)[0]['summary']['new_candidates'] == 4
assert call('GET', '/api/discovery/runs', headers=hb) == []
print('PASS one-use claims, replay protection, completion and cross-workspace isolation', flush=True)

# Database constraint remains effective when starts race.
def racing_start():
    try:
        call('POST', '/api/discovery/runs', {'query': 'Concurrent discovery'}, ha, 202)
        return True
    except AssertionError:
        return False
with ThreadPoolExecutor(max_workers=2) as pool:
    results = list(pool.map(lambda _: racing_start(), range(2)))
assert sum(results) == 1
payload = received.get(timeout=2)
path = '/api/discovery/runs/' + payload['run_id']
proof = {'run_token': payload['run_token']}
call('POST', path + '/claim', proof, service[a])
call('POST', path + '/complete', {**proof, 'status': 'FAILED', 'error_code': 'WORKFLOW_FAILED'}, service[a])
for mode in (503, 302):
    Webhook.mode = mode
    assert start()['status'] == 'FAILED'
    received.get(timeout=2)
Webhook.mode = 200
print('PASS concurrent starts, worker errors and webhook rejection/redirects', flush=True)

run = start(); received.get(timeout=2)
with SessionLocal(info={'workspace_id': UUID(a)}) as db:
    row = db.get(DiscoveryRun, UUID(run['id']))
    row.created_at = datetime.now(timezone.utc) - timedelta(minutes=6)
    db.commit()
assert next(item for item in call('GET', '/api/discovery/runs', headers=ha) if item['id'] == run['id'])['status'] == 'TIMED_OUT'
print('PASS stale runs stop blocking discovery', flush=True)

jar = http.cookiejar.CookieJar()
browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
def page(path):
    with browser.open(DASHBOARD + path, timeout=15) as response:
        return response.read().decode()
def form(path, values):
    return browser.open(urllib.request.Request(DASHBOARD + path, data=urllib.parse.urlencode(values).encode()), timeout=15)
csrf = re.search(r'name="csrf_token" value="([^"]+)"', page('/login'))[1]
with form('/login', {'csrf_token': csrf, 'email': email, 'password': password}): pass
csrf = re.search(r'name="csrf_token" value="([^"]+)"', page('/workspaces'))[1]
with form('/workspaces/switch', {'csrf_token': csrf, 'workspace_id': a}): pass
markup = page('/discovered-leads')
assert 'Find Leads' in markup and 'Fresh company websites' in markup
try:
    form('/discovered-leads/find', {'csrf_token': 'invalid', 'query': 'New customer websites'})
    raise AssertionError('CSRF accepted')
except urllib.error.HTTPError as error:
    assert error.code == 403
with form('/discovered-leads/find', {'csrf_token': csrf, 'query': 'Dashboard discovery', 'target_new_companies': 3}) as response:
    assert 'Finding leads' in response.read().decode()
payload = received.get(timeout=2)
path = '/api/discovery/runs/' + payload['run_id']
proof = {'run_token': payload['run_token']}
call('POST', path + '/claim', proof, service[a])
call('POST', path + '/complete', {**proof, 'status': 'COMPLETED', 'summary': {'new_candidates': 2, 'websites_fetched': 3}}, service[a])
assert '2 new candidates saved from 3 websites' in page('/discovered-leads')
assert json.loads(page('/discovered-leads/discovery-status'))[0]['status'] == 'COMPLETED'
with form('/workspaces/switch', {'csrf_token': csrf, 'workspace_id': b}): pass
assert json.loads(page('/discovered-leads/discovery-status')) == []
with ControlSession() as db:
    member = db.get(Membership, (UUID(a), user_id)); member.role = 'VIEWER'; db.commit()
call('POST', '/api/discovery/runs', {'query': 'Blocked discovery'}, ha, 403)
print('PASS dashboard button, CSRF, status refresh, workspace switch and viewer restriction', flush=True)
bootstrap = Path('/tmp/discovery-bootstrap-' + suffix + '.json')
bootstrap.write_text(json.dumps({'workspace_id': b, 'webhook_url': webhook, 'default_query': 'Bootstrap customers', 'enabled': True}))
env = {**os.environ, 'DISCOVERY_BOOTSTRAP_FILE': str(bootstrap)}
subprocess.run([sys.executable, '-m', 'app.discovery_bootstrap'], env=env, check=True)
assert call('GET', '/api/discovery/config', headers=hb)['enabled']
call('PUT', '/api/discovery/config', {'webhook_url': webhook, 'default_query': 'Keep administrator choice', 'enabled': False}, hb)
subprocess.run([sys.executable, '-m', 'app.discovery_bootstrap'], env=env, check=True)
configuration = call('GET', '/api/discovery/config', headers=hb)
assert not configuration['enabled'] and configuration['default_query'] == 'Keep administrator choice'
bootstrap.unlink()
print('PASS deployment bootstrap initializes once and preserves disabled administrator settings', flush=True)
server.shutdown()
print('Discovery run regression PASSED', flush=True)
