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


def claim_attempt(db, lease_seconds=120, pool="EMAIL"):
    from sqlalchemy import func, Integer, or_, text
    from sqlalchemy.orm import aliased
    from .models import ExecutorOwnership, ProductLine, Workspace
    from .pools import get_pool
    selected = get_pool(pool)
    if selected.kind != "delivery":
        raise ValueError("A delivery pool is required")
    active_attempt, active_delivery = aliased(DeliveryAttempt), aliased(Delivery)
    active = select(func.count()).select_from(active_attempt).join(active_delivery,
        active_delivery.id == active_attempt.delivery_id).where(
        active_delivery.product_line_id == Delivery.product_line_id,
        active_delivery.channel == Delivery.channel,
        active_attempt.status == "SENDING").correlate(Delivery).scalar_subquery()
    attempt = db.scalar(select(DeliveryAttempt).join(Delivery, Delivery.id == DeliveryAttempt.delivery_id)
        .join(ProductLine, ProductLine.id == Delivery.product_line_id)
        .join(Workspace, Workspace.id == Delivery.workspace_id)
        .join(ExecutorOwnership, (ExecutorOwnership.workspace_id == Delivery.workspace_id) &
            (ExecutorOwnership.capability == "SENDING"))
        .where(DeliveryAttempt.status == "READY", DeliveryAttempt.available_at <= now(),
            Delivery.status == "QUEUED", Delivery.channel.in_(selected.channels),
            Workspace.active.is_(True),
            or_(ProductLine.versioned.is_(False), ProductLine.paused.is_(False)),
            ExecutorOwnership.owner == "PYTHON", ExecutorOwnership.state == "ACTIVE",
            active < func.coalesce(ProductLine.limits["per_pool_concurrency"].astext.cast(Integer),1))
        .order_by(DeliveryAttempt.created_at,DeliveryAttempt.id)
        .with_for_update(of=DeliveryAttempt,skip_locked=True).limit(1))
    if not attempt:
        return None
    delivery = db.scalar(select(Delivery).where(Delivery.id == attempt.delivery_id).with_for_update())
    key = "delivery:"+str(delivery.product_line_id)+":"+delivery.channel
    if not db.scalar(text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key,0))"), {"key":key}):
        db.commit(); return None
    count = db.scalar(select(func.count()).select_from(DeliveryAttempt).join(Delivery,
        Delivery.id == DeliveryAttempt.delivery_id).where(Delivery.product_line_id == delivery.product_line_id,
        Delivery.channel == delivery.channel,DeliveryAttempt.status == "SENDING"))
    if count >= db.get(ProductLine,delivery.product_line_id).limits.get("per_pool_concurrency",1):
        db.commit(); return None
    attempt.status, attempt.lease_token = "SENDING", secrets.token_hex(24)
    attempt.lease_until = now() + timedelta(seconds=lease_seconds)
    delivery.status, delivery.updated_at = "SENDING", now()
    from .delivery_events import record
    record(db,delivery,attempt,"CLAIM")
    db.commit()
    return attempt.id, attempt.lease_token


def execute_attempt(db, attempt_id, token, transport=None, pool="EMAIL", adapter=None):
    import time
    from .pools import get_pool
    from .models import Workspace, ProductLine, EmailSuppression
    from .delivery_events import record
    selected = get_pool(pool)
    if selected.kind != "delivery":
        raise ValueError("A delivery pool is required")
    started = time.monotonic()
    attempt = db.scalar(select(DeliveryAttempt).where(DeliveryAttempt.id == attempt_id,
        DeliveryAttempt.lease_token == token,DeliveryAttempt.status == "SENDING").with_for_update())
    if not attempt or attempt.lease_until <= now():
        return False
    delivery = db.get(Delivery, attempt.delivery_id)
    if not delivery or delivery.channel not in selected.channels:
        return False
    from .ownership import active_python
    if not active_python(db,attempt.workspace_id,"SENDING"):
        return False
    from .approval_context import valid_delivery
    workspace = db.get(Workspace,attempt.workspace_id)
    line = db.get(ProductLine,attempt.product_line_id)
    code = None
    if not workspace or not workspace.active or not line or (line.versioned and line.paused):
        code = "PRODUCT_PAUSED"
    elif not valid_delivery(db,delivery,require_send=True):
        code = "STALE_APPROVAL_CONTEXT"
    elif delivery.channel == "EMAIL" and db.scalar(select(EmailSuppression.id).where(
        EmailSuppression.workspace_id == delivery.workspace_id,
        EmailSuppression.email == delivery.snapshot.get("recipient"))):
        code = "RECIPIENT_SUPPRESSED"
    sender = db.get(SenderConnection,delivery.sender_id) if delivery.sender_id else None
    if not code and delivery.channel == "EMAIL" and (not sender or not sender.enabled or not sender.verified_at):
        code = "SENDER_NOT_VERIFIED"
    if code:
        attempt.status,attempt.failure_code,delivery.status = "FAILED",code,"FAILED"
    else:
        try:
            if delivery.channel == "EMAIL":
                message = build_message(delivery,sender)
                attempt.message_id = message["Message-ID"]
                (transport or smtp_handoff)(sender,decrypt_secret(sender),message,delivery.snapshot["recipient"])
            else:
                from .channels import adapter_for
                receipt = (adapter or adapter_for(delivery.channel)).handoff(delivery)
                attempt.message_id = receipt.reference
            attempt.status = delivery.status = "ACCEPTED"
        except HandoffError as exc:
            from .delivery_events import KNOWN
            attempt.status = delivery.status = "UNCERTAIN" if exc.uncertain else "FAILED"
            attempt.failure_code = exc.code if exc.code in KNOWN else "HANDLER_ERROR"
        except Exception as exc:
            from .channels import AdapterUnavailable
            if isinstance(exc,AdapterUnavailable):
                attempt.status = delivery.status = "FAILED"
                attempt.failure_code = "CHANNEL_NOT_CONFIGURED"
            else:
                attempt.status = delivery.status = "UNCERTAIN"
                attempt.failure_code = "SMTP_HANDOFF_UNCERTAIN" if delivery.channel == "EMAIL" else "CHANNEL_HANDOFF_UNCERTAIN"
    attempt.finished_at,attempt.lease_token,attempt.lease_until = now(),None,None
    delivery.updated_at = now()
    record(db,delivery,attempt,"COMPLETION" if attempt.status == "ACCEPTED" else "FAILURE",
        attempt.failure_code,max(0,int((time.monotonic()-started)*1000)))
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
            from .delivery_events import record
            record(db,delivery,attempt,"LEASE_LOSS","WORKER_TERMINATED_DURING_HANDOFF")
    db.commit()
