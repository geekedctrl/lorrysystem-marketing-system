from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.campaigns import CampaignProposal
from app.models.leads import Lead
from app.schemas.campaign import GenerateProposal, EditProposal, ProposalRead, ReviewProposal
from app.services.campaign_strategist import generate, edit, get_proposal, scoped, review

router = APIRouter(tags=['Campaign Strategist'])


@router.post('/api/leads/{lead_id}/campaign-proposals', response_model=ProposalRead)
def generate_proposal(lead_id: UUID, data: GenerateProposal, db: Session = Depends(get_db)):
    return generate(db, lead_id, data)


@router.get('/api/leads/{lead_id}/campaign-proposals', response_model=list[ProposalRead])
def list_proposals(lead_id: UUID, db: Session = Depends(get_db)):
    from fastapi import HTTPException
    if not db.scalar(scoped(db, Lead).where(Lead.id == lead_id)):
        raise HTTPException(404, 'Lead not found')
    return list(db.scalars(scoped(db, CampaignProposal).where(CampaignProposal.lead_id == lead_id).order_by(CampaignProposal.created_at.desc())))


@router.get('/api/campaign-proposals/{proposal_id}', response_model=ProposalRead)
def read_proposal(proposal_id: UUID, db: Session = Depends(get_db)):
    return get_proposal(db, proposal_id)


@router.patch('/api/campaign-proposals/{proposal_id}', response_model=ProposalRead)
def edit_proposal(proposal_id: UUID, data: EditProposal, db: Session = Depends(get_db)):
    return edit(db, proposal_id, data)


@router.post('/api/campaign-proposals/{proposal_id}/review', response_model=ProposalRead)
def review_proposal(proposal_id: UUID, data: ReviewProposal, db: Session = Depends(get_db)):
    return review(db, proposal_id, data)
