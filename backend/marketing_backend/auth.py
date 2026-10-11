import hashlib, secrets, hmac
from datetime import timedelta
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select, text
from .db import session
from .models import User, LoginSession, Membership, Workspace, now


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password):
    salt = secrets.token_hex(16)
    value = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 600000
    ).hex()
    return f"pbkdf2_sha256$600000${salt}${value}"


def verify_password(password, encoded):
    try:
        _, iterations, salt, expected = encoded.split("$")
        return hmac.compare_digest(
            hashlib.pbkdf2_hmac(
                "sha256", password.encode(), salt.encode(), int(iterations)
            ).hex(),
            expected,
        )
    except (ValueError, TypeError):
        return False


DUMMY = hash_password(secrets.token_urlsafe(24))


def user(db=Depends(session), authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sign in required")
    login = db.get(LoginSession, digest(authorization[7:]))
    actor = db.get(User, login.user_id) if login and login.expires_at > now() else None
    if not actor or not actor.active:
        raise HTTPException(401, "Session invalid or expired")
    return actor


def scope(workspace_id, actor, db, roles=None):
    workspace = db.get(Workspace, workspace_id)
    membership = db.get(Membership, (workspace_id, actor.id))
    if not workspace or not workspace.active or not membership:
        raise HTTPException(404, "Workspace not found")
    if roles and membership.role not in roles:
        raise HTTPException(403, "Workspace permission required")
    db.execute(
        text("SELECT set_config('app.workspace_id', :wid, true)"),
        {"wid": str(workspace_id)},
    )
    return membership
