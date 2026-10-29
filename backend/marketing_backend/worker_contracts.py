"""Compatibility bridge from the legacy worker to explicit stage contracts.

NULL task_envelope denotes historical, unversioned work. New explicit envelopes
are validated before providers and again at completion. Producers opt in while
product-line settings/APIs and the remaining stage schemas are being migrated.
"""
from typing import Any, Literal
from pydantic import Field

from . import artifacts
from .stage_contracts import (
    Strict, Code, ContractViolation, content_hash, canonical_json,
    validate_envelope, validate_payload,
)
from .diagnostics import classify

IMPLEMENTATION = "native.day1.1"


class EvaluatedDomain(Strict):
    domain: str = Field(min_length=1, max_length=254)
    source_url: str = Field(min_length=8, max_length=1500)
    reason: Code


class DiscoveryCounts(Strict):
    searches_attempted: int = Field(ge=0, le=3)
    searches_unavailable: int = Field(ge=0, le=3)
    websites_attempted: int = Field(ge=0, le=100)
    pages_attempted: int = Field(ge=0, le=10)
    assessments_attempted: int = Field(ge=0, le=10)
    candidates_ready: int = Field(ge=0, le=10)


class DiscoveryBatch(Strict):
    candidates: list[dict[str, Any]] = Field(max_length=10)
    evaluated_domains: list[EvaluatedDomain] = Field(max_length=100)
    coverage: str = Field(max_length=2000)
    counts: DiscoveryCounts
    outcome: Literal["CANDIDATES_READY", "PARTIAL_FAILURE", "NO_NEW_MATCHES"]
    human_review_required: Literal[True]


def event_version(job):
    value = job.task_envelope
    version = value.get("schema_version") if isinstance(value, dict) else None
    return version if type(version) is int and 0 <= version <= 2147483647 else 0


def record(db, job, event, code=None, duration_ms=None, actor_id=None):
    return artifacts.append_event(db, job.id, job.workspace_id, job.product_line_id, dict(
        event=event, stage=job.kind, pool="LEGACY", attempt=job.attempts,
        schema_version=event_version(job), trace_id=str(job.trace_id),
        error_code=classify(code).code if code else None, duration_ms=duration_ms,
        actor_id=str(actor_id) if actor_id else None,
    ))


def validate_task(db, job):
    if job.task_envelope is None:
        return None
    value = validate_envelope(job.task_envelope)
    if (value.job_id != job.id or value.workspace_id != job.workspace_id
            or value.product_line_id != job.product_line_id or value.trace_id != job.trace_id
            or value.stage != job.kind or value.idempotency_key != job.idempotency_key
            or value.max_attempts != job.max_attempts or value.lead_id != job.lead_id
            or (value.company_id is not None and value.company_id != job.lead_id)
            or value.actor_id is not None):
        # Candidate-scoped tasks need the line-specific candidate model in the
        # next ownership migration. Never guess an ownership association here.
        raise ContractViolation("ARTIFACT_SCOPE_MISMATCH")
    if value.input_hash is not None and value.input_hash != content_hash(job.payload):
        raise ContractViolation("ARTIFACT_HASH_MISMATCH")
    from .product_lines import line_mode
    if line_mode(job):
        from .stage_contracts import validate_input
        validate_input(job.payload,value)
    if value.candidate_id:
        from .models import DiscoveryMemory
        from sqlalchemy import select
        row=db.scalar(select(DiscoveryMemory).where(DiscoveryMemory.id==value.candidate_id,
            DiscoveryMemory.workspace_id==job.workspace_id,DiscoveryMemory.product_line_id==job.product_line_id,
            DiscoveryMemory.accepted_lead_id==job.lead_id,DiscoveryMemory.outcome=="ACCEPTED"))
        if not row:raise ContractViolation("ARTIFACT_SCOPE_MISMATCH")
    artifacts._line(db, value.workspace_id, value.product_line_id, value.context_version, value.context_hash)
    for ref in value.prior_artifacts:
        result = artifacts.consume_artifact(db, ref.artifact_id, value.workspace_id,
            value.product_line_id, value.context_version, value.context_hash)
        if content_hash(result) != ref.content_hash:
            raise ContractViolation("ARTIFACT_HASH_MISMATCH")
    artifacts._references(db, value, {})
    return value


def store_output(db, job, result):
    value = validate_task(db, job)
    if value is None:
        return result
    envelope = value.model_dump(mode="json")
    envelope["attempt"] = job.attempts
    if value.contract_name == "discovery.candidate":
        try:
            batch = DiscoveryBatch.model_validate_json(canonical_json(result)).model_dump(mode="json")
        except (ValueError, TypeError, OverflowError):
            raise ContractViolation("STAGE_PAYLOAD_INVALID") from None
        if type(result.get("human_review_required")) is not bool or batch["counts"]["candidates_ready"] != len(batch["candidates"]):
            raise ContractViolation("STAGE_PAYLOAD_INVALID")
        outputs = [("candidate:" + content_hash(item["domain"]), item) for item in (
            validate_payload(value.contract_name, value.schema_version, candidate) for candidate in batch["candidates"]
        )]
        if len({key for key, _ in outputs}) != len(outputs):
            raise ContractViolation("STAGE_PAYLOAD_INVALID")
    else:
        if value.contract_name == "content.output" and value.schema_version == 2:
            result = {**result, "asset_type": "EMAIL_TEXT" if result.get("channel") == "EMAIL" else "SOCIAL_TEXT"}
        key = "result" if job.output_generation == 0 else "result:"+str(job.output_generation)
        outputs = [(key, validate_payload(value.contract_name, value.schema_version, result))]
    for key, output in outputs:
        evidence = evidence_refs(output)
        strategies = {"worker": IMPLEMENTATION}
        if value.contract_name == "discovery.candidate":
            from .discovery_strategies import versions
            strategies.update(versions())
        artifacts.persist_artifact(db, job.id, job.lease_token, envelope, output, key, dict(
            evidence_refs=evidence, strategy_versions=strategies,
            input_hashes={"task_input": content_hash(job.payload)},
        ))
    # Preserve exact public/legacy result shape. Artifacts have their own schema.
    return result


def evidence_refs(value):
    refs={}
    def visit(node):
        if isinstance(node,dict):
            if isinstance(node.get("source_url"),str) and ("text" in node or "evidence_quote" in node):
                digest=content_hash(node.get("text",node.get("evidence_quote","")))
                refs[node["source_url"],digest]=dict(source_url=node["source_url"],content_hash=digest)
            for v in node.values():visit(v)
        elif isinstance(node,list):
            for v in node:visit(v)
    visit(value)
    return list(refs.values())[:50]


def event_read(row):
    failure = classify(row.error_code) if row.error_code else None
    return dict(id=row.id, event=row.event, stage=row.stage, pool=row.pool,
        actor_id=row.actor_id,
        product_line_id=row.product_line_id, attempt=row.attempt,
        schema_version=row.schema_version, trace_id=row.trace_id,
        error_code=row.error_code, error_category=failure.category if failure else None,
        duration_ms=row.duration_ms, created_at=row.created_at)
