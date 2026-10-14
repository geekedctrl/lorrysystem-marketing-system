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
    Approval,
    ProviderUsage,
    DiscoveryMemory,
    PreparationRun,
    ExecutorOwnership,
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
        # Coexistence safety: native work must remain unclaimed while the
        # default ownership rows are N8N/ACTIVE. If ownership is already
        # delegated in a synthetic environment, provider absence is the
        # expected terminal result instead.
        assert (
            job["status"] == "PENDING"
            or (job["status"] == "FAILED" and job["failure_code"] == "PROVIDER_NOT_CONFIGURED")
        ), job["status"]
        print(
            "PASS running restricted-role API login/catalog/lead/queue and Python worker; no provider calls"
        )
        operations = client.get(f"/workspaces/{wid}/operations")
        operations.raise_for_status()
        assert all(row["owner"] == "N8N" and row["state"] == "ACTIVE" for row in operations.json()["ownership"])
        blocked = client.post(f"/workspaces/{wid}/leads/{lid}/prepare", json={"idempotency_key": "smoke-native-preparation"})
        assert blocked.status_code == 409, blocked.text
        print("PASS native claims remain blocked while ownership is N8N; no provider calls")
        if os.getenv("RUN_NATIVE_ACTIVE_SMOKE") != "true":
            raise SystemExit(0)
        r = client.post(f"/workspaces/{wid}/automation/activate", json={"idempotency_key": "smoke-native-activation", "product_description": "Explicit synthetic smoke test product description"})
        r.raise_for_status()
        setup_id = r.json()["job_id"]
        r = client.post(f"/workspaces/{wid}/leads/{lid}/prepare", json={"idempotency_key": "smoke-native-preparation"})
        r.raise_for_status()
        run_id = r.json()["run_id"]
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            setup = client.get(f"/workspaces/{wid}/jobs/{setup_id}")
            run = client.get(f"/workspaces/{wid}/preparation/{run_id}")
            setup.raise_for_status()
            run.raise_for_status()
            if setup.json()["status"] == "FAILED" and run.json()["status"] == "FAILED":
                break
            time.sleep(0.25)
        assert setup.json()["failure_code"] == "PROVIDER_NOT_CONFIGURED"
        assert run.json()["stop_reason"] == "PROVIDER_NOT_CONFIGURED"
        operations = client.get(f"/workspaces/{wid}/operations")
        operations.raise_for_status()
        assert len(operations.json()["current_preparation"]) == 1
        assert operations.json()["recent_provider_usage"] == []
        print(
            "PASS native activation/preparation/operations with actual API and worker roles; missing keys make zero provider calls"
        )
finally:
    with Session() as db:
        for model in (
            Approval,
            ProviderUsage,
            Job,
            DiscoveryMemory,
            PreparationRun,
            Lead,
            Catalog,
        ):
            db.execute(delete(model).where(model.workspace_id == wid))
        db.execute(delete(Membership).where(Membership.workspace_id == wid))
        db.execute(delete(LoginSession).where(LoginSession.user_id == uid))
        db.execute(delete(ExecutorOwnership).where(ExecutorOwnership.workspace_id == wid))
        db.execute(delete(Workspace).where(Workspace.id == wid))
        db.execute(delete(User).where(User.id == uid))
        db.commit()
