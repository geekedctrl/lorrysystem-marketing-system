import json
import os
import secrets
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select,text
from sqlalchemy.exc import IntegrityError

from app.auth import token_hash
from app.db.session import get_db
from app.models.discovery_runs import DiscoveryAutomation, DiscoveryRun
from app.workspace_context import current_principal

router = APIRouter(prefix='/api/discovery', tags=['Discovery'])
ACTIVE = ('QUEUED', 'RUNNING')


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class AutomationConfig(StrictModel):
    webhook_url: str = Field(max_length=2048)
    default_query: str = Field(min_length=3, max_length=300)
    enabled: bool = True

    @field_validator('webhook_url')
    @classmethod
    def webhook(cls, value):
        url = urlsplit(value)
        allowed = os.getenv('DISCOVERY_WEBHOOK_ALLOWED_HOSTS', 'n8n-dev.obsidian.cam').split(',')
        local_test = os.getenv('APP_ENV') in ('ci', 'workspace-test') and url.hostname == '127.0.0.1'
        if (url.scheme != 'https' and not (local_test and url.scheme == 'http')) or (
            url.hostname not in [host.strip() for host in allowed] and not local_test
        ) or url.username or url.password or url.query or url.fragment or not url.path.startswith('/webhook/'):
            raise ValueError('Use an HTTPS production webhook on an allowed n8n host')
        if any(char.isspace() for char in value) or (not local_test and url.port not in (None, 443)):
            raise ValueError('Invalid webhook URL')
        return value

    @field_validator('default_query')
    @classmethod
    def query(cls, value):
        if len(value.strip()) < 3:
            raise ValueError('Enter a discovery search')
        return value.strip()


class StartRun(StrictModel):
    query: str = Field(min_length=3, max_length=300)
    target_new_companies: int = Field(default=5, ge=1, le=10, strict=True)

    @field_validator('query')
    @classmethod
    def query(cls, value):
        return AutomationConfig.query(value)


class RunProof(StrictModel):
    run_token: str = Field(min_length=32, max_length=128)


class CompleteRun(RunProof):
    status: Literal['COMPLETED', 'FAILED']
    summary: dict[str, int] = Field(default_factory=dict)
    error_code: Literal['WORKFLOW_FAILED', 'SEARCH_FAILED', 'CANDIDATE_API_FAILED'] | None = None

    @field_validator('summary')
    @classmethod
    def counts(cls, value):
        allowed = {'search_results', 'websites_fetched', 'existing_skipped', 'new_candidates', 'existing_candidates', 'fetch_failures', 'model_failures'}
        if set(value) - allowed or any(type(n) is not int or not 0 <= n <= 1000 for n in value.values()):
            raise ValueError('Invalid discovery counters')
        return value


def require_role(*roles):
    principal = current_principal.get()
    if principal.role not in roles or (principal.role == 'SERVICE' and not principal.actor.startswith('service:')):
        raise HTTPException(403, 'Your workspace role does not allow this action')
    return principal


def expire_runs(db):
    now = datetime.now(timezone.utc)
    for run in db.scalars(select(DiscoveryRun).where(DiscoveryRun.status.in_(ACTIVE)).with_for_update()):
        limit = timedelta(minutes=5 if run.status == 'QUEUED' else 30)
        if now - (run.started_at or run.created_at) > limit:
            run.status, run.error_code, run.finished_at = 'TIMED_OUT', 'RUN_TIMED_OUT', now
    db.commit()


def run_read(run):
    return {key: getattr(run, key) for key in ('id', 'workspace_id', 'status', 'query', 'target_new_companies', 'summary', 'error_code', 'created_at', 'started_at', 'finished_at')}


@router.get('/config')
def config(db=Depends(get_db)):
    from app.models.automation import ProductAutomationPlan
    managed=db.scalar(select(ProductAutomationPlan))
    if managed:
        return {'configured':True,'enabled':managed.enabled and managed.state=='ACTIVE','managed':True,'default_query':managed.configuration.get('discovery_query','')}
    row = db.scalar(select(DiscoveryAutomation))
    result = {'configured': bool(row), 'enabled': bool(row and row.enabled), 'default_query': row.default_query if row else ''}
    if current_principal.get().role == 'ADMIN':
        result['webhook_url'] = row.webhook_url if row else ''
    return result


@router.put('/config')
def configure(data: AutomationConfig, db=Depends(get_db)):
    require_role('ADMIN')
    row = db.scalar(select(DiscoveryAutomation).with_for_update())
    if row is None:
        row = DiscoveryAutomation(**data.model_dump())
        db.add(row)
    else:
        for key, value in data.model_dump().items():
            setattr(row, key, value)
    db.commit()
    return config(db)


@router.get('/runs')
def runs(db=Depends(get_db)):
    from app.models.automation import AutomationJob,ProductAutomationPlan
    if db.scalar(select(ProductAutomationPlan.id)):
        return [{'id':j.id,'status':'QUEUED' if j.status=='PENDING' else j.status,'query':j.payload.get('query',''),
                 'target_new_companies':j.payload.get('target_new_companies',5),'summary':{**j.result,'new_candidates':j.result.get('accepted_leads',0)},
                 'error_code':j.failure_reason,'created_at':j.created_at,'started_at':j.started_at,'finished_at':j.finished_at}
                for j in db.scalars(select(AutomationJob).where(AutomationJob.kind=='DISCOVERY').order_by(AutomationJob.created_at.desc()).limit(10))]
    expire_runs(db)
    return [run_read(row) for row in db.scalars(select(DiscoveryRun).order_by(DiscoveryRun.created_at.desc()).limit(10))]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


@router.post('/runs', status_code=202)
def start(data: StartRun, db=Depends(get_db)):
    principal = require_role('ADMIN', 'OPERATOR')
    from app.models.automation import AutomationJob,ProductAutomationPlan
    from app.services.product_automation import schedule
    managed=db.scalar(select(ProductAutomationPlan))
    if managed:
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('shared-automation-claim',0))"))
        if not managed.enabled or managed.state!='ACTIVE':raise HTTPException(409,'Activate or resume this product before finding leads')
        if db.scalar(select(AutomationJob.id).where(AutomationJob.kind=='DISCOVERY',AutomationJob.status.in_(('PENDING','RUNNING')))):
            raise HTTPException(409,'Discovery is already running for this product')
        schedule(db,'DISCOVERY',payload={'query':data.query,'target_new_companies':data.target_new_companies})
        managed.next_discovery_at=datetime.now(timezone.utc)+timedelta(days=1)
        db.commit();return runs(db)[0]
    config = db.scalar(select(DiscoveryAutomation))
    if not config or not config.enabled:
        raise HTTPException(409, 'Lead discovery is not configured for this workspace. Ask an administrator to connect its workflow.')
    # Revalidate stored destinations if the host allowlist changes.
    try:
        AutomationConfig.webhook(config.webhook_url)
    except ValueError:
        raise HTTPException(409, 'The discovery workflow needs its connection updated.')
    expire_runs(db)
    if db.scalar(select(DiscoveryRun).where(DiscoveryRun.status.in_(ACTIVE))):
        raise HTTPException(409, 'Discovery is already running for this workspace.')
    proof = secrets.token_urlsafe(48)
    run = DiscoveryRun(query=data.query, target_new_companies=data.target_new_companies,
                       token_hash=token_hash(proof), requested_by=principal.actor)
    db.add(run)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Discovery is already running for this workspace.')
    destination = config.webhook_url
    payload = json.dumps({'workspace_id': str(principal.workspace_id), 'run_id': str(run.id), 'run_token': proof}).encode()
    # Release the read transaction before n8n claims this job in another request.
    db.commit()
    try:
        request = urllib.request.Request(destination, data=payload, method='POST',
            headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0 MarketingDiscovery/1.0'})
        with urllib.request.build_opener(NoRedirect).open(request, timeout=8) as response:
            if not 200 <= response.status < 300:
                raise OSError('Webhook rejected')
    except (OSError, urllib.error.URLError):
        db.refresh(run, with_for_update=True)
        if run.status == 'QUEUED':
            run.status, run.error_code, run.finished_at = 'FAILED', 'WORKFLOW_UNAVAILABLE', datetime.now(timezone.utc)
            db.commit()
        # If the workflow already claimed the job, a lost HTTP acknowledgement
        # must not overwrite its progress or encourage a duplicate run.
    db.refresh(run)
    return run_read(run)


def verified_run(db, run_id, proof):
    principal = require_role('SERVICE')
    run = db.scalar(select(DiscoveryRun).where(DiscoveryRun.id == run_id).with_for_update())
    if not run:
        raise HTTPException(404, 'Discovery run not found')
    if not secrets.compare_digest(run.token_hash, token_hash(proof)):
        raise HTTPException(403, 'Invalid run proof')
    return run, principal


@router.post('/runs/{run_id}/claim')
def claim(run_id: UUID, data: RunProof, db=Depends(get_db)):
    run, principal = verified_run(db, run_id, data.run_token)
    if run.status != 'QUEUED' or datetime.now(timezone.utc) - run.created_at > timedelta(minutes=5):
        raise HTTPException(409, 'This discovery run cannot be claimed')
    run.status, run.claimed_by, run.started_at = 'RUNNING', principal.actor, datetime.now(timezone.utc)
    db.commit()
    return {**run_read(run), 'max_results_scanned': 40, 'brave_count': 20, 'new_only': True}


@router.post('/runs/{run_id}/complete')
def complete(run_id: UUID, data: CompleteRun, db=Depends(get_db)):
    run, principal = verified_run(db, run_id, data.run_token)
    if run.claimed_by != principal.actor:
        raise HTTPException(403, 'Only the worker that claimed this run can complete it')
    if run.status in ('COMPLETED', 'FAILED'):
        return run_read(run)
    if run.status != 'RUNNING':
        raise HTTPException(409, 'This discovery run is no longer active')
    run.status, run.summary, run.error_code = data.status, data.summary, data.error_code
    run.finished_at = datetime.now(timezone.utc)
    db.commit()
    return run_read(run)
