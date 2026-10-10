import hashlib
import os
import secrets
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, Request
from sqlalchemy import select

from app.db.session import ControlSession
from app.models.workspaces import LoginSession, Membership, ServiceCredential, User, Workspace
from app.workspace_context import LORRYSYSTEM_WORKSPACE_ID, Principal


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def password_hash(password: str) -> str:
    if not 12 <= len(password) <= 256:
        raise HTTPException(422, 'Password must contain 12 to 256 characters')
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600_000).hex()
    return f'pbkdf2_sha256$600000${salt}${digest}'


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, rounds, salt, expected = encoded.split('$')
        if scheme != 'pbkdf2_sha256' or len(password) > 256:
            return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), int(rounds)).hex()
        return secrets.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def authenticated_user(db, request: Request) -> User:
    authorization = request.headers.get('Authorization', '')
    if not authorization.startswith('Bearer ') or len(authorization) > 512:
        raise HTTPException(401, 'Sign in required')
    session = db.get(LoginSession, token_hash(authorization[7:]))
    if session is None or session.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(401, 'Session expired or invalid')
    user = db.get(User, session.user_id)
    if user is None or not user.active:
        raise HTTPException(401, 'Account is unavailable')
    return user


def selected_workspace(request: Request) -> UUID:
    try:
        return UUID(request.headers.get('X-Workspace-ID', ''))
    except ValueError:
        raise HTTPException(400, 'Select a workspace')


def resolve_principal(request: Request) -> Principal:
    if request.headers.get('X-Automation-Lease'):
        from app.services.automation_access import lease_principal
        return lease_principal(request)
    with ControlSession() as db:
        if request.headers.get('Authorization'):
            user = authenticated_user(db, request)
            workspace_id = selected_workspace(request)
            membership = db.get(Membership, (workspace_id, user.id))
            if membership is None:
                raise HTTPException(403, 'Workspace access denied')
            principal = Principal(workspace_id, user.email, membership.role, user.id)
        else:
            key = request.headers.get('X-API-Key', '')
            if not key or len(key) > 512 or not key.isascii():
                raise HTTPException(401, 'Invalid or missing credentials')
            legacy_key = os.getenv('MARKETING_API_KEY', '')
            if (os.getenv('ENABLE_LEGACY_API_KEY', 'true').lower() == 'true'
                    and legacy_key and secrets.compare_digest(key, legacy_key)):
                principal = Principal(LORRYSYSTEM_WORKSPACE_ID, 'legacy-lorrysystem-worker', 'SERVICE')
            else:
                credential = db.scalar(select(ServiceCredential).where(
                    ServiceCredential.token_hash == token_hash(key), ServiceCredential.active.is_(True)))
                if credential is None:
                    raise HTTPException(401, 'Invalid or missing credentials')
                principal = Principal(credential.workspace_id, f'service:{credential.name}', 'SERVICE')
            requested = request.headers.get('X-Workspace-ID')
            if requested and requested != str(principal.workspace_id):
                raise HTTPException(403, 'Credential is restricted to its workspace')
        workspace = db.get(Workspace, principal.workspace_id)
        if workspace is None or not workspace.active:
            raise HTTPException(403, 'Workspace is unavailable')
        return principal


def check_business_permission(principal: Principal, request: Request):
    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return
    decision = request.url.path.startswith('/api/approvals/') and request.url.path.rsplit('/', 1)[-1] in (
        'approve', 'reject', 'request-changes')
    candidate_decision = request.url.path.startswith('/api/candidates/') and request.url.path.rsplit('/', 1)[-1] in ('accept', 'reject')
    campaign_review = request.url.path.startswith('/api/campaign-proposals/') and request.url.path.endswith('/review')
    if campaign_review:
        if not principal.user_id or principal.role not in {'ADMIN', 'REVIEWER'}:
            raise HTTPException(403, 'Strategy review requires a signed-in reviewer')
        return
    if '/campaign-proposals' in request.url.path:
        if not principal.user_id or principal.role not in {'ADMIN', 'OPERATOR', 'REVIEWER'}:
            raise HTTPException(403, 'Campaign proposals require a signed-in workspace editor')
        return
    allowed = {'ADMIN', 'REVIEWER'} if decision else {'ADMIN', 'OPERATOR'} if candidate_decision else {'ADMIN', 'OPERATOR', 'SERVICE'}
    if principal.role not in allowed:
        raise HTTPException(403, 'Your workspace role does not allow this action')
