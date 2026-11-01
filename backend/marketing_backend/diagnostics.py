"""Stable log/event classification. Never return the caller's raw exception."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Failure:
    code: str
    category: str
    retryable: bool = False


DELIVERY_CATEGORIES = {
    "STALE_APPROVAL_CONTEXT": "context", "PRODUCT_PAUSED": "context",
    "SENDER_NOT_VERIFIED": "configuration", "CHANNEL_NOT_CONFIGURED": "configuration",
    "SMTP_AUTHENTICATION_FAILED": "configuration", "RECIPIENT_SUPPRESSED": "policy",
    "SMTP_SENDER_REJECTED": "provider_response", "SMTP_RECIPIENT_REJECTED": "provider_response",
    "SMTP_DATA_REJECTED": "provider_response", "SMTP_CONNECTION_FAILED": "provider_transport",
    "SMTP_HANDOFF_UNCERTAIN": "delivery_uncertainty", "CHANNEL_HANDOFF_UNCERTAIN": "delivery_uncertainty",
    "WORKER_TERMINATED_DURING_HANDOFF": "lease",
}


def delivery_failure(code, attempt=1):
    # Advisory eligibility for a separate human retry, never an automatic send.
    return classify(code, retryable=type(attempt) is int and 1 <= attempt < 3)


def classify(code, retryable=False):
    if not isinstance(code, str):
        return Failure("HANDLER_ERROR", "internal")
    if code in DELIVERY_CATEGORIES:
        return Failure(code, DELIVERY_CATEGORIES[code], bool(retryable) and code == "SMTP_CONNECTION_FAILED")
    if code in {"UNSUPPORTED_CONTRACT", "TASK_ENVELOPE_INVALID", "TASK_INPUT_INVALID", "STAGE_PAYLOAD_INVALID",
                "ARTIFACT_HASH_MISMATCH", "ARTIFACT_SCOPE_MISMATCH", "ARTIFACT_METADATA_INVALID", "ARTIFACT_CONFLICT"}:
        return Failure(code, "contract")
    if code in {"LEASE_LOST", "LEASE_EXPIRED"}:
        return Failure("LEASE_LOST", "lease")
    if code in {"STALE_CONTEXT", "CONTEXT_CHANGED", "RUN_NOT_ACTIVE"}:
        return Failure("STALE_CONTEXT", "context")
    if "BUDGET" in code or code == "BUDGET_EXHAUSTED":
        return Failure("BUDGET_EXHAUSTED", "budget")
    if "THROTTL" in code or "RATE_LIMIT" in code:
        return Failure("PROVIDER_THROTTLED", "provider_throttling", bool(retryable))
    if "NOT_CONFIGURED" in code or code in {"CONFIGURATION_ERROR", "TARGETING_NOT_READY", "CATALOG_NOT_READY"}:
        return Failure("CONFIGURATION_ERROR", "configuration")
    if "TRANSPORT" in code or "UNAVAILABLE" in code or "TIMEOUT" in code:
        return Failure("PROVIDER_TRANSPORT", "provider_transport", bool(retryable))
    if "OUTPUT" in code or "SCHEMA" in code:
        return Failure("PROVIDER_SCHEMA_INVALID", "provider_schema")
    if "EVIDENCE" in code or "CITATION" in code or code == "CANDIDATE_NOT_SUPPORTED":
        return Failure("EVIDENCE_INVALID", "evidence")
    return Failure("HANDLER_ERROR", "internal")
