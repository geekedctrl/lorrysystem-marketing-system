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

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

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
    contract_name: Literal["discovery.candidate", "research.output"]
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
        expected = {"discovery.candidate": "DISCOVERY", "research.output": "RESEARCH"}
        if self.contract_name in expected and self.stage != expected[self.contract_name]:
            raise ValueError("contract does not match stage")
        return self


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


SCHEMAS = {
    ("discovery.candidate", 1): DiscoveryCandidateV1,
    ("discovery.candidate", 2): DiscoveryCandidateV2,
    ("research.output", 1): ResearchOutputV1,
    ("research.output", 2): ResearchOutputV2,
}


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
