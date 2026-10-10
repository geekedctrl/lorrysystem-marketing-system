"""PostgreSQL integration checks; run ONLY in the disposable CI workspace DB."""
import os
import sys
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if os.getenv('APP_ENV') not in ('workspace-test', 'ci'):
    raise SystemExit('Refusing integration writes outside workspace-test/ci')

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from app.db.session import ControlSession, SessionLocal
from app.models import Workspace, Company, Contact, Lead, LeadResearch, ResearchSource, Product, ICPProfile, ProductMatch, MarketingAction, ApprovalRequest, Event, CampaignProposal
from app.schemas.campaign import GenerateProposal, EditProposal, ReviewProposal, ProposalRead
from app.services.campaign_strategist import generate, get_proposal, edit, review
from app.workspace_context import Principal

passed = 0


def check(label, condition):
    global passed
    assert condition, label
    passed += 1
    print('PASS ' + label, flush=True)


def denied(label, code, operation):
    try:
        operation()
    except HTTPException as exc:
        check(label, exc.status_code == code)
    else:
        raise AssertionError(label)


suffix = str(uuid4())
with ControlSession() as control:
    a = Workspace(name='Synthetic strategist A', slug='strategy-a-' + suffix)
    b = Workspace(name='Synthetic strategist B', slug='strategy-b-' + suffix)
    control.add_all([a, b])
    control.commit()
    workspace_a, workspace_b = a.id, b.id


def session(workspace, role='ADMIN', human=True):
    principal = Principal(workspace, 'synthetic-reviewer', role, uuid4() if human else None)
    return SessionLocal(info={'workspace_id': workspace, 'principal': principal})


with session(workspace_a) as db:
    company = Company(name='Synthetic Fleet Company')
    product = Product(code='SYNTHETIC', name='Synthetic Fleet Product', active=True, description='Synthetic product catalogue description with factual capabilities. ' * 3)
    icp = ICPProfile(code='SYNTHETIC', name='Synthetic ICP')
    db.add_all([company, product, icp])
    db.flush()
    contact = Contact(company_id=company.id, full_name='Synthetic Contact', email='synthetic-' + suffix + '@example.test',
                      status='ACTIVE', source_url='https://example.test/fleet', updated_at=datetime.now(timezone.utc))
    db.add(contact)
    db.flush()
    lead = Lead(company_id=company.id, primary_contact_id=contact.id, icp_profile_id=icp.id, status='QUALIFIED', current_score=80)
    db.add(lead)
    db.flush()
    research = LeadResearch(lead_id=lead.id, research_status='COMPLETED', completed_at=datetime.now(timezone.utc),
                            summary='Synthetic fleet evidence', company_facts={})
    db.add(research)
    db.flush()
    source = ResearchSource(research_id=research.id, url='https://example.test/fleet', evidence='Synthetic company operates a fleet. Public contact: ' + contact.email,
                            observed_at=datetime.now(timezone.utc))
    db.add_all([source, ProductMatch(lead_id=lead.id, product_id=product.id, fit_score=80)])
    db.commit()
    lead_id, research_id, source_id, product_id = lead.id, research.id, source.id, product.id
    contact_id = contact.id
    request = GenerateProposal(idempotency_key=uuid4())
    proposal = generate(db, lead_id, request)
    proposal_id = proposal.id
    check('synthetic proposal persisted and serializable', ProposalRead.model_validate(proposal).status == 'DRAFT')
    check('mock zero charges', proposal.actual_cost_usd == 0 and proposal.provider == 'mock')
    check('sourced active contact supports email draft', [c['channel'] for c in proposal.strategy['channels']] == ['EMAIL'])
    check('conditional brochure estimate remains unknown', proposal.strategy['assets'][0]['type'] == 'BROCHURE' and proposal.strategy['assets'][0]['estimated_cost_usd'] is None)
    check('idempotent repeat returns original proposal', generate(db, lead_id, request).id == proposal_id)
    check('idempotency produces one record', db.scalar(select(func.count()).select_from(CampaignProposal)) == 1)
    denied('key cannot be reused for other lead', 409, lambda: generate(db, uuid4(), request))
    denied('stale optimistic edit version', 409, lambda: edit(db, proposal_id, EditProposal(expected_version=99, strategy=proposal.strategy)))
    reviewed = review(db, proposal_id, ReviewProposal(expected_version=1, decision='REVIEWED', notes='Synthetic review'))
    check('human strategy review persisted', reviewed.status == 'REVIEWED' and reviewed.version == 2)
    changed = edit(db, proposal_id, EditProposal(expected_version=2, strategy=reviewed.strategy))
    check('edits invalidate strategy review', changed.status == 'DRAFT' and changed.reviewed_at is None and changed.version == 3)
    rejected = review(db, proposal_id, ReviewProposal(expected_version=3, decision='REJECTED'))
    check('rejection persisted', rejected.status == 'REJECTED')
    check('no marketing action side effects', db.scalar(select(func.count()).select_from(MarketingAction)) == 0)
    check('no outbound approval side effects', db.scalar(select(func.count()).select_from(ApprovalRequest)) == 0)
    check('audited strategy lifecycle', db.scalar(select(func.count()).select_from(Event)) == 4)

with session(workspace_b) as db:
    denied('other tenant proposal hidden', 404, lambda: get_proposal(db, proposal_id))
    denied('other tenant lead hidden', 404, lambda: generate(db, lead_id, GenerateProposal(idempotency_key=uuid4())))
    check('database RLS hides proposals', db.scalar(select(func.count()).select_from(CampaignProposal)) == 0)

for role, human in [('SERVICE', False), ('VIEWER', True)]:
    with session(workspace_a, role, human) as db:
        denied(role + ' cannot generate', 403, lambda: generate(db, lead_id, GenerateProposal(idempotency_key=uuid4())))
        denied(role + ' cannot review', 403, lambda: review(db, proposal_id, ReviewProposal(expected_version=4, decision='REVIEWED')))
with session(workspace_a, 'OPERATOR') as db:
    denied('operator cannot review', 403, lambda: review(db, proposal_id, ReviewProposal(expected_version=4, decision='REVIEWED')))

with session(workspace_a) as db:
    contact = db.get(Contact, contact_id)
    original_email = contact.email
    contact.email = 'changed-' + suffix + '@example.test'
    db.commit()
    denied('changed contact invalidates review snapshot', 409, lambda: review(db, proposal_id, ReviewProposal(expected_version=4, decision='REVIEWED')))
    db.rollback()
    contact.email = original_email
    db.commit()
    match = db.scalar(select(ProductMatch).where(ProductMatch.lead_id == lead_id))
    match.fit_score = 75
    db.commit()
    denied('changed product match invalidates review snapshot', 409, lambda: review(db, proposal_id, ReviewProposal(expected_version=4, decision='REVIEWED')))
    db.rollback()
    match.fit_score = 80
    db.commit()
    source = db.get(ResearchSource, source_id)
    source.evidence = 'Synthetic updated evidence'
    db.commit()
    denied('changed source invalidates review snapshot', 409, lambda: review(db, proposal_id, ReviewProposal(expected_version=4, decision='REVIEWED')))
    db.rollback()
    research = db.get(LeadResearch, research_id)
    research.completed_at = datetime.now(timezone.utc) - timedelta(days=31)
    db.commit()
    denied('stale research blocks generation', 409, lambda: generate(db, lead_id, GenerateProposal(idempotency_key=uuid4())))

with ControlSession() as db:
    # Composite tenant constraints protect writes even when a privileged session bypasses RLS.
    invalid = CampaignProposal(workspace_id=workspace_b, lead_id=lead_id, research_id=research_id,
                               idempotency_key=uuid4(), strategy={}, context_hash='synthetic')
    db.add(invalid)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        check('composite relationship rejects cross-tenant write', True)
    else:
        raise AssertionError('Cross-tenant write was accepted')

print(f'{passed} campaign strategist integration checks passed')
