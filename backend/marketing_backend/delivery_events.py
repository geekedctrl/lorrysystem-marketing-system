"""Sanitized delivery diagnostics; no recipient, body or credentials."""
import json
import logging
from .models import DeliveryEvent
from .pools import channel_pool

from .diagnostics import DELIVERY_CATEGORIES, delivery_failure

KNOWN = set(DELIVERY_CATEGORIES)


def public_failure(code, attempt=1):
    failure=delivery_failure(code,attempt) if code else None
    return dict(error_code=failure.code if failure else None,
        error_category=failure.category if failure else None,
        retryable=failure.retryable if failure else False,
        automatic_retry=False)


def event_read(event):
    result={k:getattr(event,k) for k in ("id","delivery_id","product_line_id","event","pool","channel",
        "trace_id","attempt","schema_version","duration_ms","created_at")}
    return {**result,**public_failure(event.error_code,event.attempt)}



def record(db, delivery, attempt, event, code=None, duration_ms=None):
    failure = public_failure(code,attempt.attempt_number)
    safe = failure["error_code"]
    values = dict(workspace_id=delivery.workspace_id, product_line_id=delivery.product_line_id,
        delivery_id=delivery.id, attempt_id=attempt.id, event=event, pool=channel_pool(delivery.channel),
        channel=delivery.channel, trace_id=delivery.trace_id, attempt=attempt.attempt_number,
        schema_version=1, error_code=safe, duration_ms=duration_ms)
    db.add(DeliveryEvent(**values))
    logging.getLogger("marketing-delivery").info(json.dumps({k:str(v) if k.endswith("_id") else v
        for k,v in {**values,**failure,"stage":delivery.channel,"contract_version":1}.items()}, separators=(",", ":")))
