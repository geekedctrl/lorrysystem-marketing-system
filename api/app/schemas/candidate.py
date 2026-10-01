from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.lead import LeadPriority


CandidateStatus = Literal[
    "NEW",
    "READY_FOR_REVIEW",
    "NEEDS_REVIEW",
    "ACCEPTED",
    "REJECTED",
    "DUPLICATE",
    "FAILED",
]

CandidateSourceType = Literal[
    "SEARCH_RESULT",
    "COMPANY_WEBSITE",
    "PUBLIC_DIRECTORY",
    "NEWS",
    "RSS",
    "PUBLIC_PAGE",
]

CandidateCreateOutcome = Literal[
    "NEW_CANDIDATE",
    "EXISTING_COMPANY",
    "EXISTING_ACTIVE_LEAD",
    "EXISTING_CANDIDATE",
]

CandidateAcceptOutcome = Literal[
    "ACCEPTED",
    "DUPLICATE",
]


class CandidateSourceCreate(BaseModel):
    source_type: CandidateSourceType
    url: str = Field(min_length=1)
    title: str | None = None
    source_query: str | None = None
    summary: str | None = None
    evidence: str | None = None
    published_at: datetime | None = None
    discovered_at: datetime | None = None


class CandidateCreate(BaseModel):
    company_name: str = Field(min_length=1)
    website_url: str | None = None
    domain: str | None = None
    industry: str | None = None

    country_code: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
    )

    state: str | None = None
    city: str | None = None

    contact_name: str | None = None
    job_title: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None

    suggested_icp_profile_id: UUID

    icp_confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    icp_reasoning: str = Field(min_length=1)

    fleet_clues: list[str] = Field(default_factory=list)
    buying_signals: list[str] = Field(default_factory=list)
    source_summary: str | None = None

    # Every candidate must start with actual public-page evidence.
    # A search-result snippet alone cannot create a candidate.
    source: CandidateSourceCreate

    @model_validator(mode="after")
    def reject_search_snippet_only(self):
        if self.source.source_type == "SEARCH_RESULT":
            raise ValueError(
                "Initial candidate source cannot be SEARCH_RESULT. "
                "Fetch and inspect the public page first."
            )
        return self


class CandidateUpdate(BaseModel):
    company_name: str | None = Field(default=None, min_length=1)
    website_url: str | None = None
    domain: str | None = None
    industry: str | None = None

    country_code: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
    )

    state: str | None = None
    city: str | None = None

    contact_name: str | None = None
    job_title: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None

    suggested_icp_profile_id: UUID | None = None

    icp_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    icp_reasoning: str | None = Field(
        default=None,
        min_length=1,
    )

    fleet_clues: list[str] | None = None
    buying_signals: list[str] | None = None
    source_summary: str | None = None
    failure_reason: str | None = None


class CandidateSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    source_type: str
    url: str
    title: str | None
    source_query: str | None
    summary: str | None
    evidence: str | None
    published_at: datetime | None
    discovered_at: datetime
    created_at: datetime


class CandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    company_name: str
    normalized_name: str
    website_url: str | None
    normalized_website: str | None
    domain: str | None
    industry: str | None
    country_code: str | None
    state: str | None
    city: str | None

    contact_name: str | None
    job_title: str | None
    email: str | None
    phone: str | None
    linkedin_url: str | None

    suggested_icp_profile_id: UUID
    icp_confidence: float
    icp_reasoning: str

    fleet_clues: list
    buying_signals: list
    source_summary: str | None

    existing_company_id: UUID | None
    accepted_lead_id: UUID | None
    duplicate_lead_id: UUID | None

    failure_reason: str | None
    review_notes: str | None
    reviewed_at: datetime | None
    reviewed_by: str | None

    created_at: datetime
    updated_at: datetime


class CandidateDetail(CandidateRead):
    sources: list[CandidateSourceRead] = Field(default_factory=list)


class CandidateCreateResult(BaseModel):
    outcome: CandidateCreateOutcome
    candidate: CandidateRead | None = None
    existing_company_id: UUID | None = None
    existing_lead_id: UUID | None = None


class CandidateAccept(BaseModel):
    reviewed_by: str = Field(min_length=1)
    priority: LeadPriority = "MEDIUM"

    # Optional human override; otherwise use suggested ICP.
    icp_profile_id: UUID | None = None
    review_notes: str | None = None


class CandidateReject(BaseModel):
    reviewed_by: str = Field(min_length=1)
    review_notes: str | None = None


class CandidateAcceptResult(BaseModel):
    outcome: CandidateAcceptOutcome
    candidate: CandidateRead
    lead_id: UUID
