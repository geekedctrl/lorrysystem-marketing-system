"""Public response contracts. Provider secrets and worker ownership tokens stay private."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from .stages import Finding, Person, Citation, Criterion, ProductMatch

Role = Literal["ADMIN", "OPERATOR", "REVIEWER", "VIEWER"]
RunStatus = Literal[
    "PREPARING",
    "NEEDS_REVIEW",
    "PENDING_APPROVAL",
    "APPROVED",
    "REJECTED",
    "CHANGES_REQUESTED",
    "FAILED",
    "STALE",
]
JobStatus = Literal["PENDING", "RUNNING", "COMPLETED", "NEEDS_REVIEW", "FAILED"]
DecisionStatus = Literal["APPROVED", "REJECTED", "CHANGES_REQUESTED"]


class Public(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class LoginResponse(Public):
    token: str
    token_type: Literal["bearer"]


class Capabilities(Public):
    create_workspace: bool


class CurrentUser(Public):
    id: UUID
    email: str
    capabilities: Capabilities
    expires_at: datetime


class WorkspaceResponse(Public):
    id: UUID
    name: str
    role: Role


class WorkspaceCreated(Public):
    id: UUID
    name: str


class CatalogResponse(Public):
    id: UUID
    kind: Literal["PRODUCT", "ICP"]
    code: str
    name: str
    description: str
    rules: dict[str, Any]


class CatalogSaved(Public):
    id: UUID
    code: str


class CatalogState(CatalogResponse):
    active: bool
    version: int


class CatalogLifecycle(Public):
    id: UUID
    code: str
    active: bool


class LeadResponse(Public):
    id: UUID
    company_name: str
    website: str


class Profile(Public):
    url: str
    platform: str
    source_url: str
    evidence_quote: str
    basis: str


class ReviewedBy(Public):
    actor_id: UUID
    at: datetime


class ContactPerson(Person):
    profiles: list[Profile] = Field(default_factory=list)
    profile_candidates: list[Profile] = Field(default_factory=list)
    human_review: ReviewedBy | None = None


class Page(Public):
    source_url: str
    text: str
    unavailable: bool | None = None
    # Older stopped research results also retain bounded crawl links.
    links: list[str] | None = None


class Coverage(Public):
    pages_attempted: int
    unavailable_pages: int


class ResearchResult(Public):
    facts: list[Finding]
    people: list[Person]
    unknowns: list[str]
    pages: list[Page]
    industry: Finding | None = None
    coverage: Coverage | None = None
    stop_reason: str | None = None


class ContactResult(Public):
    people: list[ContactPerson]
    selected_contact: ContactPerson | None
    unavailable_queries: int
    stop_reason: str | None


class ScoreResult(Public):
    criteria: list[Criterion]
    unknowns: list[str]
    score: int
    relevance: int
    opportunity: int
    adjustments: list[str]
    stop_reason: str | None


class MatchResult(Public):
    matches: list[ProductMatch]
    selected_product: str | None
    stop_reason: str | None


class DraftResult(Public):
    subject: str
    body: str
    evidence: list[Citation]
    channel: Literal["EMAIL", "LINKEDIN"]
    recipient: str
    product_code: str
    status: Literal["PENDING_APPROVAL"]


class StageResults(Public):
    RESEARCH: ResearchResult | None = None
    CONTACT_SEARCH: ContactResult | None = None
    SCORING: ScoreResult | None = None
    MATCHING: MatchResult | None = None
    DRAFTING: DraftResult | None = None


class PreparationResponse(Public):
    id: UUID
    lead_id: UUID
    status: RunStatus
    stop_reason: str | None
    results: StageResults
    created_at: datetime


class PreparationHistory(PreparationResponse):
    current: bool


class PreparationStarted(Public):
    run_id: UUID


class PreparationContinued(PreparationStarted):
    status: RunStatus


class JobEvent(Public):
    model_config = ConfigDict(extra="allow")
    at: datetime


class JobResponse(Public):
    id: UUID
    workspace_id: UUID
    lead_id: UUID | None
    kind: Literal[
        "SETUP",
        "DISCOVERY",
        "RESEARCH",
        "CONTACT_SEARCH",
        "SCORING",
        "MATCHING",
        "DRAFTING",
    ]
    run_id: UUID | None
    managed: bool
    status: JobStatus
    attempts: int
    max_attempts: int
    result: dict[str, Any]
    failure_code: str | None
    history: list[JobEvent]
    created_at: datetime
    available_at: datetime
    lease_until: datetime | None


class JobQueued(Public):
    job_id: UUID
    status: JobStatus


class Enabled(Public):
    enabled: bool


class ApprovalInputs(Public):
    catalog: list[dict[str, Any]]
    preferences: dict[str, Any]
    company: dict[str, str]


class ApprovalSnapshot(Public):
    context_hash: str
    inputs: ApprovalInputs
    results: StageResults
    draft: DraftResult
    revision: dict[str, Any] | None = None


class ReviewDecision(Public):
    actor_id: UUID | None = None
    at: datetime | None = None
    note: str | None = None


class ApprovalResponse(Public):
    id: UUID
    run_id: UUID
    snapshot: ApprovalSnapshot
    status: Literal["PENDING", "APPROVED", "REJECTED", "CHANGES_REQUESTED"]
    decision: ReviewDecision
    created_at: datetime
    stale: bool
    version: int


class DecisionResponse(Public):
    status: DecisionStatus
    sent: Literal[False]


class ProviderHealth(Public):
    last_request_status: str
    at: datetime


class Usage(Public):
    provider: str
    operation: str
    status: str
    estimated_microusd: int
    usage: dict[str, Any]
    created_at: datetime


class Operations(Public):
    enabled: bool
    preferences: dict[str, Any]
    next_discovery_at: datetime | None
    stalled_jobs: list[UUID]
    delayed_pending_jobs: list[UUID]
    current_preparation: list[PreparationResponse]
    provider_health: dict[str, ProviderHealth]
    recent_provider_usage: list[Usage]
    cost_basis: str


class LeadDetail(LeadResponse):
    created_at: datetime
    current_preparation: PreparationResponse | None
    primary_contact: ContactPerson | None


class LeadPage(Public):
    items: list[LeadDetail]
    total: int
    limit: int
    next_cursor: str | None
    as_of: datetime


class RevisionResponse(Public):
    approval_id: UUID
    run_id: UUID
    version: int
    status: Literal["PENDING_APPROVAL"]
    sent: Literal[False]
