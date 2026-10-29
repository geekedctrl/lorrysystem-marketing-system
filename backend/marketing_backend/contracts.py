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
JobStatus = Literal["PENDING", "RUNNING", "COMPLETED", "NEEDS_REVIEW", "FAILED", "QUARANTINED"]
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
    organization_id: UUID


class WorkspaceCreated(Public):
    id: UUID
    name: str


class OrganizationResponse(Public):
    id: UUID
    name: str
    role: Literal["OWNER", "ADMIN", "MEMBER"]


class OrganizationName(Public):
    id: UUID
    name: str


class OrganizationMember(Public):
    user_id: UUID
    email: str
    role: Literal["OWNER", "ADMIN", "MEMBER"]


class OrganizationWorkspace(Public):
    id: UUID
    name: str
    description: str
    active: bool
    role: Role | None


class NewWorkspace(Public):
    id: UUID
    name: str
    organization_id: UUID
    replayed: bool


class WorkspaceProfile(Public):
    id: UUID
    organization_id: UUID
    name: str
    description: str
    active: bool
    role: Role


class WorkspaceMember(Public):
    user_id: UUID
    email: str
    role: Role


class MemberRole(Public):
    user_id: UUID
    role: str


class InvitationCreated(Public):
    id: UUID
    token: str
    expires_at: datetime


class InvitationAccepted(Public):
    accepted: bool
    organization_id: UUID
    workspace_id: UUID | None


class AccountSession(Public):
    current: bool
    expires_at: datetime


class SenderStatus(Public):
    id: UUID
    name: str
    status: Literal["disabled", "verified", "unverified"]


class ProviderDraftStatus(Public):
    kind: Literal["MODEL", "SEARCH"]
    status: Literal["unverified"]
    settings: dict[str, str]
    secret_present: bool


class ConnectionStatus(Public):
    automation: Literal["disabled", "configured"]
    model: Literal["configured", "unverified", "unavailable"]
    search: Literal["configured", "unverified", "unavailable"]
    senders: list[SenderStatus]
    provider_drafts: list[ProviderDraftStatus]


class WorkspaceStatus(Public):
    id: UUID
    active: bool


class DiscoveryBatchSize(Public):
    batch_size: int


class CatalogResponse(Public):
    product_line_id: UUID | None = None
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


class DiscoveryCandidate(Public):
    product_line_id: UUID | None = None
    id: UUID
    domain: str
    status: str
    company_name: str | None = None
    website: str | None = None
    industry: str | None = None
    prospect_type: str | None = None
    confidence: int | None = None
    icp_code: str | None = None
    reasoning: str | None = None
    source_url: str | None = None
    evidence_quote: str | None = None
    unknowns: list[str] = Field(default_factory=list)
    failure_reason: str | None = None
    source_job_id: UUID | None
    accepted_lead_id: UUID | None
    reviewed_at: datetime | None
    review_note: str | None
    retry_after: datetime | None
    stale: bool
    created_at: datetime


class DiscoveryPage(Public):
    items: list[DiscoveryCandidate]
    total: int
    offset: int
    limit: int


class CandidateAccepted(Public):
    candidate_id: UUID
    lead_id: UUID
    run_id: UUID
    status: Literal["ACCEPTED"]


class CandidateReviewed(Public):
    candidate_id: UUID
    status: Literal["REJECTED", "RETRY_PENDING"]
    job_id: UUID | None = None


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
    asset_type: Literal["EMAIL_TEXT", "SOCIAL_TEXT"] | None = None
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
    product_line_id: UUID | None = None
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
    product_line_id: UUID
    trace_id: UUID
    pool: Literal["LEGACY"]
    contract_mode: Literal["LEGACY", "VERSIONED"]
    contract_name: str | None
    schema_version: int
    quarantine_reason: str | None
    replay_generation: int
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


class WorkerEventResponse(Public):
    id: UUID
    event: Literal["CLAIM", "CHECKPOINT", "RETRY", "COMPLETION", "FAILURE", "LEASE_LOSS", "QUARANTINE", "REPLAY", "HUMAN_RESOLUTION"]
    actor_id: UUID | None = None
    stage: str
    pool: str
    product_line_id: UUID
    attempt: int
    schema_version: int
    trace_id: UUID
    error_code: str | None
    error_category: str | None
    duration_ms: int | None
    created_at: datetime


class ReplayResponse(Public):
    replay_id: UUID
    job_id: UUID
    generation: int
    already_recorded: bool
    created_at: datetime


class Enabled(Public):
    enabled: bool


class LineContext(Public):
    id: UUID
    version: int
    context_hash: str


class ApprovalInputs(Public):
    product_line: LineContext | None = None
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
    ownership: list[dict[str, Any]] = []
    migration_status: dict[str, Any] | None = None
    active_leases: int = 0
    active_send_leases: int = 0


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
