"""Real PostgreSQL/RLS + test SMTP transport. Never contacts an SMTP server."""

import os, secrets, sys
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import patch
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import select

sys.path.insert(0, "/app")
from app.auth import password_hash
from app.db.session import ControlSession, SessionLocal
from app.models.workspaces import Workspace, User, Membership
from app.models.catalog import ICPProfile, Product
from app.models.companies import Company, Contact
from app.models.leads import Lead, ProductMatch
from app.models.marketing import MarketingAction
from app.models.sending import SenderAccount, DeliveryAttempt, EmailSuppression
from app.workspace_context import Principal, current_principal
from app.routers.sending import create_sender, SenderWrite, sender_read, verify_sender
from app.services.smtp_delivery import (
    send_approved,
    HandoffError,
    decrypt_password,
    smtp_handoff,
)
from app.services.marketing_action_service import create_action
from app.services.approval_service import submit_action_for_approval, approve
from app.schemas.marketing_action import MarketingActionCreate
from app.schemas.approval import ApprovalDecision

if os.getenv("APP_ENV") not in ("ci", "workspace-test"):
    raise SystemExit("Disposable environments only")
os.environ["SMTP_CREDENTIAL_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
suffix = secrets.token_hex(4)
with ControlSession() as db:
    workspace = Workspace(
        name="SMTP test " + suffix, slug="smtp-test-" + suffix, settings={}
    )
    foreign = Workspace(
        name="Other SMTP " + suffix, slug="smtp-other-" + suffix, settings={}
    )
    user = User(
        email=f"smtp-{suffix}@example.test",
        password_hash=password_hash(secrets.token_urlsafe(24)),
    )
    db.add_all([workspace, foreign, user])
    db.flush()
    db.add(Membership(workspace_id=workspace.id, user_id=user.id, role="ADMIN"))
    icp = ICPProfile(
        workspace_id=workspace.id,
        code="SMTP_FIXTURE",
        name="SMTP test companies",
        active=True,
        qualification_rules={},
    )
    company = Company(
        workspace_id=workspace.id,
        name="SMTP fixture company",
        domain=f"smtp-{suffix}.com",
        status="ACTIVE",
    )
    db.add_all([icp, company])
    db.flush()
    contact = Contact(
        workspace_id=workspace.id,
        company_id=company.id,
        full_name="Test Business Contact",
        email="recipient@example.test",
        status="ACTIVE",
        source_url="https://example.com/",
    )
    db.add(contact)
    db.flush()
    lead = Lead(
        workspace_id=workspace.id,
        company_id=company.id,
        primary_contact_id=contact.id,
        icp_profile_id=icp.id,
        status="READY_FOR_OUTREACH",
        current_score=80,
    )
    product = Product(
        workspace_id=workspace.id, code="SMTP_FIXTURE", name="Test offering"
    )
    db.add_all([lead, product])
    db.flush()
    db.add(
        ProductMatch(
            workspace_id=workspace.id,
            lead_id=lead.id,
            product_id=product.id,
            fit_score=80,
            rationale="Test fixture",
        )
    )
    wid, user_id, lead_id, contact_id, actor = (
        workspace.id,
        user.id,
        lead.id,
        contact.id,
        user.email,
    )
    foreign_id = foreign.id
    db.commit()
principal = Principal(wid, actor, "ADMIN", user_id)
token = current_principal.set(principal)
calls = []


def capture(sender, password, message, recipient):
    assert password == "test-only-password" and recipient == "recipient@example.test"
    assert (
        b"\r\n" in message.as_bytes()
        and b"test-only-password" not in message.as_bytes()
    )
    calls.append(str(message["Message-ID"]))


def expect(code, callback):
    try:
        callback()
    except HTTPException as error:
        assert error.status_code == code, (error.status_code, error.detail)
    else:
        raise AssertionError("Expected rejection")


try:
    with SessionLocal(info={"workspace_id": wid, "principal": principal}) as db:
        config = SenderWrite(
            name="Test sender",
            from_email="sender@example.test",
            from_name="Product team",
            host="smtp.example.com",
            username="test-user",
            password="test-only-password",
            enabled=True,
        )
        sender_id = create_sender(config, db)["id"]
        sender = db.get(SenderAccount, sender_id)
        assert (
            "test-only-password" not in sender.password_ciphertext
            and "password" not in sender_read(sender)
        )
        with patch("app.routers.sending.smtp_handoff", lambda s, p: None):
            assert verify_sender(sender.id, db)["verified"]
        assert calls == [], "Connection verification does not send"

        def action(approved=True):
            created = create_action(
                db,
                lead_id=lead_id,
                data=MarketingActionCreate(
                    contact_id=contact_id,
                    channel="EMAIL",
                    action_type="EMAIL",
                    subject="A question about your workflow",
                    content="Hello, would a short conversation about your documented business workflow be useful?",
                    created_by=actor,
                ),
            )
            # Service returns a read model/dict, not necessarily the ORM row.
            aid = created["id"] if isinstance(created, dict) else created.id
            row = db.get(MarketingAction, aid)
            review = submit_action_for_approval(db, action_id=row.id)
            if approved:
                approve(
                    db,
                    approval_id=review["id"],
                    data=ApprovalDecision(decided_by=actor),
                )
            return row

        pending = action(False)
        expect(409, lambda: send_approved(db, pending.id, sender.id, uuid4(), capture))
        db.rollback()
        approved = action()
        assert calls == [], "Approval does not send"
        contact = db.get(Contact, contact_id)
        contact.email = "changed@example.test"
        db.commit()
        expect(409, lambda: send_approved(db, approved.id, sender.id, uuid4(), capture))
        db.rollback()
        contact.email = "recipient@example.test"
        db.commit()
        blocked = EmailSuppression(email=contact.email, reason="OPT_OUT")
        db.add(blocked)
        db.commit()
        expect(409, lambda: send_approved(db, approved.id, sender.id, uuid4(), capture))
        db.rollback()
        db.delete(blocked)
        db.commit()
        service = Principal(wid, "service:test", "SERVICE")
        context = current_principal.set(service)
        try:
            expect(
                403, lambda: send_approved(db, approved.id, sender.id, uuid4(), capture)
            )
        finally:
            current_principal.reset(context)
        key = uuid4()
        result = send_approved(db, approved.id, sender.id, key, capture)
        assert result["status"] == "ACCEPTED" and len(calls) == 1
        assert (
            send_approved(db, approved.id, sender.id, key, capture)["status"]
            == "ACCEPTED"
        )
        assert (
            send_approved(db, approved.id, sender.id, uuid4(), capture)["status"]
            == "ACCEPTED"
            and len(calls) == 1
        )
        retry = action()
        key = uuid4()

        def auth_failure(*args):
            raise HandoffError("SMTP_AUTHENTICATION_FAILED")

        assert (
            send_approved(db, retry.id, sender.id, key, auth_failure)["status"]
            == "FAILED"
        )
        assert (
            send_approved(db, retry.id, sender.id, key, capture)["status"] == "FAILED"
        )
        assert (
            send_approved(db, retry.id, sender.id, uuid4(), capture)["status"]
            == "ACCEPTED"
        )
        uncertain = action()

        def disconnected(*args):
            raise HandoffError("SMTP_HANDOFF_UNCERTAIN", True)

        assert (
            send_approved(db, uncertain.id, sender.id, uuid4(), disconnected)["status"]
            == "UNCERTAIN"
        )
        count = len(calls)
        assert (
            send_approved(db, uncertain.id, sender.id, uuid4(), capture)["status"]
            == "UNCERTAIN"
            and len(calls) == count
        )
        modified = action()
        modified.content = "Changed after approval without a new decision"
        db.commit()
        expect(409, lambda: send_approved(db, modified.id, sender.id, uuid4(), capture))
        db.rollback()
        sender.workspace_id = foreign_id
        expect(503, lambda: decrypt_password(sender))
        db.rollback()
    with SessionLocal(
        info={
            "workspace_id": foreign_id,
            "principal": Principal(foreign_id, actor, "ADMIN", user_id),
        }
    ) as other:
        assert other.get(SenderAccount, sender_id) is None
        assert other.scalar(select(DeliveryAttempt)) is None

    # Test the real SMTP adapter with a fake socket-free client: TLS before AUTH, no DATA on rejection.
    class Client:
        def __init__(self, *args, **kwargs):
            self.events = []
            clients.append(self)

        def ehlo(self):
            self.events.append("EHLO")

        def starttls(self, **kwargs):
            self.events.append("TLS")

        def login(self, *args):
            self.events.append("AUTH")

        def mail(self, *args):
            self.events.append("MAIL")
            return 250, b"ok"

        def rcpt(self, *args):
            self.events.append("RCPT")
            return 250, b"ok"

        def data(self, *args):
            self.events.append("DATA")
            return 250, b"ok"

        def close(self):
            self.events.append("CLOSE")

    clients = []
    from types import SimpleNamespace
    from email.message import EmailMessage

    connection = SimpleNamespace(
        host="smtp.example.com",
        port=587,
        security="STARTTLS",
        username="user",
        from_email="sender@example.test",
    )
    with patch("app.services.smtp_delivery.PinnedSMTP", Client):
        smtp_handoff(
            connection, "test-password", EmailMessage(), "recipient@example.test"
        )
    assert clients[0].events == [
        "EHLO",
        "TLS",
        "EHLO",
        "AUTH",
        "MAIL",
        "RCPT",
        "DATA",
        "CLOSE",
    ]
    print(
        "PASS SMTP encryption/workspace binding, separate approval/send, immutable recipient/content, suppressions, human-only access, acceptance/idempotence, explicit safe retries and uncertain-handoff duplicate prevention; test transport only"
    )
finally:
    current_principal.reset(token)
