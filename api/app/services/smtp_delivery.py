"""Explicit SMTP handoff; failures after DATA are uncertain and never retried."""

import json, os, smtplib, socket, ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formataddr
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import select, text
from app.models.sending import SenderAccount, DeliveryAttempt, EmailSuppression
from app.models.marketing import MarketingAction, ApprovalRequest, Event
from app.models.companies import Contact, Company
from app.models.leads import Lead
from app.services.approval_service import build_content_snapshot
from app.services.public_fetch_guard import pinned_address, FetchError
from app.workspace_context import current_principal


def permit_sender(admin=False):
    p = current_principal.get()
    if (
        not p
        or not p.user_id
        or p.automation_job_id
        or p.role not in (("ADMIN",) if admin else ("ADMIN", "OPERATOR"))
    ):
        raise HTTPException(
            403,
            (
                "A signed-in workspace administrator is required"
                if admin
                else "A signed-in operator or administrator is required to send"
            ),
        )
    return p


def vault():
    try:
        return Fernet(os.environ.get("SMTP_CREDENTIAL_ENCRYPTION_KEY", "").encode())
    except (ValueError, TypeError):
        raise HTTPException(
            503, "Platform SMTP credential encryption is not configured"
        ) from None


def encrypt_password(password, workspace_id):
    return (
        vault()
        .encrypt(
            json.dumps(
                {"workspace_id": str(workspace_id), "password": password}
            ).encode()
        )
        .decode()
    )


def decrypt_password(sender):
    try:
        value = json.loads(vault().decrypt(sender.password_ciphertext.encode()))
        if value["workspace_id"] != str(sender.workspace_id):
            raise InvalidToken
        return value["password"]
    except (InvalidToken, KeyError, ValueError):
        raise HTTPException(
            503, "Sender credentials are unavailable; reconnect the account"
        ) from None


class PinnedSMTP(smtplib.SMTP):
    def _get_socket(self, host, port, timeout):
        return socket.create_connection((pinned_address(host, port), port), timeout)


class PinnedSMTPSSL(smtplib.SMTP_SSL):
    def _get_socket(self, host, port, timeout):
        raw = socket.create_connection((pinned_address(host, port), port), timeout)
        try:
            return self.context.wrap_socket(raw, server_hostname=host)
        except Exception:
            raw.close()
            raise


class HandoffError(Exception):
    def __init__(self, code, uncertain=False):
        self.code, self.uncertain = code, uncertain


def smtp_handoff(sender, password, message=None, recipient=None):
    client = None
    data_started = False
    try:
        context = ssl.create_default_context()
        if sender.security == "TLS":
            client = PinnedSMTPSSL(
                sender.host, sender.port, timeout=20, context=context
            )
        else:
            client = PinnedSMTP(sender.host, sender.port, timeout=20)
            client.ehlo()
            client.starttls(context=context)
            client.ehlo()
        client.login(sender.username, password)
        if message is None:
            return
        # MAIL/RCPT can fail safely; once DATA starts a disconnect is ambiguous.
        code, _ = client.mail(sender.from_email)
        if code != 250:
            raise HandoffError("SMTP_SENDER_REJECTED")
        code, _ = client.rcpt(recipient)
        if code not in (250, 251):
            raise HandoffError("SMTP_RECIPIENT_REJECTED")
        data_started = True
        code, _ = client.data(message.as_bytes())
        if code != 250:
            raise HandoffError("SMTP_DATA_REJECTED")
    except HandoffError:
        raise
    except smtplib.SMTPAuthenticationError:
        raise HandoffError("SMTP_AUTHENTICATION_FAILED") from None
    except smtplib.SMTPDataError:
        raise HandoffError("SMTP_DATA_REJECTED") from None
    except (OSError, smtplib.SMTPException, FetchError):
        raise HandoffError(
            "SMTP_HANDOFF_UNCERTAIN" if data_started else "SMTP_CONNECTION_FAILED",
            data_started,
        ) from None
    finally:
        # QUIT failure after accepted DATA does not change the SMTP acceptance result.
        if client is not None:
            try:
                client.close()
            except OSError:
                pass


def attempt_read(attempt):
    return {
        key: getattr(attempt, key)
        for key in (
            "id",
            "action_id",
            "sender_id",
            "recipient",
            "message_id",
            "status",
            "failure_reason",
            "attempt_count",
            "created_at",
            "finished_at",
        )
    }


def audit(db, action, kind, **metadata):
    db.add(
        Event(
            event_type=kind,
            entity_type="MARKETING_ACTION",
            entity_id=action.id,
            actor_type="USER",
            actor_id=current_principal.get().actor,
            metadata_json=metadata,
        )
    )


def send_approved(db, action_id, sender_id, idempotency_key, transport=None):
    principal = permit_sender()
    # Serialize duplicate submissions before committing the durable handoff intent.
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": f"send:{principal.workspace_id}:{action_id}"},
    )
    action = db.scalar(
        select(MarketingAction).where(MarketingAction.id == action_id).with_for_update()
    )
    if not action:
        raise HTTPException(404, "Marketing action not found")
    previous = db.scalar(
        select(DeliveryAttempt).where(DeliveryAttempt.action_id == action.id)
    )
    if previous and (
        previous.idempotency_key == idempotency_key
        or previous.status in ("SENDING", "ACCEPTED", "UNCERTAIN")
    ):
        return attempt_read(previous)
    if (
        action.status != "APPROVED"
        or action.channel != "EMAIL"
        or action.action_type not in ("EMAIL", "FOLLOW_UP")
    ):
        raise HTTPException(409, "Only a separately approved email can be sent")
    approval = db.scalar(
        select(ApprovalRequest)
        .where(ApprovalRequest.marketing_action_id == action.id)
        .order_by(ApprovalRequest.requested_at.desc(), ApprovalRequest.id.desc())
        .limit(1)
    )
    if (
        not approval
        or approval.status != "APPROVED"
        or approval.content_snapshot != build_content_snapshot(action, db)
    ):
        raise HTTPException(
            409, "Current email content must match its approved snapshot"
        )
    contact = db.get(Contact, action.contact_id) if action.contact_id else None
    lead = db.get(Lead, action.lead_id) if action.lead_id else None
    company = db.get(Company, lead.company_id) if lead else None
    if (
        not contact
        or not lead
        or not company
        or contact.company_id != lead.company_id
        or contact.status != "ACTIVE"
        or company.status != "ACTIVE"
        or lead.status in ("CONVERTED", "DISQUALIFIED")
        or not contact.email
    ):
        raise HTTPException(
            409, "An active company-linked email contact and lead are required"
        )
    from app.routers.sending import normalized_email

    try:
        recipient = normalized_email(contact.email)
    except ValueError:
        raise HTTPException(
            409, "The contact does not have a valid single email address"
        ) from None
    if db.scalar(
        select(EmailSuppression.id).where(EmailSuppression.email == recipient)
    ):
        raise HTTPException(409, "This recipient is suppressed for this product")
    sender = db.scalar(
        select(SenderAccount).where(SenderAccount.id == sender_id).with_for_update()
    )
    if not sender:
        raise HTTPException(404, "Sender account not found")
    if not sender.enabled or not sender.verified_at:
        raise HTTPException(409, "Connect and verify an enabled sender account first")
    if previous and previous.attempt_count >= 3:
        raise HTTPException(409, "Maximum explicit send attempts reached")
    if db.scalar(
        select(DeliveryAttempt.id).where(
            DeliveryAttempt.idempotency_key == idempotency_key,
            DeliveryAttempt.action_id != action.id,
        )
    ):
        raise HTTPException(
            409, "This send request identifier belongs to another action"
        )
    password = decrypt_password(sender)
    from types import SimpleNamespace

    connection = SimpleNamespace(
        **{
            key: getattr(sender, key)
            for key in ("host", "port", "security", "username", "from_email")
        }
    )
    if action.subject and any(character in action.subject for character in "\r\n"):
        raise HTTPException(422, "Email subject must be a single line")
    message = EmailMessage(policy=SMTP)
    message["From"] = formataddr((sender.from_name, sender.from_email))
    message["To"] = recipient
    message["Subject"] = action.subject or ""
    message["Message-ID"] = f"<{action.id}@{sender.from_email.split('@')[1]}>"
    message.set_content(action.content, cte="quoted-printable")
    attempt = previous or DeliveryAttempt(
        action_id=action.id,
        sender_id=sender.id,
        idempotency_key=idempotency_key,
        recipient=recipient,
        message_id=message["Message-ID"],
        status="SENDING",
        requested_by=principal.actor,
    )
    if previous:
        attempt.idempotency_key = idempotency_key
        attempt.sender_id = sender.id
        attempt.recipient = recipient
        attempt.attempt_count += 1
        attempt.status = "SENDING"
        attempt.failure_reason = None
        attempt.finished_at = None
    db.add(attempt)
    action.status = "QUEUED"
    audit(db, action, "email_send_requested", sender_id=str(sender.id))
    db.commit()
    try:
        (transport or smtp_handoff)(connection, password, message, recipient)
        attempt.status = "ACCEPTED"
        action.status = "SENT"
        action.executed_at = datetime.now(timezone.utc)
        action.external_reference = attempt.message_id
    except HandoffError as error:
        attempt.status = "UNCERTAIN" if error.uncertain else "FAILED"
        attempt.failure_reason = error.code
        action.status = "QUEUED" if error.uncertain else "APPROVED"
    except Exception:
        # Unexpected failures after durable handoff intent never authorize a repeat send.
        attempt.status = "UNCERTAIN"
        attempt.failure_reason = "SMTP_HANDOFF_UNCERTAIN"
        action.status = "QUEUED"
    attempt.finished_at = datetime.now(timezone.utc)
    audit(
        db,
        action,
        "email_send_result",
        status=attempt.status,
        failure_reason=attempt.failure_reason,
        message_id=attempt.message_id,
    )
    db.commit()
    return attempt_read(attempt)
