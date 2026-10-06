import os
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from .api_client import MarketingAPIError
from .workspace_context import request_auth, request_icps

router = APIRouter()
templates = Jinja2Templates(directory='app/templates')


class WorkspaceDashboardMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, api):
        super().__init__(app)
        self.api = api

    async def dispatch(self, request, call_next):
        path = request.url.path
        public = path in ('/login', '/invitation', '/health') or path.startswith('/static/')
        if public:
            response = await call_next(request)
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Referrer-Policy'] = 'no-referrer'
            return response
        token = request.session.get('auth_token')
        if not token:
            return RedirectResponse('/login', status_code=302)
        auth_token = request_auth.set({'token': token})
        icp_token = request_icps.set([])
        try:
            try:
                user = await self.api.get('/api/auth/me')
            except MarketingAPIError as exc:
                if exc.status_code == 401:
                    request.session.clear()
                    return RedirectResponse('/login', status_code=302)
                return HTMLResponse('Account service is temporarily unavailable.', status_code=503)
            requested = request.session.get('workspace_id')
            selected = next((w for w in user['workspaces'] if w['id'] == requested), None)
            if not requested and user['workspaces']:
                selected = user['workspaces'][0]
                request.session['workspace_id'] = selected['id']
            request.state.user = user
            request.state.workspace = selected
            request_auth.set({'token': token, 'workspace_id': selected['id'] if selected else None})
            if selected and request.method == 'POST' and not path.startswith('/workspaces/') and path not in ('/logout', '/account/password'):
                allowed = ('ADMIN', 'REVIEWER') if path.startswith('/approvals/') else ('ADMIN', 'OPERATOR')
                if selected['role'] not in allowed:
                    return HTMLResponse('Your workspace role does not allow this action.', status_code=403)
            if selected:
                try:
                    icps = await self.api.get('/api/icp-profiles')
                    request_icps.set([{'id': i['id'], 'label': i['name'], 'code': i['code']} for i in icps])
                except MarketingAPIError:
                    return HTMLResponse('Workspace is temporarily unavailable.', status_code=503)
            elif path not in ('/workspaces', '/logout', '/account/password') and not path.startswith('/workspaces/'):
                return RedirectResponse('/workspaces', status_code=302)
            response = await call_next(request)
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Referrer-Policy'] = 'no-referrer'
            return response
        finally:
            request_auth.reset(auth_token)
            request_icps.reset(icp_token)


def csrf(request):
    if not request.session.get('csrf_token'):
        request.session['csrf_token'] = secrets.token_urlsafe(32)
    return request.session['csrf_token']


def valid_csrf(request, value):
    return bool(value and secrets.compare_digest(value, request.session.get('csrf_token', '')))


def page(request, template, **context):
    return templates.TemplateResponse(request=request, name=template, context={
        'csrf_token': csrf(request), 'reviewer_identity': getattr(request.state, 'user', {}).get('email', ''),
        'current_user': getattr(request.state, 'user', None),
        'current_workspace': getattr(request.state, 'workspace', None), **context})


@router.get('/login', response_class=HTMLResponse)
async def login_page(request: Request):
    return page(request, 'login.html')


@router.post('/login')
async def login(request: Request, email: str = Form(...), password: str = Form(...), csrf_token: str = Form(...)):
    if not valid_csrf(request, csrf_token):
        return HTMLResponse('Invalid form token. Reload the page.', status_code=403)
    try:
        result = await request.app.state.api.post('/api/auth/login', json={'email': email, 'password': password}, authenticated=False)
    except MarketingAPIError as exc:
        return page(request, 'login.html', error=exc.message)
    request.session.clear()
    request.session['auth_token'] = result['token']
    return RedirectResponse('/dashboard', status_code=303)


@router.post('/logout')
async def logout(request: Request, csrf_token: str = Form(...)):
    if not valid_csrf(request, csrf_token):
        return HTMLResponse('Invalid form token.', status_code=403)
    try:
        await request.app.state.api.post('/api/auth/logout')
    except MarketingAPIError:
        pass
    request.session.clear()
    return RedirectResponse('/login', status_code=303)


@router.get('/invitation', response_class=HTMLResponse)
async def invitation_page(request: Request, token: str = ''):
    return page(request, 'invitation.html', token=token)


@router.post('/invitation')
async def accept_invitation(request: Request, token: str = Form(...), password: str = Form(...), csrf_token: str = Form(...)):
    if not valid_csrf(request, csrf_token):
        return HTMLResponse('Invalid form token.', status_code=403)
    try:
        await request.app.state.api.post('/api/auth/invitations/accept', json={'token': token, 'password': password}, authenticated=False)
    except MarketingAPIError as exc:
        return page(request, 'invitation.html', token=token, error=exc.message)
    return RedirectResponse('/login', status_code=303)


@router.get('/workspaces', response_class=HTMLResponse)
async def workspaces(request: Request, message: str = ''):
    selected = request.state.workspace
    members, credentials, audit, products, icps = [], [], [], [], []
    if selected and selected['role'] == 'ADMIN':
        api = request.app.state.api
        prefix = '/api/workspaces/' + selected['id']
        members = await api.get(prefix + '/members')
        credentials = await api.get(prefix + '/credentials')
        audit = await api.get(prefix + '/audit')
        products = await api.get('/api/products')
        icps = await api.get('/api/icp-profiles')
    return page(request, 'workspaces.html', members=members, credentials=credentials,
                audit=audit, products=products, icps=icps, message=message)


@router.post('/workspaces/switch')
async def switch(request: Request, workspace_id: str = Form(...), csrf_token: str = Form(...)):
    if not valid_csrf(request, csrf_token):
        return HTMLResponse('Invalid form token.', status_code=403)
    if not any(w['id'] == workspace_id for w in request.state.user['workspaces']):
        return HTMLResponse('Workspace access denied.', status_code=403)
    request.session['workspace_id'] = workspace_id
    return RedirectResponse('/dashboard', status_code=303)


@router.post('/workspaces/manage')
async def manage(request: Request):
    form = await request.form()
    if not valid_csrf(request, str(form.get('csrf_token', ''))):
        return HTMLResponse('Invalid form token.', status_code=403)
    action = form.get('action')
    selected = request.state.workspace
    prefix = '/api/workspaces/' + selected['id'] if selected else ''
    api = request.app.state.api
    # All authorization is checked again by the API, including malicious form actions.
    try:
        if action == 'create':
            result = await api.post('/api/workspaces', json={'name': form.get('name'), 'slug': form.get('slug')})
            request.session['workspace_id'] = result['id']
        elif action == 'invite':
            result = await api.post(prefix + '/invitations', json={'email': form.get('email'), 'role': form.get('role')})
            # Show a relative link; never trust Host when generating invitation URLs.
            return page(request, 'workspace_secret.html', heading='Invitation created',
                        secret=os.getenv('DASHBOARD_PUBLIC_URL', '').rstrip('/') + '/invitation#' + urlencode({'token': result['token']}), invitation=True)
        elif action == 'credential':
            result = await api.post(prefix + '/credentials', json={'name': form.get('name')})
            return page(request, 'workspace_secret.html', heading='Automation credential created', secret=result['token'])
        elif action == 'revoke':
            await api.request('DELETE', prefix + '/credentials/' + str(form.get('credential_id')))
        elif action == 'role':
            await api.patch(prefix + '/members/' + str(form.get('user_id')), json={'role': form.get('role')})
        elif action == 'remove':
            await api.request('DELETE', prefix + '/members/' + str(form.get('user_id')))
        elif action == 'settings':
            await api.patch(prefix + '/settings', json={'description': form.get('description', ''),
                'brand_voice': form.get('brand_voice', ''), 'monthly_budget_usd': form.get('monthly_budget_usd', 50)})
        elif action in ('products', 'icps'):
            import json
            try:
                rules = json.loads(str(form.get('qualification_rules') or '{}'))
            except ValueError:
                return RedirectResponse('/workspaces?' + urlencode({'message': 'Qualification rules must be valid JSON.'}), status_code=303)
            await api.post(prefix + '/catalog/' + action, json={'code': form.get('code'), 'name': form.get('name'),
                'description': form.get('description'), 'qualification_rules': rules})
        else:
            return HTMLResponse('Unknown action.', status_code=400)
    except MarketingAPIError as exc:
        return RedirectResponse('/workspaces?' + urlencode({'message': exc.message}), status_code=303)
    return RedirectResponse('/workspaces', status_code=303)


@router.post('/account/password')
async def password(request: Request, current_password: str = Form(...), new_password: str = Form(...), csrf_token: str = Form(...)):
    if not valid_csrf(request, csrf_token):
        return HTMLResponse('Invalid form token.', status_code=403)
    try:
        await request.app.state.api.post('/api/auth/password', json={'current_password': current_password, 'new_password': new_password})
    except MarketingAPIError as exc:
        return RedirectResponse('/workspaces?' + urlencode({'message': exc.message}), status_code=303)
    request.session.clear()
    return RedirectResponse('/login', status_code=303)
