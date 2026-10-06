import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import case, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from app.auth import authenticated_user, password_hash, token_hash, verify_password
from app.db.session import ControlSession, SessionLocal, get_db
from app.models import ICPProfile, Product
from app.models.workspaces import (AccessAudit, Invitation, LoginAttempt, LoginSession,
                                  Membership, ServiceCredential, User, Workspace)

router = APIRouter(tags=['Workspaces and accounts'])
Role = Literal['ADMIN', 'OPERATOR', 'REVIEWER', 'VIEWER']


def control_db():
    with ControlSession() as db:
        yield db


def normalize_email(value):
    value = value.strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value) or len(value) > 254:
        raise ValueError('Enter a valid email address')
    return value


class Login(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)
    _email = field_validator('email')(normalize_email)


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$', max_length=80)


class Invite(BaseModel):
    email: str = Field(max_length=254)
    role: Role = 'OPERATOR'
    _email = field_validator('email')(normalize_email)


class AcceptInvite(BaseModel):
    token: str = Field(min_length=20, max_length=100)
    password: str = Field(min_length=12, max_length=256)


class RoleChange(BaseModel):
    role: Role


class CredentialCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ProfileSettings(BaseModel):
    description: str = Field(default='', max_length=5000)
    brand_voice: str = Field(default='', max_length=5000)
    monthly_budget_usd: float = Field(default=50, ge=0, le=1000000)


class CatalogItem(BaseModel):
    code: str = Field(pattern=r'^[A-Z0-9_]+$', max_length=80)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=5000)
    qualification_rules: dict = Field(default_factory=dict)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


def audit(db, user, action, workspace_id=None, **detail):
    db.add(AccessAudit(actor=user.email, action=action, workspace_id=workspace_id, detail=detail))


def admin_for(db, request, workspace_id):
    user = authenticated_user(db, request)
    workspace = db.get(Workspace, workspace_id)
    membership = db.get(Membership, (workspace_id, user.id))
    if workspace is None or not workspace.active or membership is None or membership.role != 'ADMIN':
        raise HTTPException(403, 'Workspace administrator access required')
    return user


def workspace_read(workspace, role):
    return {'id': str(workspace.id), 'name': workspace.name, 'slug': workspace.slug, 'role': role, 'settings': workspace.settings}


@router.post('/api/auth/login')
def login(data: Login, request: Request, db=Depends(control_db)):
    now = datetime.now(timezone.utc)
    # Count before password verification; atomic UPSERT persists limits across workers.
    for key, maximum in ((f'email:{data.email}', 8), (f'ip:{request.client.host if request.client else "unknown"}', 100)):
        statement = insert(LoginAttempt).values(key=token_hash(key), failures=1, window_started_at=now)
        expired = LoginAttempt.window_started_at < now - timedelta(minutes=15)
        statement = statement.on_conflict_do_update(index_elements=['key'], set_={
            'failures': case((expired, 1), else_=LoginAttempt.failures + 1),
            'window_started_at': case((expired, now), else_=LoginAttempt.window_started_at),
        }).returning(LoginAttempt.failures)
        attempts = db.scalar(statement)
        db.commit()
        if attempts > maximum:
            raise HTTPException(429, 'Too many login attempts. Try again in 15 minutes.')
    user = db.scalar(select(User).where(User.email == data.email))
    dummy = f'pbkdf2_sha256$600000${"0" * 32}${"0" * 64}'
    valid = verify_password(data.password, user.password_hash if user else dummy)
    if user is None or not user.active or not valid:
        raise HTTPException(401, 'Email or password is incorrect')
    db.execute(delete(LoginAttempt).where(LoginAttempt.key == token_hash(f'email:{data.email}')))
    db.execute(delete(LoginSession).where(LoginSession.expires_at < now))
    token = secrets.token_urlsafe(48)
    db.add(LoginSession(token_hash=token_hash(token), user_id=user.id, expires_at=now + timedelta(hours=12)))
    audit(db, user, 'login')
    db.commit()
    return {'token': token, 'expires_in': 43200}


@router.get('/api/auth/me')
def me(request: Request, db=Depends(control_db)):
    user = authenticated_user(db, request)
    rows = db.execute(select(Workspace, Membership.role).join(Membership).where(
        Membership.user_id == user.id, Workspace.active.is_(True))).all()
    return {'id': str(user.id), 'email': user.email, 'platform_admin': user.platform_admin,
            'workspaces': [workspace_read(w, role) for w, role in rows]}


@router.post('/api/auth/logout')
def logout(request: Request, db=Depends(control_db)):
    user = authenticated_user(db, request)
    db.execute(delete(LoginSession).where(LoginSession.token_hash == token_hash(request.headers['Authorization'][7:])))
    audit(db, user, 'logout')
    db.commit()
    return {'status': 'signed_out'}


@router.post('/api/auth/password')
def change_password(data: PasswordChange, request: Request, db=Depends(control_db)):
    user = authenticated_user(db, request)
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(401, 'Current password is incorrect')
    user.password_hash = password_hash(data.new_password)
    db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
    audit(db, user, 'password_changed')
    db.commit()
    return {'status': 'password_changed_sign_in_again'}


@router.post('/api/auth/invitations/accept')
def accept_invitation(data: AcceptInvite, db=Depends(control_db)):
    now = datetime.now(timezone.utc)
    invitation = db.scalar(select(Invitation).where(Invitation.token_hash == token_hash(data.token)).with_for_update())
    if invitation is None or invitation.used_at or invitation.expires_at <= now:
        raise HTTPException(400, 'Invitation is invalid or expired')
    # A known invitation cannot be used for unlimited password guesses against
    # an existing account. Use a separate transaction to preserve the row lock.
    with ControlSession() as limiter:
        key = token_hash('invitation:' + data.token)
        expired = LoginAttempt.window_started_at < now - timedelta(minutes=15)
        statement = insert(LoginAttempt).values(key=key, failures=1, window_started_at=now)
        attempts = limiter.scalar(statement.on_conflict_do_update(index_elements=['key'], set_={
            'failures': case((expired, 1), else_=LoginAttempt.failures + 1),
            'window_started_at': case((expired, now), else_=LoginAttempt.window_started_at),
        }).returning(LoginAttempt.failures))
        limiter.commit()
        if attempts > 8:
            raise HTTPException(429, 'Too many invitation attempts. Try again in 15 minutes.')
    workspace = db.get(Workspace, invitation.workspace_id)
    if workspace is None or not workspace.active:
        raise HTTPException(400, 'Workspace is unavailable')
    user = db.scalar(select(User).where(User.email == invitation.email))
    if user:
        if not user.active or not verify_password(data.password, user.password_hash):
            raise HTTPException(401, 'Enter your existing account password')
    else:
        user = User(email=invitation.email, password_hash=password_hash(data.password))
        db.add(user)
        db.flush()
    if db.get(Membership, (invitation.workspace_id, user.id)) is None:
        db.add(Membership(workspace_id=invitation.workspace_id, user_id=user.id, role=invitation.role))
    invitation.used_at = now
    audit(db, user, 'invitation_accepted', invitation.workspace_id)
    db.commit()
    return {'status': 'accepted'}


@router.get('/api/workspaces')
def workspaces(request: Request, db=Depends(control_db)):
    return me(request, db)['workspaces']


@router.post('/api/workspaces', status_code=201)
def create_workspace(data: WorkspaceCreate, request: Request, db=Depends(control_db)):
    user = authenticated_user(db, request)
    if not user.platform_admin:
        raise HTTPException(403, 'Platform administrator access required')
    workspace = Workspace(name=data.name.strip(), slug=data.slug)
    db.add(workspace)
    try:
        db.flush()
        db.add(Membership(workspace_id=workspace.id, user_id=user.id, role='ADMIN'))
        audit(db, user, 'workspace_created', workspace.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Workspace slug already exists')
    return workspace_read(workspace, 'ADMIN')


@router.get('/api/workspaces/{workspace_id}/members')
def members(workspace_id: UUID, request: Request, db=Depends(control_db)):
    admin_for(db, request, workspace_id)
    return [{'user_id': str(u.id), 'email': u.email, 'role': m.role}
            for u, m in db.execute(select(User, Membership).join(Membership).where(Membership.workspace_id == workspace_id))]


@router.post('/api/workspaces/{workspace_id}/invitations', status_code=201)
def invite(workspace_id: UUID, data: Invite, request: Request, db=Depends(control_db)):
    user = admin_for(db, request, workspace_id)
    token = secrets.token_urlsafe(32)
    db.execute(delete(Invitation).where(Invitation.workspace_id == workspace_id, Invitation.email == data.email, Invitation.used_at.is_(None)))
    db.add(Invitation(token_hash=token_hash(token), workspace_id=workspace_id, email=data.email,
                      role=data.role, expires_at=datetime.now(timezone.utc) + timedelta(days=2)))
    audit(db, user, 'invitation_created', workspace_id, email=data.email, role=data.role)
    db.commit()
    return {'token': token, 'expires_in': 172800}


def membership_to_change(db, workspace_id, user_id, protect_last_admin=True):
    db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    member = db.get(Membership, (workspace_id, user_id))
    if member is None:
        raise HTTPException(404, 'Member not found')
    if member.role == 'ADMIN' and protect_last_admin:
        count = db.scalar(select(func.count()).select_from(Membership).where(
            Membership.workspace_id == workspace_id, Membership.role == 'ADMIN'))
        if count <= 1:
            raise HTTPException(409, 'Keep at least one workspace administrator')
    return member


@router.patch('/api/workspaces/{workspace_id}/members/{user_id}')
def change_role(workspace_id: UUID, user_id: UUID, data: RoleChange, request: Request, db=Depends(control_db)):
    user = admin_for(db, request, workspace_id)
    member = membership_to_change(db, workspace_id, user_id, protect_last_admin=data.role != 'ADMIN')
    member.role = data.role
    audit(db, user, 'member_role_changed', workspace_id, user_id=str(user_id), role=data.role)
    db.commit()
    return {'status': 'updated'}


@router.delete('/api/workspaces/{workspace_id}/members/{user_id}')
def remove_member(workspace_id: UUID, user_id: UUID, request: Request, db=Depends(control_db)):
    user = admin_for(db, request, workspace_id)
    member = membership_to_change(db, workspace_id, user_id)
    target = db.get(User, user_id)
    db.execute(delete(Invitation).where(Invitation.workspace_id == workspace_id, Invitation.email == target.email))
    db.delete(member)
    audit(db, user, 'member_removed', workspace_id, user_id=str(user_id))
    db.commit()
    return {'status': 'removed'}


@router.get('/api/workspaces/{workspace_id}/credentials')
def credentials(workspace_id: UUID, request: Request, db=Depends(control_db)):
    admin_for(db, request, workspace_id)
    return [{'id': str(c.id), 'name': c.name, 'active': c.active}
            for c in db.scalars(select(ServiceCredential).where(ServiceCredential.workspace_id == workspace_id))]


@router.post('/api/workspaces/{workspace_id}/credentials', status_code=201)
def create_credential(workspace_id: UUID, data: CredentialCreate, request: Request, db=Depends(control_db)):
    user = admin_for(db, request, workspace_id)
    token = 'mw_' + secrets.token_urlsafe(48)
    credential = ServiceCredential(workspace_id=workspace_id, name=data.name, token_hash=token_hash(token))
    db.add(credential)
    audit(db, user, 'credential_created', workspace_id, name=data.name)
    db.commit()
    return {'id': str(credential.id), 'token': token}


@router.delete('/api/workspaces/{workspace_id}/credentials/{credential_id}')
def revoke_credential(workspace_id: UUID, credential_id: UUID, request: Request, db=Depends(control_db)):
    user = admin_for(db, request, workspace_id)
    credential = db.get(ServiceCredential, credential_id)
    if credential is None or credential.workspace_id != workspace_id:
        raise HTTPException(404, 'Credential not found')
    credential.active = False
    audit(db, user, 'credential_revoked', workspace_id, credential_id=str(credential_id))
    db.commit()
    return {'status': 'revoked'}


@router.patch('/api/workspaces/{workspace_id}/settings')
def settings(workspace_id: UUID, data: ProfileSettings, request: Request, db=Depends(control_db)):
    user = admin_for(db, request, workspace_id)
    workspace = db.get(Workspace, workspace_id)
    workspace.settings = data.model_dump()
    audit(db, user, 'workspace_settings_updated', workspace_id)
    db.commit()
    return workspace_read(workspace, 'ADMIN')


@router.get('/api/workspaces/{workspace_id}/audit')
def audit_history(workspace_id: UUID, request: Request, db=Depends(control_db)):
    admin_for(db, request, workspace_id)
    return [{'actor': a.actor, 'action': a.action, 'detail': a.detail, 'created_at': a.created_at}
            for a in db.scalars(select(AccessAudit).where(AccessAudit.workspace_id == workspace_id)
                                .order_by(AccessAudit.created_at.desc()).limit(100))]


@router.get('/api/icp-profiles')
def icp_profiles(db=Depends(get_db)):
    return [{'id': str(i.id), 'code': i.code, 'name': i.name, 'description': i.description,
             'qualification_rules': i.qualification_rules}
            for i in db.scalars(select(ICPProfile).where(ICPProfile.active.is_(True)).order_by(ICPProfile.name))]


@router.get('/api/workspace-context')
def workspace_context(db=Depends(get_db)):
    from app.workspace_context import current_principal
    principal = current_principal.get()
    with ControlSession() as control:
        workspace = control.get(Workspace, principal.workspace_id)
        return {'workspace': workspace_read(workspace, principal.role), 'icps': icp_profiles(db),
                'automation': {
                    'contract_version': 1,
                    'credential_kind': ('legacy' if principal.actor == 'legacy-lorrysystem-worker'
                                        else 'workspace' if principal.role == 'SERVICE' else 'user'),
                    'registry_namespace': f'workspace:{principal.workspace_id}:discovery',
                    'human_candidate_review_required': True,
                    'human_marketing_approval_required': True,
                },
                'products': [{'id': str(p.id), 'code': p.code, 'name': p.name, 'description': p.description}
                             for p in db.scalars(select(Product).where(Product.active.is_(True)))]}


@router.post('/api/workspaces/{workspace_id}/catalog/{kind}', status_code=201)
def catalog(workspace_id: UUID, kind: Literal['products', 'icps'], data: CatalogItem, request: Request, db=Depends(control_db)):
    user = admin_for(db, request, workspace_id)
    with SessionLocal(info={'workspace_id': workspace_id}) as scoped:
        model = Product if kind == 'products' else ICPProfile
        values = {'code': data.code, 'name': data.name, 'description': data.description}
        if kind == 'icps':
            values['qualification_rules'] = data.qualification_rules
        item = model(**values)
        scoped.add(item)
        try:
            scoped.commit()
            item_id = str(item.id)
        except IntegrityError:
            scoped.rollback()
            raise HTTPException(409, 'Code already exists in this workspace')
    audit(db, user, 'catalog_item_created', workspace_id, kind=kind, code=data.code)
    db.commit()
    return {'id': item_id, **values}
