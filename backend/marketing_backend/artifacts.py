"""Transactional worker artifacts/events; callers own the final commit.

These are opt-in foundation primitives. Existing stage execution is not routed
through them until product-line context selection and quarantine are integrated.
Do not call this module from a provider adapter or log its payload arguments.
"""

from typing import Literal
from uuid import UUID

from pydantic import Field
from sqlalchemy import select, text

from .models import ProductLine, StageArtifact, StageEvent, Job
from . import queue
from .stage_contracts import (
    Strict, Code, Hash, Stage, ContractViolation, canonical_json, content_hash,
    validate_envelope, validate_payload,
)

FailureCode = Literal[
    "CONFIGURATION_ERROR", "PROVIDER_TRANSPORT", "PROVIDER_THROTTLED",
    "PROVIDER_SCHEMA_INVALID", "EVIDENCE_INVALID", "BUDGET_EXHAUSTED",
    "STALE_CONTEXT", "LEASE_LOST", "UNSUPPORTED_CONTRACT", "HANDLER_ERROR",
    "TASK_ENVELOPE_INVALID", "STAGE_PAYLOAD_INVALID", "ARTIFACT_HASH_MISMATCH",
    "ARTIFACT_SCOPE_MISMATCH", "ARTIFACT_METADATA_INVALID", "ARTIFACT_CONFLICT",
]


class EvidenceReference(Strict):
    source_url: str = Field(min_length=8, max_length=1500)
    content_hash: Hash


class Provenance(Strict):
    evidence_refs: list[EvidenceReference] = Field(max_length=50)
    strategy_versions: dict[Code, Code] = Field(max_length=10)
    input_hashes: dict[Code, Hash] = Field(max_length=20)


class EventData(Strict):
    event: Literal["CLAIM", "CHECKPOINT", "RETRY", "COMPLETION", "FAILURE", "LEASE_LOSS", "QUARANTINE", "REPLAY"]
    pool: Stage
    stage: Stage
    attempt: int = Field(ge=0, le=5)
    schema_version: int = Field(ge=1, le=2)
    trace_id: UUID
    error_code: FailureCode | None = None
    duration_ms: int | None = Field(default=None, ge=0)


def _metadata(value, schema):
    try:
        return schema.model_validate_json(canonical_json(value)).model_dump(mode="json")
    except (ValueError, TypeError, OverflowError):
        raise ContractViolation("ARTIFACT_METADATA_INVALID") from None


def _line(db, workspace_id, line_id, version, context_hash):
    db.execute(text("SELECT worker_lock_product_line(:wid,:lid)"), {"wid": workspace_id, "lid": line_id})
    line = db.scalar(select(ProductLine).where(
        ProductLine.workspace_id == workspace_id, ProductLine.id == line_id,
    ).execution_options(populate_existing=True))
    if not line:
        raise ContractViolation("ARTIFACT_SCOPE_MISMATCH")
    if line.context_version != version or line.context_hash != context_hash or line.paused:
        raise ContractViolation("STALE_CONTEXT")
    return line


def _references(db, envelope, payload):
    for ref in envelope.prior_artifacts:
        artifact = db.scalar(select(StageArtifact).where(
            StageArtifact.id == ref.artifact_id,
            StageArtifact.workspace_id == envelope.workspace_id,
            StageArtifact.product_line_id == envelope.product_line_id,
        ))
        if (not artifact or artifact.contract_name != ref.contract_name
                or artifact.schema_version != ref.schema_version
                or artifact.content_hash != ref.content_hash
                or artifact.context_hash != envelope.context_hash
                or artifact.context_version != envelope.context_version
                or content_hash(validate_payload(artifact.contract_name, artifact.schema_version, artifact.payload)) != ref.content_hash):
            raise ContractViolation("ARTIFACT_SCOPE_MISMATCH")
    allowed = {str(ref.artifact_id) for ref in envelope.prior_artifacts}
    if not set(payload.get("source_artifact_ids", [])).issubset(allowed):
        raise ContractViolation("ARTIFACT_SCOPE_MISMATCH")


def persist_artifact(db, job_id, token, envelope, payload, artifact_key, provenance):
    """Validate producer output before INSERT; serialize duplicate completions.

    The existing job lease/ownership check locks job+workspace before the line
    lock. No commit is performed, so artifact, event and next-job transition can
    share one transaction. A repeated key with different content fails closed.
    """
    value = validate_envelope(envelope)
    job = queue.owned(db, job_id, token)
    if (value.job_id != job.id or value.workspace_id != job.workspace_id
            or value.product_line_id != job.product_line_id or value.stage != job.kind
            or value.idempotency_key != job.idempotency_key
            or value.attempt != job.attempts or value.max_attempts != job.max_attempts
            or value.lead_id != job.lead_id):
        raise ContractViolation("ARTIFACT_SCOPE_MISMATCH")
    _line(db, value.workspace_id, value.product_line_id, value.context_version, value.context_hash)
    if not isinstance(artifact_key, str) or not 1 <= len(artifact_key) <= 120:
        raise ContractViolation("ARTIFACT_METADATA_INVALID")
    result = validate_payload(value.contract_name, value.schema_version, payload)
    _references(db, value, result)
    metadata = _metadata(provenance, Provenance)
    digest = content_hash(result)
    existing = db.scalar(select(StageArtifact).where(
        StageArtifact.job_id == job.id, StageArtifact.artifact_key == artifact_key,
    ))
    if existing:
        unchanged = (
            existing.content_hash == digest and content_hash(existing.payload) == digest
            and existing.contract_name == value.contract_name
            and existing.schema_version == value.schema_version
            and existing.context_hash == value.context_hash
            and existing.context_version == value.context_version
            and existing.producer_version == value.producer_version
            and existing.envelope.get("trace_id") == str(value.trace_id)
            and all(getattr(existing, k) == v for k, v in metadata.items())
        )
        if not unchanged:
            raise ContractViolation("ARTIFACT_CONFLICT")
        return existing
    artifact = StageArtifact(
        workspace_id=job.workspace_id, product_line_id=job.product_line_id,
        job_id=job.id, artifact_key=artifact_key, contract_name=value.contract_name,
        schema_version=value.schema_version, producer_version=value.producer_version,
        context_version=value.context_version, context_hash=value.context_hash,
        content_hash=digest, envelope=value.model_dump(mode="json"), payload=result,
        **metadata,
    )
    db.add(artifact)
    db.flush()
    return artifact


def consume_artifact(db, artifact_id, workspace_id, product_line_id, context_version, context_hash):
    """Consumer entry validates scope, current context, version, payload and hash."""
    artifact = db.scalar(select(StageArtifact).where(
        StageArtifact.id == artifact_id, StageArtifact.workspace_id == workspace_id,
        StageArtifact.product_line_id == product_line_id,
    ))
    if not artifact:
        raise ContractViolation("ARTIFACT_SCOPE_MISMATCH")
    _line(db, workspace_id, product_line_id, context_version, context_hash)
    if artifact.context_version != context_version or artifact.context_hash != context_hash:
        raise ContractViolation("STALE_CONTEXT")
    value = validate_envelope(artifact.envelope)
    if (value.workspace_id != workspace_id or value.product_line_id != product_line_id
            or value.job_id != artifact.job_id or value.contract_name != artifact.contract_name
            or value.schema_version != artifact.schema_version
            or value.producer_version != artifact.producer_version
            or value.context_version != context_version or value.context_hash != context_hash):
        raise ContractViolation("ARTIFACT_SCOPE_MISMATCH")
    result = validate_payload(artifact.contract_name, artifact.schema_version, artifact.payload)
    if content_hash(result) != artifact.content_hash:
        raise ContractViolation("ARTIFACT_HASH_MISMATCH")
    _references(db, value, result)
    return result


def append_event(db, job_id, workspace_id, product_line_id, data):
    """Append only known structured fields; no payload/message/detail parameter."""
    value = _metadata(data, EventData)
    job = db.scalar(select(Job).where(
        Job.id == job_id, Job.workspace_id == workspace_id,
        Job.product_line_id == product_line_id,
    ).with_for_update())
    if (not job or job.kind != value["stage"] or value["pool"] != value["stage"]
            or job.attempts != value["attempt"]):
        raise ContractViolation("ARTIFACT_SCOPE_MISMATCH")
    value["trace_id"] = UUID(value["trace_id"])
    event = StageEvent(job_id=job_id, workspace_id=workspace_id, product_line_id=product_line_id, **value)
    db.add(event)
    db.flush()
    return event
