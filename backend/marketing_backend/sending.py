"""Encrypted SMTP connections and a restart-safe, human-approved delivery outbox."""

import json, os, re, secrets, smtplib, socket, ssl
from datetime import timedelta
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formataddr
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import select
from .models import Delivery, DeliveryAttempt, SenderConnection, now
from .public_fetch import pinned_address, FetchError


def normalized_email(value):
    value = value.strip().lower()
    if len(value) > 254 or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}", value):
        raise ValueError("Enter one business email address")
    return value


def vault():
    try:
        return Fernet(os.environ.get("SENDER_CREDENTIAL_ENCRYPTION_KEY", "").encode())
    except (ValueError, TypeError):
        raise HTTPException(503, "Sender credential encryption is not configured") from None


def encrypt_secret(password, workspace_id):
    return vault().encrypt(json.dumps({"workspace_id": str(workspace_id), "password": password}).encode()).decode()


def decrypt_secret(sender):
    try:
        value = json.loads(vault().decrypt(sender.secret_ciphertext.encode()))
        if value["workspace_id"] != str(sender.workspace_id):
            raise InvalidToken
        return value["password"]
    except (InvalidToken, KeyError, ValueError, TypeError):
        raise HTTPException(503, "Sender credentials are unavailable; reconnect the account") from None


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
    client, data_started = None, False
    try:
        context = ssl.create_default_context()
        if sender.security == "TLS":
            client = PinnedSMTPSSL(sender.host, sender.port, timeout=20, context=context)
        else:
            client = PinnedSMTP(sender.host, sender.port, timeout=20)
            client.ehlo(); client.starttls(context=context); client.ehlo()
        client.login(sender.username, password)
        if message is None:
            return
        code, _ = client.mail(sender.from_email)
        if code != 250: raise HandoffError("SMTP_SENDER_REJECTED")
        code, _ = client.rcpt(recipient)
        if code not in (250, 251): raise HandoffError("SMTP_RECIPIENT_REJECTED")
        data_started = True
        code, _ = client.data(message.as_bytes())
        if code != 250: raise HandoffError("SMTP_DATA_REJECTED")
    except HandoffError:
        raise
    except smtplib.SMTPAuthenticationError:
        raise HandoffError("SMTP_AUTHENTICATION_FAILED") from None
    except smtplib.SMTPDataError:
        raise HandoffError("SMTP_DATA_REJECTED") from None
    except (OSError, smtplib.SMTPException, FetchError):
        raise HandoffError("SMTP_HANDOFF_UNCERTAIN" if data_started else "SMTP_CONNECTION_FAILED", data_started) from None
    finally:
        if client:
            try: client.close()
            except OSError: pass


def build_message(delivery, sender):
    snap = delivery.snapshot
    message = EmailMessage(policy=SMTP)
    message["From"] = formataddr((sender.from_name, sender.from_email))
    message["To"] = snap["recipient"]
    message["Subject"] = snap["subject"]
    message["Message-ID"] = f"<{delivery.id}@{sender.from_email.split('@')[1]}>"
    message.set_content(snap["body"], cte="quoted-printable")
    return message


def claim_attempt(db, lease_seconds=120):
    attempt = db.scalar(select(DeliveryAttempt).where(DeliveryAttempt.status == "READY", DeliveryAttempt.available_at <= now()).order_by(DeliveryAttempt.created_at).with_for_update(skip_locked=True).limit(1))
    if not attempt: return None
    delivery = db.get(Delivery, attempt.delivery_id)
    if not delivery or delivery.status != "QUEUED": return None
    attempt.status, attempt.lease_token = "SENDING", secrets.token_hex(24)
    attempt.lease_until = now() + timedelta(seconds=lease_seconds)
    delivery.status, delivery.updated_at = "SENDING", now()
    db.commit()
    return attempt.id, attempt.lease_token


def execute_attempt(db, attempt_id, token, transport=None):
    attempt = db.scalar(select(DeliveryAttempt).where(DeliveryAttempt.id == attempt_id, DeliveryAttempt.lease_token == token, DeliveryAttempt.status == "SENDING").with_for_update())
    if not attempt or attempt.lease_until <= now(): return False
    delivery, sender = db.get(Delivery, attempt.delivery_id), None
    if delivery: sender = db.get(SenderConnection, delivery.sender_id)
    if not delivery or not sender:
        return False
    if not sender.enabled or not sender.verified_at:
        attempt.status, attempt.failure_code, attempt.finished_at = "FAILED", "SENDER_NOT_VERIFIED", now()
        attempt.lease_token = attempt.lease_until = None
        delivery.status, delivery.updated_at = "FAILED", now()
        db.commit()
        return True
    message = build_message(delivery, sender)
    attempt.message_id = message["Message-ID"]
    try:
        (transport or smtp_handoff)(sender, decrypt_secret(sender), message, delivery.snapshot["recipient"])
        attempt.status, delivery.status = "ACCEPTED", "ACCEPTED"
    except HandoffError as exc:
        attempt.status = "UNCERTAIN" if exc.uncertain else "FAILED"
        delivery.status, attempt.failure_code = attempt.status, exc.code
    except Exception:
        attempt.status = delivery.status = "UNCERTAIN"
        attempt.failure_code = "SMTP_HANDOFF_UNCERTAIN"
    attempt.finished_at, attempt.lease_token, attempt.lease_until = now(), None, None
    delivery.updated_at = now()
    db.commit()
    return True


def recover_expired(db):
    """A lost worker may have crossed SMTP DATA; preserve it as uncertain."""
    for attempt in db.scalars(select(DeliveryAttempt).where(DeliveryAttempt.status == "SENDING", DeliveryAttempt.lease_until < now()).with_for_update(skip_locked=True)):
        attempt.status, attempt.failure_code, attempt.finished_at = "UNCERTAIN", "WORKER_TERMINATED_DURING_HANDOFF", now()
        attempt.lease_token = attempt.lease_until = None
        delivery = db.get(Delivery, attempt.delivery_id)
        if delivery:
            delivery.status, delivery.updated_at = "UNCERTAIN", now()
    db.commit()
