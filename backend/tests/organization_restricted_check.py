"""Exercise native organization endpoints with the restricted API database role."""
import os
import uuid
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from marketing_backend.auth import hash_password
from marketing_backend.api import app


def main():
    api_url = os.environ["DATABASE_URL"]
    owner_url = os.environ["ADMIN_DATABASE_URL"]
    if not api_url.endswith("/marketing_rebuild_test") or not owner_url.endswith("/marketing_rebuild_test"):
        raise RuntimeError("Use only the synthetic marketing_rebuild_test database")
    engine = create_engine(owner_url)
    uid, oid = uuid.uuid4(), uuid.uuid4()
    email = f"restricted-{uid.hex[:12]}@example.test"
    password = "synthetic-password-123"
    os.environ["SENDER_CREDENTIAL_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    with engine.begin() as db:
        db.execute(text("INSERT INTO users(id,email,password_hash,active,platform_admin) VALUES (:id,:email,:hash,true,false)"),
                   {"id": uid, "email": email, "hash": hash_password(password)})
        db.execute(text("INSERT INTO organizations(id,name) VALUES (:id,'Restricted fixture')"), {"id": oid})
        db.execute(text("INSERT INTO organization_memberships(organization_id,user_id,role) VALUES (:oid,:uid,'OWNER')"),
                   {"oid": oid, "uid": uid})
    try:
        client = TestClient(app)
        login = client.post("/auth/login", json={"email": email, "password": password})
        assert login.status_code == 200, login.text
        headers = {"Authorization": "Bearer " + login.json()["token"]}
        assert client.get("/organizations", headers=headers).status_code == 200
        created = client.post(f"/organizations/{oid}/workspaces", headers=headers,
                              json={"name": "Restricted product", "idempotency_key": "restricted-create-0001"})
        assert created.status_code == 201, created.text
        wid = created.json()["id"]
        assert client.get(f"/workspaces/{wid}/profile", headers=headers).status_code == 200
        renamed = client.put(f"/workspaces/{wid}/profile", headers=headers,
                             json={"name": "Renamed product", "description": "Synthetic"})
        assert renamed.status_code == 200, renamed.text
        assert client.get(f"/workspaces/{wid}/connections", headers=headers).status_code == 200
        draft = client.put(f"/workspaces/{wid}/provider-connections/MODEL", headers=headers,
                           json={"secret": "synthetic-provider-key", "base_url": "https://api.syntheticprovider.com/v1",
                                 "model_name": "synthetic-model"})
        assert draft.status_code == 200, draft.text
        assert "synthetic-provider-key" not in draft.text
        status = client.patch(f"/organizations/{oid}/workspaces/{wid}/status", headers=headers,
                              json={"active": False})
        assert status.status_code == 200, status.text
        assert client.patch(f"/organizations/{oid}/workspaces/{wid}/status", headers=headers,
                            json={"active": True}).status_code == 200
        second = client.post("/auth/login", json={"email": email, "password": password})
        assert second.status_code == 200, second.text
        changed = client.post("/auth/password", headers=headers,
                              json={"current_password": password, "new_password": "synthetic-new-password-456"})
        assert changed.status_code == 204, changed.text
        old_headers = {"Authorization": "Bearer " + second.json()["token"]}
        assert client.get("/auth/me", headers=old_headers).status_code == 401
        print("Restricted API organization, workspace, encrypted provider draft, status and password passed")
    finally:
        with engine.begin() as db:
            db.execute(text("DELETE FROM workspace_creations WHERE organization_id=:oid"), {"oid": oid})
            db.execute(text("DELETE FROM provider_connections WHERE workspace_id IN (SELECT id FROM workspaces WHERE organization_id=:oid)"), {"oid": oid})
            db.execute(text("DELETE FROM memberships WHERE workspace_id IN (SELECT id FROM workspaces WHERE organization_id=:oid)"), {"oid": oid})
            db.execute(text("DELETE FROM workspaces WHERE organization_id=:oid"), {"oid": oid})
            db.execute(text("DELETE FROM organization_memberships WHERE organization_id=:oid"), {"oid": oid})
            db.execute(text("DELETE FROM organizations WHERE id=:oid"), {"oid": oid})
            db.execute(text("DELETE FROM login_sessions WHERE user_id=:uid"), {"uid": uid})
            db.execute(text("DELETE FROM users WHERE id=:uid"), {"uid": uid})


if __name__ == "__main__":
    main()
