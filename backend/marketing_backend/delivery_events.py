"""Sanitized delivery diagnostics; no recipient, body or credentials."""
import json
import logging
from .models import DeliveryEvent
from .pools import channel_pool

KNOWN = {"STALE_APPROVAL_CONTEXT", "SENDER_NOT_VERIFIED", "RECIPIENT_SUPPRESSED", "PRODUCT_PAUSED",
    "CHANNEL_NOT_CONFIGURED", "SMTP_SENDER_REJECTED", "SMTP_RECIPIENT_REJECTED", "SMTP_DATA_REJECTED",
    "SMTP_AUTHENTICATION_FAILED", "SMTP_CONNECTION_FAILED", "SMTP_HANDOFF_UNCERTAIN",
    "CHANNEL_HANDOFF_UNCERTAIN", "WORKER_TERMINATED_DURING_HANDOFF"}


def record(db, delivery, attempt, event, code=None, duration_ms=None):
    safe = code if code in KNOWN else ("HANDLER_ERROR" if code else None)
    values = dict(workspace_id=delivery.workspace_id, product_line_id=delivery.product_line_id,
        delivery_id=delivery.id, attempt_id=attempt.id, event=event, pool=channel_pool(delivery.channel),
        channel=delivery.channel, trace_id=delivery.trace_id, attempt=attempt.attempt_number,
        schema_version=1, error_code=safe, duration_ms=duration_ms)
    db.add(DeliveryEvent(**values))
    logging.getLogger("marketing-delivery").info(json.dumps({k:str(v) if k.endswith("_id") else v
        for k,v in values.items()}, separators=(",", ":")))
