"""Share current raw public evidence within one workspace, never line decisions."""
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from .db import Session
from .models import CompanyEvidence, now
from .stage_contracts import content_hash

FETCH="guarded-pages.1"
EXTRACT="readable.1"


def lookup(job,url):
    if not job.lead_id:return None
    with Session() as db:
        row=db.scalar(select(CompanyEvidence).where(CompanyEvidence.workspace_id==job.workspace_id,
            CompanyEvidence.lead_id==job.lead_id,CompanyEvidence.input_hash==content_hash(url),
            CompanyEvidence.fetch_version==FETCH,CompanyEvidence.extract_version==EXTRACT,
            CompanyEvidence.created_at>=now()-timedelta(hours=24)).order_by(CompanyEvidence.created_at.desc()).limit(1))
        if row and content_hash(row.payload)==row.content_hash:return row.payload
    return None


def save(job,value):
    if not job.lead_id or value.get("unavailable"):return
    from .queue import owned
    with Session() as db:
        owned(db,job.id,job.lease_token)
        db.execute(insert(CompanyEvidence).values(id=uuid4(),workspace_id=job.workspace_id,lead_id=job.lead_id,
            source_url=value["source_url"],input_hash=content_hash(value["source_url"]),content_hash=content_hash(value),
            payload=value,fetch_version=FETCH,extract_version=EXTRACT,created_at=now()).on_conflict_do_nothing())
        db.commit()
