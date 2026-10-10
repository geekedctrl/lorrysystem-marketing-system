from datetime import datetime
from typing import Literal, Annotated
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

BoundedText = Annotated[str, Field(min_length=1, max_length=2000)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Claim(StrictModel):
    text: str = Field(min_length=1, max_length=2000)
    source_ids: list[str] = Field(min_length=1, max_length=10)


class Channel(StrictModel):
    channel: Literal['EMAIL', 'LINKEDIN', 'FACEBOOK', 'INSTAGRAM']
    subject: str | None = Field(default=None, max_length=300)
    body: str = Field(min_length=1, max_length=5000)
    rationale: str = Field(min_length=1, max_length=2000)


class Asset(StrictModel):
    type: Literal['POSTER', 'BROCHURE', 'PROPOSAL']
    rationale: str = Field(min_length=1, max_length=2000)
    estimated_cost_usd: None = None
    cost_rationale: BoundedText = 'Unknown future provider price; no asset generation is authorized.'


class Strategy(StrictModel):
    objective: str = Field(min_length=1, max_length=2000)
    positioning: str = Field(min_length=1, max_length=2000)
    product_id: str
    claims: list[Claim] = Field(min_length=1, max_length=20)
    hypotheses: list[BoundedText] = Field(max_length=20)
    channels: list[Channel] = Field(max_length=4)
    assets: list[Asset] = Field(max_length=3)
    warnings: list[BoundedText] = Field(max_length=20)


class GenerateProposal(BaseModel):
    model_config = ConfigDict(extra='forbid')
    idempotency_key: UUID
    max_estimated_cost_usd: float = Field(default=0, ge=0, le=50, allow_inf_nan=False)


class EditProposal(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: int = Field(ge=1)
    strategy: Strategy


class ProposalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    lead_id: UUID
    research_id: UUID
    status: Literal['DRAFT', 'REVIEWED', 'REJECTED']
    version: int
    provider: str
    strategy: Strategy
    estimated_cost_usd: float
    actual_cost_usd: float
    created_at: datetime
    updated_at: datetime
    review_notes: str | None
    reviewed_by: str | None
    reviewed_at: datetime | None


class ReviewProposal(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: int = Field(ge=1)
    decision: Literal['REVIEWED', 'REJECTED']
    notes: str = Field(default='', max_length=2000)
