from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
)

from app.schemas.candidate import (
    CandidateRead,
    CandidateSourceRead,
)
from app.schemas.company import CompanyRead
from app.schemas.contact import ContactRead
from app.schemas.lead import LeadRead


ResearchStatus = Literal[
    "PENDING",
    "RUNNING",
    "COMPLETED",
    "PARTIAL",
    "FAILED",
]


ResearchSourceType = Literal[
    "WEBSITE",
    "NEWS",
    "SOCIAL",
    "DIRECTORY",
    "SEARCH",
    "OTHER",
]


class ResearchSummary(BaseModel):
    summary: str

    pain_points: list[str] = Field(
        default_factory=list
    )

    buying_signals: list[str] = Field(
        default_factory=list
    )

    company_facts: dict[str, Any] = Field(
        default_factory=dict
    )

    confidence: int = Field(
        ge=0,
        le=100,
    )

    model_provider: str | None = None
    model_name: str | None = None

    raw_output: (
        dict[str, Any]
        | list[Any]
        | None
    ) = None


class ResearchComplete(ResearchSummary):
    pass


class ResearchPartial(ResearchSummary):
    pass


class ResearchFail(BaseModel):
    reason: str = Field(
        min_length=1
    )


class ResearchSourceCreate(BaseModel):
    source_type: ResearchSourceType
    url: HttpUrl

    title: str | None = None
    evidence: str | None = None

    confidence: int | None = Field(
        default=None,
        ge=0,
        le=100,
    )

    observed_at: datetime | None = None


class ResearchSourceRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: UUID
    research_id: UUID

    source_type: str | None
    url: str

    title: str | None
    evidence: str | None
    confidence: int | None

    observed_at: datetime | None
    created_at: datetime


class ResearchRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: UUID
    lead_id: UUID

    research_status: ResearchStatus

    summary: str | None
    pain_points: list[Any]
    buying_signals: list[Any]
    company_facts: dict[str, Any]

    confidence: int | None

    model_provider: str | None
    model_name: str | None

    raw_output: (
        dict[str, Any]
        | list[Any]
        | None
    )

    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class ResearchDetail(ResearchRead):
    sources: list[ResearchSourceRead] = Field(
        default_factory=list
    )


class ResearchICPProfileRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: UUID
    code: str
    name: str
    description: str | None
    priority: int
    qualification_rules: dict[str, Any]
    active: bool
    created_at: datetime
    updated_at: datetime


class ResearchContext(BaseModel):
    research: ResearchRead
    lead: LeadRead
    company: CompanyRead

    primary_contact: ContactRead | None = None

    icp_profile: ResearchICPProfileRead

    accepted_candidate: CandidateRead | None = None

    candidate_sources: list[
        CandidateSourceRead
    ] = Field(
        default_factory=list
    )
