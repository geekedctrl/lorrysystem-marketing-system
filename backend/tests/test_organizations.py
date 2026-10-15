"""Synthetic organization and native Settings authorization checks."""
import os
from unittest.mock import patch
from cryptography.fernet import Fernet
from sqlalchemy import select
from test_backend import BackendFixtures
from marketing_backend.db import Session
from marketing_backend.models import (Organization, OrganizationMembership, Workspace,
                                      Membership, User, LoginSession, ProviderConnection)
from marketing_backend.auth import hash_password


class OrganizationTests(BackendFixtures):
    def test_owner_creation_idempotency_and_workspace_isolation(self):
        org = self.client.post("/organizations", headers=self.headers,
                               json={"name": "Second company"})
        self.assertEqual(org.status_code, 201, org.text)
        oid = org.json()["id"]
        body = {"name": "New product", "description": "Synthetic description",
                "idempotency_key": "create-product-0001"}
        first = self.client.post(f"/organizations/{oid}/workspaces", headers=self.headers, json=body)
        self.assertEqual(first.status_code, 201, first.text)
        again = self.client.post(f"/organizations/{oid}/workspaces", headers=self.headers, json=body)
        self.assertEqual(again.status_code, 201, again.text)
        self.assertEqual(first.json()["id"], again.json()["id"])
        self.assertTrue(again.json()["replayed"])
        changed = self.client.post(f"/organizations/{oid}/workspaces", headers=self.headers,
                                   json={**body, "name": "Changed"})
        self.assertEqual(changed.status_code, 409)
        wid = first.json()["id"]
        with Session() as db:
            workspace = db.get(Workspace, wid)
            self.assertEqual(str(workspace.organization_id), oid)
            self.assertEqual(db.get(Membership, (workspace.id, self.uid)).role, "ADMIN")
        self.assertEqual(self.client.get(f"/workspaces/{wid}/profile", headers=self.headers).status_code, 200)
        viewer_headers = {"Authorization": "Bearer " + self.login("viewer@example.test")}
        self.assertEqual(self.client.get(f"/organizations/{oid}/workspaces", headers=viewer_headers).status_code, 404)
        self.assertEqual(self.client.get(f"/workspaces/{wid}/profile", headers=viewer_headers).status_code, 404)

    def test_workspace_admin_viewer_and_outsider_cannot_create_in_organization(self):
        with Session() as db:
            oid = db.get(Workspace, self.wid).organization_id
            outsider = User(email="workspace-only@example.test", password_hash=hash_password(self.password))
            db.add(outsider)
            db.flush()
            db.add(Membership(workspace_id=self.wid, user_id=outsider.id, role="ADMIN"))
            db.commit()
        body = {"name": "Denied", "idempotency_key": "denied-product-0001"}
        for email in ("workspace-only@example.test", "viewer@example.test"):
            token = self.login(email)
            response = self.client.post(f"/organizations/{oid}/workspaces",
                                        headers={"Authorization": "Bearer " + token}, json=body)
            self.assertIn(response.status_code, (403, 404))
        self.assertEqual(self.client.get(f"/organizations/{oid}/members", headers=self.headers).status_code, 200)

    def test_organization_admin_can_create_without_platform_admin_and_owner_guard(self):
        with Session() as db:
            oid = db.get(Workspace, self.wid).organization_id
            account = User(email="org-admin@example.test", password_hash=hash_password(self.password), platform_admin=False)
            db.add(account)
            db.flush()
            db.add(OrganizationMembership(organization_id=oid, user_id=account.id, role="ADMIN"))
            db.commit()
            account_id = account.id
        headers = {"Authorization": "Bearer " + self.login("org-admin@example.test")}
        created = self.client.post(f"/organizations/{oid}/workspaces", headers=headers,
                                   json={"name": "Admin product", "idempotency_key": "org-admin-create-0001"})
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(self.client.post("/workspaces", headers=headers,
                                          json={"name": "Platform attempt"}).status_code, 403)
        self.assertEqual(self.client.patch(f"/organizations/{oid}/members/{self.uid}", headers=headers,
                                           json={"role": "MEMBER"}).status_code, 403)
        self.assertEqual(self.client.patch(f"/organizations/{oid}/members/{self.uid}", headers=self.headers,
                                           json={"role": "MEMBER"}).status_code, 409)
        self.assertEqual(self.client.patch(f"/organizations/{oid}/members/{account_id}", headers=self.headers,
                                           json={"role": "OWNER"}).status_code, 200)
        self.assertEqual(self.client.patch(f"/organizations/{oid}/members/{self.uid}", headers=self.headers,
                                           json={"role": "ADMIN"}).status_code, 200)

    def test_workspace_status_and_connection_projection(self):
        with Session() as db:
            oid = db.get(Workspace, self.wid).organization_id
        connections = self.client.get(f"/workspaces/{self.wid}/connections", headers=self.headers)
        self.assertEqual(connections.status_code, 200, connections.text)
        self.assertNotIn("secret", connections.text.lower())
        with Session() as db:
            db.get(Workspace, self.wid).automation = {"product_description": "Synthetic product", "batch_size": 3}
            db.commit()
        preferences = self.client.put(f"/workspaces/{self.wid}/automation/preferences", headers=self.headers,
                                      json={"batch_size": 4})
        self.assertEqual(preferences.status_code, 200, preferences.text)
        self.assertEqual(preferences.json()["batch_size"], 4)
        self.assertEqual(self.client.patch(f"/organizations/{oid}/workspaces/{self.other}/status",
                                           headers=self.headers, json={"active": False}).status_code, 200)
        self.assertEqual(self.client.patch(f"/organizations/{oid}/workspaces/{self.other}/status",
                                           headers=self.headers, json={"active": True}).status_code, 200)
        viewer_headers = {"Authorization": "Bearer " + self.login("viewer@example.test")}
        self.assertEqual(self.client.put(f"/workspaces/{self.wid}/automation/preferences",
                                         headers=viewer_headers, json={"batch_size": 5}).status_code, 403)
        self.assertIn(self.client.patch(f"/organizations/{oid}/workspaces/{self.other}/status",
                                        headers=viewer_headers, json={"active": False}).status_code, (403, 404))
        foreign = self.client.post("/organizations", headers=self.headers, json={"name": "Other owner"}).json()
        self.assertEqual(self.client.patch(f"/organizations/{foreign['id']}/workspaces/{self.wid}/status",
                                           headers=self.headers, json={"active": False}).status_code, 404)

    def test_provider_draft_is_encrypted_unverified_and_admin_only(self):
        payload = {"secret": "synthetic-provider-secret", "base_url": "https://api.syntheticprovider.com/v1",
                   "model_name": "synthetic-model"}
        with patch.dict(os.environ, {"SENDER_CREDENTIAL_ENCRYPTION_KEY": Fernet.generate_key().decode(),
                                    "MODEL_API_KEY": ""}):
            saved = self.client.put(f"/workspaces/{self.wid}/provider-connections/MODEL",
                                    headers=self.headers, json=payload)
            self.assertEqual(saved.status_code, 200, saved.text)
            self.assertNotIn(payload["secret"], saved.text)
            self.assertEqual(saved.json()["status"], "unverified")
            with Session() as db:
                row = db.get(ProviderConnection, (self.wid, "MODEL"))
                self.assertNotIn(payload["secret"], row.secret_ciphertext)
                self.assertFalse(row.enabled)
                self.assertIsNone(row.verified_at)
            status = self.client.get(f"/workspaces/{self.wid}/connections", headers=self.headers)
            self.assertEqual(status.json()["model"], "unverified")
            self.assertNotIn(payload["secret"], status.text)
            viewer_headers = {"Authorization": "Bearer " + self.login("viewer@example.test")}
            denied = self.client.put(f"/workspaces/{self.wid}/provider-connections/MODEL",
                                     headers=viewer_headers, json=payload)
            self.assertEqual(denied.status_code, 403)
            invalid = self.client.put(f"/workspaces/{self.wid}/provider-connections/MODEL",
                                      headers=self.headers, json={**payload, "secret": "short"})
            self.assertEqual(invalid.status_code, 422)
            self.assertNotIn("short", invalid.text)

    def test_invitation_acceptance_duplicate_and_password_revocation(self):
        with Session() as db:
            oid = db.get(Workspace, self.wid).organization_id
        body = {"email": "viewer@example.test", "role": "REVIEWER"}
        invite = self.client.post(f"/workspaces/{self.other}/invitations", headers=self.headers, json=body)
        # The fixture admin has no membership in the second workspace.
        self.assertEqual(invite.status_code, 404)
        invite = self.client.post(f"/workspaces/{self.wid}/invitations", headers=self.headers,
                                  json={"email": "new@example.test", "role": "REVIEWER"})
        self.assertEqual(invite.status_code, 201, invite.text)
        duplicate = self.client.post(f"/workspaces/{self.wid}/invitations", headers=self.headers,
                                     json={"email": "new@example.test", "role": "REVIEWER"})
        self.assertEqual(duplicate.status_code, 409)
        with Session() as db:
            account = User(email="new@example.test", password_hash=hash_password(self.password))
            db.add(account)
            db.commit()
        token = self.login("new@example.test")
        headers = {"Authorization": "Bearer " + token}
        accepted = self.client.post("/invitations/accept", headers=headers,
                                    json={"token": invite.json()["token"]})
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(self.client.post("/invitations/accept", headers=headers,
                                         json={"token": invite.json()["token"]}).status_code, 200)
        with Session() as db:
            self.assertEqual(db.get(Membership, (self.wid, account.id)).role, "REVIEWER")
            self.assertEqual(db.get(OrganizationMembership, (oid, account.id)).role, "MEMBER")
        old = self.login("admin@example.test")
        changed = self.client.post("/auth/password", headers=self.headers,
                                   json={"current_password": self.password,
                                         "new_password": "a-new-synthetic-password-123"})
        self.assertEqual(changed.status_code, 204, changed.text)
        self.assertEqual(self.client.get("/auth/me", headers={"Authorization": "Bearer " + old}).status_code, 401)
