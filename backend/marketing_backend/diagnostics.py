"""Stable log/event classification. Never return the caller's raw exception."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Failure:
    code: str
    category: str
    retryable: bool = False


def classify(code, retryable=False):
    if not isinstance(code, str):
        return Failure("HANDLER_ERROR", "internal")
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
