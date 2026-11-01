"""Preserve human contact resolutions as new immutable artifacts, never edits."""
from sqlalchemy import select
from fastapi import HTTPException
from .models import Membership, StageArtifact
from .stage_contracts import content_hash, validate_payload
from .worker_contracts import validate_task,evidence_refs
from .artifacts import append_event


def contact_resolution(db,job,run,actor_id,value):
    membership=db.get(Membership,(job.workspace_id,actor_id))
    if not membership or membership.role not in ("ADMIN","OPERATOR"):
        raise HTTPException(403,"Contact resolution permission required")
    if job.kind!="CONTACT_SEARCH" or run.status!="NEEDS_REVIEW" or run.stop_reason not in ("SUPPORTED_CONTACT_REQUIRED","CONTACT_SEARCH_UNAVAILABLE"):
        raise HTTPException(409,"Contact resolution is not pending")
    parsed=validate_task(db,job)
    if parsed is None:return
    value=validate_payload("contact.output",parsed.schema_version,value)
    digest=content_hash(value);key="result:human:"+digest
    if db.scalar(select(StageArtifact.id).where(StageArtifact.job_id==job.id,StageArtifact.artifact_key==key)):
        return
    header=parsed.model_dump(mode="json")
    header.update(actor_id=str(actor_id),producer_version="human.contact.1",attempt=job.attempts)
    row=StageArtifact(workspace_id=job.workspace_id,product_line_id=job.product_line_id,job_id=job.id,
        artifact_key=key,contract_name="contact.output",schema_version=parsed.schema_version,
        producer_version="human.contact.1",context_version=parsed.context_version,context_hash=parsed.context_hash,
        content_hash=digest,envelope=header,payload=value,evidence_refs=evidence_refs(value),
        strategy_versions={"contact_resolution":"human.contact.1"},
        input_hashes={"task_input":content_hash(job.payload),"human_decision":digest})
    db.add(row);db.flush()
    append_event(db,job.id,job.workspace_id,job.product_line_id,dict(event="HUMAN_RESOLUTION",pool="APPLICATION",
        stage="CONTACT_SEARCH",attempt=job.attempts,schema_version=parsed.schema_version,
        trace_id=str(job.trace_id),actor_id=str(actor_id)))
