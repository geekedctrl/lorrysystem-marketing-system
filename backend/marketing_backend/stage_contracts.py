"""Worker boundary contracts. These models never import providers or the database.

Versions 1 and 2 are the first explicitly versioned contracts, not labels applied
to historical JSON results. V2 adds optional upstream artifact references. No
version conversion, provider checkpoint forwarding, or evidence acceptance occurs
here: source validation and human candidate acceptance remain separate gates.
"""

import hashlib
import json
from typing import Annotated, Literal
from uuid import UUID
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, JsonValue, field_validator, model_validator

CURRENT_VERSION = 2
SUPPORTED_VERSIONS = (1, 2)
Stage = Literal["SETUP", "DISCOVERY", "RESEARCH", "CONTACT_SEARCH", "SCORING", "MATCHING", "DRAFTING"]
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Code = Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.:-]+$")]
Note = Annotated[str, Field(max_length=2000)]


class ContractViolation(Exception):
    """Safe to log: never retain Pydantic errors or the offending payload."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class ArtifactReference(Strict):
    artifact_id: UUID
    contract_name: Code
    schema_version: int = Field(ge=1, le=2)
    content_hash: Hash


class TaskEnvelope(Strict):
    workspace_id: UUID
    product_line_id: UUID
    job_id: UUID
    company_id: UUID | None = None
    lead_id: UUID | None = None
    candidate_id: UUID | None = None
    stage: Stage
    idempotency_key: str = Field(min_length=1, max_length=120)
    trace_id: UUID
    contract_name: Code
    schema_version: int = Field(ge=1)
    producer_version: Code
    input_hash: Hash | None = None
    actor_id: UUID | None = None
    context_version: int = Field(ge=1)
    context_hash: Hash
    attempt: int = Field(ge=0, le=5)
    max_attempts: int = Field(ge=1, le=5)
    prior_artifacts: list[ArtifactReference] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def consistent(self):
        if self.attempt > self.max_attempts:
            raise ValueError("attempt exceeds retry budget")
        if self.stage not in ("SETUP", "DISCOVERY") and not (self.lead_id or self.company_id):
            raise ValueError("lead-level task needs an identity")
        ids = [a.artifact_id for a in self.prior_artifacts]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate artifact reference")
        expected = {name: stage for stage, name in STAGE_CONTRACTS.items()}
        if self.contract_name in expected and self.stage != expected[self.contract_name]:
            raise ValueError("contract does not match stage")
        return self


class CatalogContext(Strict):
    kind: Literal["PRODUCT","ICP"]
    code: str = Field(min_length=1,max_length=80)
    name: str = Field(min_length=2,max_length=120)
    description: str = Field(max_length=5000)
    rules: dict[str,JsonValue]
    version: int = Field(ge=1)


class CompanyContext(Strict):
    id: UUID
    company_name: str = Field(min_length=2,max_length=200)
    website: str = Field(min_length=8,max_length=1500)


class LineContext(Strict):
    id: UUID
    version: int = Field(ge=1)
    context_hash: Hash


class InputContext(Strict):
    catalog: list[CatalogContext] = Field(max_length=1000)
    # Policy extensions are a declared JSON bag; API settings/rubrics have their
    # own strict domain validation. Unknown task/context fields are forbidden.
    preferences: dict[str,JsonValue] = Field(max_length=50)
    product_line: LineContext
    company: CompanyContext | None = None


class StageInput(Strict):
    product_line_id: UUID
    context: InputContext
    context_hash: Hash
    company_name: str | None = Field(default=None,max_length=200)
    website: str | None = Field(default=None,max_length=1500)
    icp_code: str | None = Field(default=None,max_length=80)
    retry_domain: str | None = Field(default=None,max_length=254)
    retry_url: str | None = Field(default=None,max_length=1500)
    source_candidate_id: UUID | None = None


def validate_input(value, envelope):
    try:
        parsed=StageInput.model_validate_json(canonical_json(value))
        if (parsed.product_line_id!=envelope.product_line_id or parsed.context.product_line.id!=envelope.product_line_id
            or parsed.context.product_line.version!=envelope.context_version
            or parsed.context.product_line.context_hash!=envelope.context_hash
            or parsed.context_hash!=hashlib.sha256(json.dumps(value["context"],sort_keys=True,separators=(",",":")).encode()).hexdigest()):
            raise ValueError("input context mismatch")
        if envelope.stage not in ("SETUP","DISCOVERY"):
            company=parsed.context.company
            if (not company or company.id!=envelope.lead_id or company.company_name!=parsed.company_name
                or company.website!=parsed.website or parsed.icp_code not in {c.code for c in parsed.context.catalog if c.kind=="ICP"}):
                raise ValueError("invalid lead-stage input")
        return parsed
    except (ValidationError,ValueError,TypeError,KeyError,OverflowError):
        raise ContractViolation("TASK_INPUT_INVALID") from None


class Citation(Strict):
    source_url: str = Field(min_length=8, max_length=1500)
    evidence_quote: str = Field(min_length=8, max_length=12000)

    @model_validator(mode="after")
    def url_shape(self):
        value = urlsplit(self.source_url)
        if value.scheme not in ("http", "https") or not value.hostname or value.username or value.password:
            raise ValueError("invalid evidence URL")
        return self


class DiscoveryCandidateV1(Citation):
    suitable: Literal[True]
    prospect_type: Literal["FLEET_OPERATOR", "LOGISTICS_PROVIDER", "TRANSPORT_BUYER", "PRODUCT_BUYER"]
    company_name: str = Field(min_length=2, max_length=200)
    icp_code: str = Field(min_length=1, max_length=80)
    # The uploaded implementation's assess() gate is 50. Do not change policy
    # to the older documentation's 75 while introducing transport contracts.
    confidence: int = Field(ge=50, le=100)
    official_company: Literal[True]
    excerpt_id: str = Field(max_length=30)
    industry: str = Field(min_length=2, max_length=150)
    reasoning: str = Field(min_length=15, max_length=1500)
    unknowns: list[Note] = Field(max_length=10)
    website: str = Field(min_length=8, max_length=1500)
    domain: str = Field(min_length=1, max_length=254)

    @field_validator("suitable", "official_company", mode="before")
    @classmethod
    def exact_true(cls, value):
        if value is not True:
            raise ValueError("literal boolean true required")
        return value

    @model_validator(mode="after")
    def identity(self):
        website = urlsplit(self.website)
        if website.scheme not in ("http", "https") or website.username or website.password:
            raise ValueError("invalid company URL")
        hosts = [(urlsplit(u).hostname or "").lower().rstrip(".").removeprefix("www.")
                 for u in (self.website, self.source_url)]
        if not all(h == self.domain for h in hosts):
            raise ValueError("company/evidence domain mismatch")
        return self


class DiscoveryCandidateV2(DiscoveryCandidateV1):
    source_artifact_ids: list[UUID] = Field(default_factory=list, max_length=20)


class Finding(Citation):
    category: Literal["COMPANY", "INDUSTRY", "SERVICES", "FLEET", "TECHNOLOGY", "LOCATION", "PAIN_POINT", "SIGNAL"]
    statement: str = Field(min_length=8, max_length=1000)
    confidence: int = Field(ge=0, le=100)
    kind: Literal["OBSERVED", "INFERRED"]


class Person(Citation):
    name: str = Field(min_length=3, max_length=150)
    role: str = Field(min_length=2, max_length=200)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=80)


class ResearchPage(Strict):
    source_url: str = Field(min_length=8, max_length=1500)
    text: str = Field(max_length=100000)
    unavailable: bool | None = None
    links: list[str] | None = Field(default=None, max_length=100)


class Coverage(Strict):
    pages_attempted: int = Field(ge=0, le=6)
    unavailable_pages: int = Field(ge=0, le=6)

    @model_validator(mode="after")
    def counts(self):
        if self.unavailable_pages > self.pages_attempted:
            raise ValueError("invalid coverage counts")
        return self


class ResearchOutputV1(Strict):
    facts: list[Finding] = Field(max_length=30)
    people: list[Person] = Field(max_length=5)
    unknowns: list[Note] = Field(max_length=20)
    pages: list[ResearchPage] = Field(max_length=6)
    industry: Finding | None = None
    coverage: Coverage | None = None
    stop_reason: Code | None = None


class ResearchOutputV2(ResearchOutputV1):
    source_artifact_ids: list[UUID] = Field(default_factory=list, max_length=20)


class ICP(Strict):
    code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Z0-9_]+$")
    name: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=15, max_length=2000)


class SetupResult(Strict):
    discovery_query: str = Field(min_length=3, max_length=300)
    icps: list[ICP] = Field(max_length=5)


class Profile(Strict):
    url: str = Field(max_length=1500)
    platform: str = Field(max_length=80)
    source_url: str = Field(max_length=1500)
    evidence_quote: str = Field(max_length=5000)
    basis: Code


class HumanReview(Strict):
    actor_id: UUID
    at: str = Field(min_length=10, max_length=80)


class ContactPerson(Person):
    profiles: list[Profile] = Field(default_factory=list, max_length=20)
    profile_candidates: list[Profile] = Field(default_factory=list, max_length=100)
    human_review: HumanReview | None = None


class ContactResult(Strict):
    people: list[ContactPerson] = Field(max_length=5)
    selected_contact: ContactPerson | None
    unavailable_queries: int = Field(ge=0, le=10)
    stop_reason: Code | None


class Criterion(Strict):
    criterion: str = Field(max_length=60)
    points: int = Field(ge=0, le=100)
    rationale: str = Field(min_length=8, max_length=2000)
    evidence: list[Citation] = Field(max_length=5)


class ScoreResult(Strict):
    criteria: list[Criterion] = Field(min_length=1, max_length=10)
    unknowns: list[Note] = Field(max_length=20)
    score: int = Field(ge=0, le=100)
    relevance: int = Field(ge=0, le=100)
    opportunity: int = Field(ge=0, le=100)
    adjustments: list[Code] = Field(max_length=10)
    stop_reason: Code | None

    @model_validator(mode="after")
    def totals(self):
        if self.score != sum(v.points for v in self.criteria) or self.score != self.relevance+self.opportunity:
            raise ValueError("inconsistent score totals")
        if len({v.criterion for v in self.criteria}) != len(self.criteria):
            raise ValueError("duplicate criterion")
        return self


class Match(Strict):
    product_code: str = Field(max_length=80)
    fit: int = Field(ge=0, le=100)
    rationale: str = Field(min_length=8, max_length=1000)
    evidence: list[Citation] = Field(max_length=5)


class MatchResult(Strict):
    matches: list[Match] = Field(max_length=30)
    selected_product: str | None
    stop_reason: Code | None


class ContentResult(Strict):
    subject: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=30, max_length=3000)
    evidence: list[Citation] = Field(min_length=1, max_length=10)
    channel: Literal["EMAIL", "LINKEDIN"]
    recipient: str = Field(min_length=3, max_length=1500)
    product_code: str = Field(max_length=80)
    status: Literal["PENDING_APPROVAL"]


class WithSources(Strict):
    source_artifact_ids: list[UUID] = Field(default_factory=list, max_length=20)


class SetupV2(SetupResult, WithSources):
    pass


class ContactV2(ContactResult, WithSources):
    pass


class ScoreV2(ScoreResult, WithSources):
    pass


class MatchV2(MatchResult, WithSources):
    pass


class ContentV2(ContentResult, WithSources):
    asset_type: Literal["EMAIL_TEXT", "SOCIAL_TEXT"] | None = None


STAGE_CONTRACTS = dict(SETUP="setup.output", DISCOVERY="discovery.candidate", RESEARCH="research.output",
    CONTACT_SEARCH="contact.output", SCORING="scoring.output", MATCHING="matching.output", DRAFTING="content.output")


SCHEMAS = {
    ("discovery.candidate", 1): DiscoveryCandidateV1,
    ("discovery.candidate", 2): DiscoveryCandidateV2,
    ("research.output", 1): ResearchOutputV1,
    ("research.output", 2): ResearchOutputV2,
}
for _name, _v1, _v2 in (("setup.output", SetupResult, SetupV2), ("contact.output", ContactResult, ContactV2),
    ("scoring.output", ScoreResult, ScoreV2), ("matching.output", MatchResult, MatchV2), ("content.output", ContentResult, ContentV2)):
    SCHEMAS[_name, 1], SCHEMAS[_name, 2] = _v1, _v2


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def content_hash(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def validate_envelope(value):
    try:
        envelope = TaskEnvelope.model_validate_json(canonical_json(value))
    except (ValidationError, TypeError, ValueError, OverflowError):
        raise ContractViolation("TASK_ENVELOPE_INVALID") from None
    if (envelope.contract_name, envelope.schema_version) not in SCHEMAS:
        raise ContractViolation("UNSUPPORTED_CONTRACT")
    return envelope


def validate_payload(name, version, value):
    # Reject bool and numeric strings, including for dictionary registry lookup.
    if type(version) is not int or not isinstance(name, str) or (name, version) not in SCHEMAS:
        raise ContractViolation("UNSUPPORTED_CONTRACT")
    try:
        schema = SCHEMAS[name, version]
        return schema.model_validate_json(canonical_json(value)).model_dump(mode="json", exclude_unset=True)
    except (ValidationError, TypeError, ValueError, OverflowError):
        raise ContractViolation("STAGE_PAYLOAD_INVALID") from None
