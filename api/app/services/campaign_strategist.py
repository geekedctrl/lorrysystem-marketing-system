"""Deterministic mock strategist. Research excerpts are data, never instructions.

Only verbatim cited evidence is accepted as a supported company claim. Free-form
strategy and copy remain human-reviewed suggestions, never verified company facts.
No provider, marketing action, approval or delivery side effects exist here.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import hashlib
import json
import re
from urllib.parse import urlsplit
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models.campaigns import CampaignProposal
from app.models.catalog import Product
from app.models.companies import Company, Contact
from app.models.leads import Lead, LeadResearch, ProductMatch, ResearchSource
from app.models.marketing import Event
from app.schemas.campaign import Strategy


def scoped(db, model):
    return select(model).where(model.workspace_id == db.info['workspace_id'])


def require_editor(db):
    principal = db.info.get('principal')
    if not principal or not principal.user_id or principal.role not in {'ADMIN', 'OPERATOR', 'REVIEWER'}:
        raise HTTPException(403, 'Campaign proposals require a signed-in workspace editor')


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def context_hash(lead, research, sources, product, company, contact=None, match=None):
    payload = {
        'lead': [str(lead.id), str(lead.primary_contact_id), lead.status, lead.current_score],
        'research': [str(research.id), str(research.completed_at), research.summary, research.company_facts],
        'sources': sorted([(str(s.id), s.url, s.evidence, str(s.observed_at)) for s in sources]),
        'product': [str(product.id), product.name, product.description, str(product.updated_at)],
        'company': [str(company.id), company.name],
        'contact': None if not contact else [str(contact.id), contact.full_name, contact.email, contact.linkedin_url,
            contact.source_url, contact.status, str(contact.updated_at)],
        'match': None if not match else [str(match.id), str(match.product_id), match.fit_score, match.rationale, str(match.updated_at)],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def ensure_snapshot(proposal, values):
    if proposal.context_hash != context_hash(*values):
        raise HTTPException(409, 'Research, product, contact or match context changed; generate a fresh proposal')


def check_context(lead, research, sources, product, now=None):
    now = now or datetime.now(timezone.utc)
    if lead.status not in {'QUALIFIED', 'READY_FOR_OUTREACH'} or (lead.current_score or 0) < 60:
        raise HTTPException(409, 'A qualified lead with score at least 60 is required')
    completed = aware(research.completed_at or research.researched_at) if research else None
    if not research or research.research_status != 'COMPLETED' or not completed or completed > now or completed < now - timedelta(days=30):
        raise HTTPException(409, 'Completed research within the last 30 days is required')
    if not sources:
        raise HTTPException(409, 'Research requires cited evidence')
    if not product or not product.active:
        raise HTTPException(409, 'An active matched product is required')


def context(db, lead_id, research_id=None):
    lead = db.scalar(scoped(db, Lead).where(Lead.id == lead_id))
    if not lead:
        raise HTTPException(404, 'Lead not found')
    query = scoped(db, LeadResearch).where(LeadResearch.lead_id == lead.id)
    if research_id:
        query = query.where(LeadResearch.id == research_id)
    research = db.scalar(query.order_by(LeadResearch.created_at.desc()).limit(1))
    sources = [] if not research else list(db.scalars(scoped(db, ResearchSource).where(ResearchSource.research_id == research.id)))
    now = datetime.now(timezone.utc)
    sources = [s for s in sources if s.evidence and s.url.startswith(('https://', 'http://'))
               and aware(s.observed_at or s.created_at) and now - timedelta(days=30) <= aware(s.observed_at or s.created_at) <= now]
    match = db.scalar(scoped(db, ProductMatch).where(ProductMatch.lead_id == lead.id).order_by(ProductMatch.fit_score.desc()).limit(1))
    product = db.scalar(scoped(db, Product).where(Product.id == match.product_id)) if match else None
    check_context(lead, research, sources, product, now)
    company = db.scalar(scoped(db, Company).where(Company.id == lead.company_id))
    if not company:
        raise HTTPException(409, 'Company is unavailable')
    contact = db.scalar(scoped(db, Contact).where(Contact.id == lead.primary_contact_id, Contact.company_id == company.id)) if lead.primary_contact_id else None
    return lead, research, sources, product, company, contact, match


def validate_strategy(payload, sources, product, budget=0, contact=None):
    try:
        strategy = Strategy.model_validate(payload)
    except ValueError as exc:
        raise HTTPException(422, 'Malformed structured strategy') from exc
    if strategy.product_id != str(product.id):
        raise HTTPException(422, 'Strategy must use the selected matched product')
    evidence = {str(source.id): source.evidence for source in sources}
    for claim in strategy.claims:
        if any(source_id not in evidence for source_id in claim.source_ids):
            raise HTTPException(422, 'Unknown or cross-context citation')
        if not any(claim.text == evidence[source_id][:2000] for source_id in claim.source_ids):
            raise HTTPException(422, 'Supported claims must quote cited evidence exactly')
    if len({channel.channel for channel in strategy.channels}) != len(strategy.channels):
        raise HTTPException(422, 'Duplicate campaign channels')
    allowed_channels = {c['channel'] for c in mock_strategy(sources, product, contact=contact)['channels']}
    if any(channel.channel not in allowed_channels for channel in strategy.channels):
        raise HTTPException(422, 'Channel requires current sourced contact or social evidence')
    # Only the deterministic mock executes here, at zero cost. Recommended
    # assets are unpriced and never scheduled, reserved or generated.
    if 0 > budget:
        raise HTTPException(409, 'Campaign generation budget exceeded')
    return strategy.model_dump()


def host_is(url, domain):
    try:
        parsed = urlsplit(url or '')
        host = (parsed.hostname or '').lower()
        return parsed.scheme in {'http', 'https'} and (host == domain or host.endswith('.' + domain))
    except ValueError:
        return False


def contact_is_current(contact, sources, now):
    if not contact or contact.status != 'ACTIVE' or not contact.source_url:
        return False
    updated = aware(contact.updated_at)
    return bool(updated and now - timedelta(days=30) <= updated <= now
                and contact.source_url in {s.url for s in sources})


def mock_strategy(sources, product, contact=None, company=None, match=None, now=None):
    now = now or datetime.now(timezone.utc)
    channels, assets = [], []
    warnings = ['Mock inference: all strategy and copy are suggestions requiring human review.',
                'Company need, budget and buying intent are unverified.',
                'No outbound message or asset has been approved or generated.']
    fresh_contact = contact_is_current(contact, sources, now)
    contact_sources = [] if not fresh_contact else [s for s in sources if s.url == contact.source_url]
    sourced_email = bool(fresh_contact and contact.email and any(
        re.search(r'(?<![\w.+-])' + re.escape(contact.email) + r'(?![\w.-])', s.evidence, flags=re.IGNORECASE)
        for s in contact_sources))
    if sourced_email and re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', contact.email):
        channels.append({'channel': 'EMAIL', 'subject': 'An introduction and a question',
                         'body': f'Hello, would an introduction to {product.name} be useful? We would welcome a conversation to understand whether it is relevant to your team.',
                         'rationale': 'The active primary contact has a current, research-sourced email. Recipient review and separate message approval are required before any send.'})
    sourced_profile = bool(fresh_contact and contact.linkedin_url and any(
        s.url == contact.linkedin_url or contact.linkedin_url in s.evidence for s in contact_sources))
    if sourced_profile and host_is(contact.linkedin_url, 'linkedin.com'):
        channels.append({'channel': 'LINKEDIN', 'subject': None,
                         'body': f'Would a conversation about {product.name} be relevant to your team?',
                         'rationale': 'A current sourced primary-contact LinkedIn profile supports a draft introduction; no connection or publishing action is authorized.'})
    for domain, channel in [('facebook.com', 'FACEBOOK'), ('instagram.com', 'INSTAGRAM')]:
        if any(host_is(s.url, domain) for s in sources):
            channels.append({'channel': channel, 'subject': None,
                             'body': f'Explore {product.name}. Contact our team to discuss whether it fits your requirements.',
                             'rationale': 'A current research source identifies this social channel. Prospect affiliation and channel suitability are hypotheses requiring review; this general awareness draft does not infer a company problem or permission to publish.'})
    if not channels:
        warnings.append('No current sourced contact or social channel is available. Review contact evidence before choosing an engagement channel.')
    if product.description and len(product.description.strip()) >= 80 and match and match.fit_score >= 70:
        assets.append({'type': 'BROCHURE', 'rationale': 'The product catalogue has enough detail for a factual product overview and the matched fit supports reviewing it; do not assert prospect need.',
                       'estimated_cost_usd': None,
                       'cost_rationale': 'Future brochure assembly and illustration costs are unknown. Pricing and a separate budget authorization are required before generation.'})
    if any(c['channel'] in {'FACEBOOK', 'INSTAGRAM'} for c in channels) and product.description:
        assets.append({'type': 'POSTER', 'rationale': 'A cited social presence supports considering a general product-awareness visual; publishing still requires separate approval.',
                       'estimated_cost_usd': None,
                       'cost_rationale': 'Live image-provider pricing is unknown and no paid generation is authorized.'})
    return {
        'objective': f"Explore whether {product.name} is relevant to {company.name if company else 'this prospect'} in a human-reviewed introductory conversation.",
        'positioning': f"Introduce the catalogue product {product.name} to {company.name if company else 'this prospect'}; use the cited facts as background and confirm requirements before making need or benefit claims.",
        'product_id': str(product.id),
        'claims': [{'text': s.evidence[:2000], 'source_ids': [str(s.id)]} for s in sources[:3]],
        'hypotheses': ['Product fit is a hypothesis. Company need, budget and buying intent remain unverified.'] +
                      [f"{channel['channel']} account affiliation and engagement suitability are hypotheses requiring human review."
                       for channel in channels if channel['channel'] in {'FACEBOOK', 'INSTAGRAM'}],
        'channels': channels,
        'assets': assets,
        'warnings': warnings,
    }


def get_proposal(db, proposal_id, lock=False):
    query = scoped(db, CampaignProposal).where(CampaignProposal.id == proposal_id)
    if lock:
        query = query.with_for_update()
    proposal = db.scalar(query)
    if not proposal:
        raise HTTPException(404, 'Campaign proposal not found')
    return proposal


def generate(db, lead_id, data):
    require_editor(db)
    previous = db.scalar(scoped(db, CampaignProposal).where(CampaignProposal.idempotency_key == data.idempotency_key))
    if previous:
        if previous.lead_id != lead_id:
            raise HTTPException(409, 'Idempotency key already belongs to another lead')
        return previous
    values = context(db, lead_id)
    lead, research, sources, product, company, contact, match = values
    strategy = validate_strategy(mock_strategy(sources, product, contact, company, match), sources, product, data.max_estimated_cost_usd, contact)
    proposal = CampaignProposal(id=uuid4(), lead_id=lead.id, research_id=research.id,
                                idempotency_key=data.idempotency_key, strategy=strategy,
                                context_hash=context_hash(*values))
    db.add(proposal)
    db.add(Event(event_type='CAMPAIGN_PROPOSAL_CREATED', entity_type='campaign_proposal', entity_id=proposal.id,
                 metadata_json={'lead_id': str(lead.id), 'provider': 'mock', 'estimated_cost_usd': 0, 'actual_cost_usd': 0}))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        previous = db.scalar(scoped(db, CampaignProposal).where(CampaignProposal.idempotency_key == data.idempotency_key))
        if not previous or previous.lead_id != lead_id:
            raise HTTPException(409, 'Proposal generation conflicted; use a new idempotency key')
        return previous
    db.refresh(proposal)
    return proposal


def edit(db, proposal_id, data):
    require_editor(db)
    proposal = get_proposal(db, proposal_id, lock=True)
    if proposal.version != data.expected_version:
        raise HTTPException(409, 'Proposal changed; reload before saving')
    values = context(db, proposal.lead_id, proposal.research_id)
    lead, research, sources, product, company, contact, match = values
    ensure_snapshot(proposal, values)
    proposal.strategy = validate_strategy(data.strategy.model_dump(), sources, product, contact=contact)
    proposal.version += 1
    proposal.status = 'DRAFT'
    proposal.review_notes = None
    proposal.reviewed_by = None
    proposal.reviewed_at = None
    proposal.updated_at = datetime.now(timezone.utc)
    db.add(Event(event_type='CAMPAIGN_PROPOSAL_EDITED', entity_type='campaign_proposal', entity_id=proposal.id,
                 metadata_json={'version': proposal.version}))
    db.commit()
    db.refresh(proposal)
    return proposal


def review(db, proposal_id, data):
    principal = db.info.get('principal')
    if not principal or not principal.user_id or principal.role not in {'ADMIN', 'REVIEWER'}:
        raise HTTPException(403, 'Strategy review requires a signed-in reviewer')
    proposal = get_proposal(db, proposal_id, lock=True)
    if proposal.version != data.expected_version:
        raise HTTPException(409, 'Proposal changed; reload before reviewing')
    values = context(db, proposal.lead_id, proposal.research_id)
    lead, research, sources, product, company, contact, match = values
    ensure_snapshot(proposal, values)
    latest = db.scalar(scoped(db, LeadResearch).where(LeadResearch.lead_id == lead.id).order_by(LeadResearch.created_at.desc()).limit(1))
    if latest.id != research.id:
        raise HTTPException(409, 'Research changed; generate a fresh proposal before review')
    validate_strategy(proposal.strategy, sources, product, contact=contact)
    proposal.status = data.decision
    proposal.review_notes = data.notes
    proposal.reviewed_by = principal.actor
    proposal.reviewed_at = datetime.now(timezone.utc)
    proposal.updated_at = proposal.reviewed_at
    proposal.version += 1
    db.add(Event(event_type='CAMPAIGN_PROPOSAL_REVIEWED', entity_type='campaign_proposal', entity_id=proposal.id,
                 metadata_json={'version': proposal.version, 'decision': data.decision, 'outbound_approved': False}))
    db.commit()
    db.refresh(proposal)
    return proposal
