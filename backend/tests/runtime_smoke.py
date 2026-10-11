"""Exercise the separately running API/worker with their restricted database roles."""

import os, secrets, time
from uuid import UUID
from sqlalchemy import delete
import httpx
from marketing_backend.db import Session, engine
from marketing_backend.models import (
    User,
    Workspace,
    Membership,
    Job,
    Lead,
    Catalog,
    LoginSession,
)
from marketing_backend.auth import hash_password

if os.getenv("APP_ENV") != "local-smoke" or engine.url.database != "marketing_rebuild":
    raise RuntimeError(
        "Only the isolated rebuild development database may run this smoke test"
    )
password = secrets.token_urlsafe(24)
email = "smoke-" + secrets.token_hex(6) + "@example.test"
with Session() as db:
    actor = User(email=email, password_hash=hash_password(password))
    workspace = Workspace(name="REBUILD SMOKE FIXTURE")
    db.add_all([actor, workspace])
    db.flush()
    uid, wid = actor.id, workspace.id
    db.add(Membership(user_id=uid, workspace_id=wid, role="ADMIN"))
    db.commit()
try:
    with httpx.Client(base_url="http://backend-api:8000", timeout=10) as client:
        response = client.post(
            "/auth/login", json={"email": email, "password": password}
        )
        response.raise_for_status()
        client.headers["Authorization"] = "Bearer " + response.json()["token"]
        for kind in ("PRODUCT", "ICP"):
            r = client.put(
                f"/workspaces/{wid}/catalog",
                json={
                    "kind": kind,
                    "code": kind,
                    "name": "Fixture " + kind,
                    "description": "Explicit synthetic smoke-test catalog context",
                },
            )
            r.raise_for_status()
        r = client.post(
            f"/workspaces/{wid}/leads",
            json={"company_name": "SMOKE FIXTURE", "website": "https://example.com/"},
        )
        r.raise_for_status()
        lid = r.json()["id"]
        r = client.post(
            f"/workspaces/{wid}/leads/{lid}/research",
            json={"idempotency_key": "smoke-fixture-only"},
        )
        r.raise_for_status()
        jid = r.json()["id"]
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            r = client.get(f"/workspaces/{wid}/jobs/{jid}")
            r.raise_for_status()
            job = r.json()
            if job["status"] == "FAILED":
                break
            time.sleep(0.25)
        assert (
            job["status"] == "FAILED"
            and job["failure_code"] == "PROVIDER_NOT_CONFIGURED"
        ), job["status"]
        print(
            "PASS running restricted-role API login/catalog/lead/queue and Python worker; no provider calls"
        )
finally:
    with Session() as db:
        for model in (Job, Lead, Catalog):
            db.execute(delete(model).where(model.workspace_id == wid))
        db.execute(delete(Membership).where(Membership.workspace_id == wid))
        db.execute(delete(LoginSession).where(LoginSession.user_id == uid))
        db.execute(delete(Workspace).where(Workspace.id == wid))
        db.execute(delete(User).where(User.id == uid))
        db.commit()
