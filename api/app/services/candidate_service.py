from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.catalog import ICPProfile
from app.models.companies import Company, Contact
from app.models.discovery import LeadCandidate, LeadCandidateSource
from app.models.leads import Lead, LeadResearch
from app.models.marketing import Event
from app.schemas.candidate import (
    CandidateAccept,
    CandidateCreate,
    CandidateReject,
    CandidateSourceCreate,
    CandidateUpdate,
)
from app.services.company_service import (
    domain_from_website,
    find_duplicate_company,
    normalize_company_name,
    normalize_domain,
    normalize_website,
)
from app.services.contact_service import (
    clean_optional_text,
    find_contact_by_email,
    normalize_email,
)
from app.services.lead_service import find_active_duplicate_lead


REVIEWABLE_STATUSES = {
    "NEW",
    "READY_FOR_REVIEW",
    "NEEDS_REVIEW",
}

EDITABLE_STATUSES = REVIEWABLE_STATUSES | {"FAILED"}


class CandidateNotFoundError(Exception):
    pass


class CandidateStateError(Exception):
    pass


class ICPProfileNotFoundError(Exception):
    pass


class CandidateSourceDuplicateError(Exception):
    pass


class CandidateContactConflictError(Exception):
    pass


class ExistingActiveLeadError(Exception):
    def __init__(self, lead: Lead):
        self.lead = lead
        super().__init__(
            "An active lead already exists for "
            "this company and ICP profile."
        )


def derive_candidate_status(confidence: float) -> str:
    if confidence >= 0.75:
        return "READY_FOR_REVIEW"
    if confidence >= 0.50:
        return "NEEDS_REVIEW"
    return "REJECTED"


def _active_icp(
    db: Session,
    icp_profile_id: UUID,
) -> ICPProfile:
    icp = db.get(ICPProfile, icp_profile_id)

    if icp is None or not icp.active:
        raise ICPProfileNotFoundError(
            "Active ICP profile not found."
        )

    return icp


def _source_exists(
    db: Session,
    *,
    candidate_id: UUID,
    url: str,
) -> bool:
    statement = select(LeadCandidateSource.id).where(
        LeadCandidateSource.candidate_id == candidate_id,
        LeadCandidateSource.url == url.strip(),
    )

    return db.execute(statement).first() is not None


def _build_source(
    *,
    candidate_id: UUID,
    data: CandidateSourceCreate,
) -> LeadCandidateSource:
    return LeadCandidateSource(
        candidate_id=candidate_id,
        source_type=data.source_type,
        url=data.url.strip(),
        title=clean_optional_text(data.title),
        source_query=clean_optional_text(data.source_query),
        summary=clean_optional_text(data.summary),
        evidence=clean_optional_text(data.evidence),
        published_at=data.published_at,
        discovered_at=(
            data.discovered_at
            or datetime.now(timezone.utc)
        ),
    )


def _first_source_url(
    db: Session,
    candidate_id: UUID,
) -> str | None:
    statement = (
        select(LeadCandidateSource.url)
        .where(
            LeadCandidateSource.candidate_id == candidate_id
        )
        .order_by(
            LeadCandidateSource.discovered_at.asc(),
            LeadCandidateSource.created_at.asc(),
        )
        .limit(1)
    )
    return db.scalar(statement)


def find_duplicate_candidate(
    db: Session,
    *,
    normalized_name: str,
    domain: str | None,
    website_url: str | None,
    exclude_candidate_id: UUID | None = None,
) -> tuple[str, LeadCandidate] | None:
    base_filters = [
        LeadCandidate.status.in_(REVIEWABLE_STATUSES)
    ]

    if exclude_candidate_id is not None:
        base_filters.append(
            LeadCandidate.id != exclude_candidate_id
        )

    if domain:
        statement = select(LeadCandidate).where(
            *base_filters,
            func.lower(LeadCandidate.domain)
            == domain.lower(),
        )
        candidate = db.scalars(statement).first()
        if candidate:
            return "domain", candidate

    normalized_site = normalize_website(website_url)

    if normalized_site:
        statement = select(LeadCandidate).where(
            *base_filters,
            LeadCandidate.normalized_website
            == normalized_site,
        )
        candidate = db.scalars(statement).first()
        if candidate:
            return "website", candidate

    statement = select(LeadCandidate).where(
        *base_filters,
        LeadCandidate.normalized_name == normalized_name,
    )
    candidate = db.scalars(statement).first()

    if candidate:
        return "normalized_name", candidate

    return None


def create_candidate(
    db: Session,
    data: CandidateCreate,
    commit: bool = True,
) -> dict:
    _active_icp(
        db,
        data.suggested_icp_profile_id,
    )

    normalized_name = normalize_company_name(
        data.company_name
    )

    domain = normalize_domain(data.domain)

    if not domain:
        domain = domain_from_website(
            data.website_url
        )

    normalized_site = normalize_website(
        data.website_url
    )

    duplicate = find_duplicate_candidate(
        db,
        normalized_name=normalized_name,
        domain=domain,
        website_url=data.website_url,
    )

    if duplicate:
        _, existing_candidate = duplicate

        if not _source_exists(
            db,
            candidate_id=existing_candidate.id,
            url=data.source.url,
        ):
            db.add(
                _build_source(
                    candidate_id=existing_candidate.id,
                    data=data.source,
                )
            )
            db.add(
                Event(
                    event_type="lead_candidate_source_added",
                    entity_type="LEAD_CANDIDATE",
                    entity_id=existing_candidate.id,
                    actor_type="API",
                    actor_id="marketing-api",
                    metadata_json={
                        "source_type": data.source.source_type,
                        "source_url": data.source.url,
                        "merge_reason": "existing_candidate",
                    },
                )
            )
            db.commit() if commit else db.flush()
            db.refresh(existing_candidate)

        return {
            "outcome": "EXISTING_CANDIDATE",
            "candidate": existing_candidate,
            "existing_company_id": (
                existing_candidate.existing_company_id
            ),
            "existing_lead_id": (
                existing_candidate.duplicate_lead_id
                or existing_candidate.accepted_lead_id
            ),
        }

    company_duplicate = find_duplicate_company(
        db,
        normalized_name=normalized_name,
        domain=domain,
        website_url=data.website_url,
    )

    existing_company = None

    if company_duplicate:
        _, existing_company = company_duplicate

        active_lead = find_active_duplicate_lead(
            db,
            company_id=existing_company.id,
            icp_profile_id=(
                data.suggested_icp_profile_id
            ),
        )

        if active_lead:
            db.add(
                Event(
                    event_type=(
                        "lead_candidate_skipped_existing_lead"
                    ),
                    entity_type="LEAD",
                    entity_id=active_lead.id,
                    actor_type="API",
                    actor_id="marketing-api",
                    metadata_json={
                        "source_type": data.source.source_type,
                        "source_url": data.source.url,
                        "source_query": data.source.source_query,
                    },
                )
            )
            db.commit() if commit else db.flush()

            return {
                "outcome": "EXISTING_ACTIVE_LEAD",
                "candidate": None,
                "existing_company_id": (
                    existing_company.id
                ),
                "existing_lead_id": active_lead.id,
            }

    candidate = LeadCandidate(
        status=derive_candidate_status(
            data.icp_confidence
        ),
        company_name=data.company_name.strip(),
        normalized_name=normalized_name,
        website_url=clean_optional_text(
            data.website_url
        ),
        normalized_website=normalized_site,
        domain=domain,
        industry=clean_optional_text(
            data.industry
        ),
        country_code=(
            data.country_code.upper()
            if data.country_code
            else None
        ),
        state=clean_optional_text(data.state),
        city=clean_optional_text(data.city),
        contact_name=clean_optional_text(
            data.contact_name
        ),
        job_title=clean_optional_text(
            data.job_title
        ),
        email=normalize_email(data.email),
        phone=clean_optional_text(data.phone),
        linkedin_url=clean_optional_text(
            data.linkedin_url
        ),
        suggested_icp_profile_id=(
            data.suggested_icp_profile_id
        ),
        icp_confidence=data.icp_confidence,
        icp_reasoning=data.icp_reasoning.strip(),
        fleet_clues=data.fleet_clues,
        buying_signals=data.buying_signals,
        source_summary=clean_optional_text(
            data.source_summary
        ),
        existing_company_id=(
            existing_company.id
            if existing_company
            else None
        ),
    )

    db.add(candidate)

    try:
        db.flush()

        db.add(
            _build_source(
                candidate_id=candidate.id,
                data=data.source,
            )
        )

        db.add(
            Event(
                event_type="lead_candidate_created",
                entity_type="LEAD_CANDIDATE",
                entity_id=candidate.id,
                actor_type="API",
                actor_id="marketing-api",
                metadata_json={
                    "status": candidate.status,
                    "existing_company_id": (
                        str(existing_company.id)
                        if existing_company
                        else None
                    ),
                    "icp_profile_id": str(
                        data.suggested_icp_profile_id
                    ),
                    "icp_confidence": (
                        data.icp_confidence
                    ),
                    "source_type": data.source.source_type,
                    "source_url": data.source.url,
                },
            )
        )

        db.commit() if commit else db.flush()
        db.refresh(candidate)

        return {
            "outcome": (
                "EXISTING_COMPANY"
                if existing_company
                else "NEW_CANDIDATE"
            ),
            "candidate": candidate,
            "existing_company_id": (
                existing_company.id
                if existing_company
                else None
            ),
            "existing_lead_id": None,
        }

    except IntegrityError as exc:
        db.rollback()

        duplicate = find_duplicate_candidate(
            db,
            normalized_name=normalized_name,
            domain=domain,
            website_url=data.website_url,
        )

        if duplicate:
            _, existing_candidate = duplicate

            if not _source_exists(
                db,
                candidate_id=existing_candidate.id,
                url=data.source.url,
            ):
                db.add(
                    _build_source(
                        candidate_id=existing_candidate.id,
                        data=data.source,
                    )
                )
                db.commit() if commit else db.flush()
                db.refresh(existing_candidate)

            return {
                "outcome": "EXISTING_CANDIDATE",
                "candidate": existing_candidate,
                "existing_company_id": (
                    existing_candidate.existing_company_id
                ),
                "existing_lead_id": (
                    existing_candidate.duplicate_lead_id
                    or existing_candidate.accepted_lead_id
                ),
            }

        raise ValueError(
            "Candidate conflicts with an existing record."
        ) from exc


def get_candidate(
    db: Session,
    candidate_id: UUID,
) -> LeadCandidate | None:
    return db.get(
        LeadCandidate,
        candidate_id,
    )


def list_candidates(
    db: Session,
    *,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[LeadCandidate]:
    statement = select(LeadCandidate)

    if status is not None:
        statement = statement.where(
            LeadCandidate.status == status
        )

    statement = (
        statement
        .order_by(LeadCandidate.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    return list(db.scalars(statement).all())


def update_candidate(
    db: Session,
    *,
    candidate_id: UUID,
    data: CandidateUpdate,
) -> LeadCandidate:
    candidate = get_candidate(db, candidate_id)

    if candidate is None:
        raise CandidateNotFoundError(
            "Candidate not found."
        )

    if candidate.status not in EDITABLE_STATUSES:
        raise CandidateStateError(
            "Candidate can no longer be edited."
        )

    payload = data.model_dump(
        exclude_unset=True
    )

    required_non_null = {
        "company_name",
        "suggested_icp_profile_id",
        "icp_confidence",
        "icp_reasoning",
    }

    for field in required_non_null:
        if (
            field in payload
            and payload[field] is None
        ):
            raise ValueError(
                f"{field} cannot be null."
            )

    if "suggested_icp_profile_id" in payload:
        _active_icp(
            db,
            payload["suggested_icp_profile_id"],
        )

    simple_text_fields = {
        "industry",
        "state",
        "city",
        "contact_name",
        "job_title",
        "phone",
        "linkedin_url",
        "source_summary",
        "failure_reason",
    }

    for field in simple_text_fields:
        if field in payload:
            setattr(
                candidate,
                field,
                clean_optional_text(payload[field]),
            )

    if "company_name" in payload:
        candidate.company_name = (
            payload["company_name"].strip()
        )

    if "website_url" in payload:
        candidate.website_url = clean_optional_text(
            payload["website_url"]
        )

    if "domain" in payload:
        candidate.domain = normalize_domain(
            payload["domain"]
        )
    elif "website_url" in payload:
        candidate.domain = domain_from_website(
            candidate.website_url
        )

    if "country_code" in payload:
        candidate.country_code = (
            payload["country_code"].upper()
            if payload["country_code"]
            else None
        )

    if "email" in payload:
        candidate.email = normalize_email(
            payload["email"]
        )

    for field in (
        "suggested_icp_profile_id",
        "icp_confidence",
        "fleet_clues",
        "buying_signals",
    ):
        if field in payload:
            setattr(
                candidate,
                field,
                payload[field],
            )

    if "icp_reasoning" in payload:
        candidate.icp_reasoning = (
            payload["icp_reasoning"].strip()
        )

    candidate.normalized_name = (
        normalize_company_name(
            candidate.company_name
        )
    )

    candidate.normalized_website = (
        normalize_website(
            candidate.website_url
        )
    )

    if not candidate.domain:
        candidate.domain = domain_from_website(
            candidate.website_url
        )

    duplicate = find_duplicate_candidate(
        db,
        normalized_name=candidate.normalized_name,
        domain=candidate.domain,
        website_url=candidate.website_url,
        exclude_candidate_id=candidate.id,
    )

    if duplicate:
        _, other = duplicate
        raise ValueError(
            "Candidate conflicts with existing "
            f"candidate {other.id}."
        )

    company_duplicate = find_duplicate_company(
        db,
        normalized_name=candidate.normalized_name,
        domain=candidate.domain,
        website_url=candidate.website_url,
    )

    if company_duplicate:
        _, company = company_duplicate

        active_lead = find_active_duplicate_lead(
            db,
            company_id=company.id,
            icp_profile_id=(
                candidate.suggested_icp_profile_id
            ),
        )

        if active_lead:
            raise ExistingActiveLeadError(
                active_lead
            )

        candidate.existing_company_id = company.id
    else:
        candidate.existing_company_id = None

    candidate.updated_at = datetime.now(
        timezone.utc
    )

    db.add(
        Event(
            event_type="lead_candidate_updated",
            entity_type="LEAD_CANDIDATE",
            entity_id=candidate.id,
            actor_type="API",
            actor_id="marketing-api",
            metadata_json={
                "changed_fields": sorted(
                    payload.keys()
                )
            },
        )
    )

    try:
        db.commit()
        db.refresh(candidate)
    except IntegrityError as exc:
        db.rollback()
        raise ValueError(
            "Candidate conflicts with an existing record."
        ) from exc

    return candidate


def add_candidate_source(
    db: Session,
    *,
    candidate_id: UUID,
    data: CandidateSourceCreate,
) -> LeadCandidateSource:
    candidate = get_candidate(
        db,
        candidate_id,
    )

    if candidate is None:
        raise CandidateNotFoundError(
            "Candidate not found."
        )

    if _source_exists(
        db,
        candidate_id=candidate_id,
        url=data.url,
    ):
        raise CandidateSourceDuplicateError(
            "Source URL already exists for this candidate."
        )

    source = _build_source(
        candidate_id=candidate_id,
        data=data,
    )

    db.add(source)

    try:
        db.flush()

        db.add(
            Event(
                event_type="lead_candidate_source_added",
                entity_type="LEAD_CANDIDATE",
                entity_id=candidate_id,
                actor_type="API",
                actor_id="marketing-api",
                metadata_json={
                    "source_type": data.source_type,
                    "source_url": data.url,
                },
            )
        )

        db.commit()
        db.refresh(source)

    except IntegrityError as exc:
        db.rollback()
        raise CandidateSourceDuplicateError(
            "Source URL already exists for this candidate."
        ) from exc

    return source


def reject_candidate(
    db: Session,
    *,
    candidate_id: UUID,
    data: CandidateReject,
) -> LeadCandidate:
    candidate = get_candidate(
        db,
        candidate_id,
    )

    if candidate is None:
        raise CandidateNotFoundError(
            "Candidate not found."
        )

    if candidate.status not in REVIEWABLE_STATUSES:
        raise CandidateStateError(
            "Only reviewable candidates can be rejected."
        )

    now = datetime.now(timezone.utc)

    candidate.status = "REJECTED"
    candidate.reviewed_at = now
    candidate.reviewed_by = (
        data.reviewed_by.strip()
    )
    candidate.review_notes = (
        clean_optional_text(
            data.review_notes
        )
    )
    candidate.updated_at = now

    db.add(
        Event(
            event_type="lead_candidate_rejected",
            entity_type="LEAD_CANDIDATE",
            entity_id=candidate.id,
            actor_type="USER",
            actor_id=candidate.reviewed_by,
            metadata_json={
                "review_notes": (
                    candidate.review_notes
                )
            },
        )
    )

    db.commit()
    db.refresh(candidate)
    return candidate


def accept_candidate(
    db: Session,
    *,
    candidate_id: UUID,
    data: CandidateAccept,
    commit: bool = True,
) -> dict:
    candidate = get_candidate(
        db,
        candidate_id,
    )

    if candidate is None:
        raise CandidateNotFoundError(
            "Candidate not found."
        )

    if candidate.status not in REVIEWABLE_STATUSES:
        raise CandidateStateError(
            "Only reviewable candidates can be accepted."
        )

    icp_profile_id = (
        data.icp_profile_id
        or candidate.suggested_icp_profile_id
    )

    _active_icp(
        db,
        icp_profile_id,
    )

    try:
        company = None

        if candidate.existing_company_id:
            company = db.get(
                Company,
                candidate.existing_company_id,
            )

        if company is None:
            company_duplicate = find_duplicate_company(
                db,
                normalized_name=candidate.normalized_name,
                domain=candidate.domain,
                website_url=candidate.website_url,
            )

            if company_duplicate:
                _, company = company_duplicate
                candidate.existing_company_id = (
                    company.id
                )

        source_url = _first_source_url(
            db,
            candidate.id,
        )

        if company is None:
            company = Company(
                name=candidate.company_name,
                normalized_name=(
                    candidate.normalized_name
                ),
                website_url=(
                    candidate.website_url
                ),
                domain=candidate.domain,
                industry=candidate.industry,
                country_code=(
                    candidate.country_code
                ),
                state=candidate.state,
                city=candidate.city,
                source_type="AI_DISCOVERY",
                source_url=source_url,
                metadata_json={
                    "lead_candidate_id": str(
                        candidate.id
                    )
                },
            )

            db.add(company)
            db.flush()

            candidate.existing_company_id = (
                company.id
            )

        duplicate_lead = find_active_duplicate_lead(
            db,
            company_id=company.id,
            icp_profile_id=icp_profile_id,
        )

        if duplicate_lead:
            now = datetime.now(timezone.utc)

            candidate.status = "DUPLICATE"
            candidate.duplicate_lead_id = (
                duplicate_lead.id
            )
            candidate.reviewed_at = now
            candidate.reviewed_by = (
                data.reviewed_by.strip()
            )
            candidate.review_notes = (
                clean_optional_text(
                    data.review_notes
                )
            )
            candidate.updated_at = now

            db.add(
                Event(
                    event_type="lead_candidate_duplicate",
                    entity_type="LEAD_CANDIDATE",
                    entity_id=candidate.id,
                    actor_type="USER",
                    actor_id=(
                        candidate.reviewed_by
                    ),
                    metadata_json={
                        "existing_lead_id": str(
                            duplicate_lead.id
                        ),
                        "company_id": str(
                            company.id
                        ),
                        "icp_profile_id": str(
                            icp_profile_id
                        ),
                    },
                )
            )

            db.commit() if commit else db.flush()
            db.refresh(candidate)

            return {
                "outcome": "DUPLICATE",
                "candidate": candidate,
                "lead_id": duplicate_lead.id,
            }

        contact = None

        meaningful_contact_values = [
            candidate.contact_name,
            candidate.job_title,
            candidate.email,
            candidate.phone,
            candidate.linkedin_url,
        ]

        has_meaningful_contact = any(
            clean_optional_text(value)
            for value in meaningful_contact_values
        )

        if has_meaningful_contact:
            email = normalize_email(
                candidate.email
            )

            if email:
                existing_contact = find_contact_by_email(
                    db,
                    email,
                )

                if existing_contact:
                    if (
                        existing_contact.company_id
                        != company.id
                    ):
                        raise CandidateContactConflictError(
                            "Candidate contact email belongs "
                            "to a different company."
                        )

                    contact = existing_contact

            if contact is None:
                contact = Contact(
                    company_id=company.id,
                    full_name=clean_optional_text(
                        candidate.contact_name
                    ),
                    job_title=clean_optional_text(
                        candidate.job_title
                    ),
                    email=email,
                    phone=clean_optional_text(
                        candidate.phone
                    ),
                    linkedin_url=clean_optional_text(
                        candidate.linkedin_url
                    ),
                    is_primary=True,
                    source_url=source_url,
                )

                db.add(contact)
                db.flush()

        lead = Lead(
            company_id=company.id,
            primary_contact_id=(
                contact.id
                if contact
                else None
            ),
            icp_profile_id=icp_profile_id,
            priority=data.priority,
        )

        db.add(lead)
        db.flush()

        # ----------------------------------------------------
        # Automatic initial Research queue creation.
        #
        # Candidate acceptance creates the Lead and its first
        # Research job in the same database transaction.
        #
        # Lead remains DISCOVERED.
        # Research begins as PENDING.
        # ----------------------------------------------------

        research = LeadResearch(
            lead_id=lead.id,
        )

        db.add(research)
        db.flush()

        db.add(
            Event(
                event_type="lead_discovered",
                entity_type="LEAD",
                entity_id=lead.id,
                actor_type="USER",
                actor_id=data.reviewed_by.strip(),
                metadata_json={
                    "company_id": str(
                        company.id
                    ),
                    "primary_contact_id": (
                        str(contact.id)
                        if contact
                        else None
                    ),
                    "icp_profile_id": str(
                        icp_profile_id
                    ),
                    "priority": data.priority,
                    "lead_candidate_id": str(
                        candidate.id
                    ),
                },
            )
        )

        db.add(
            Event(
                event_type="research_requested",
                entity_type="RESEARCH",
                entity_id=research.id,
                actor_type="API",
                actor_id="marketing-api",
                metadata_json={
                    "lead_id": str(lead.id),
                    "lead_candidate_id": str(
                        candidate.id
                    ),
                    "research_status": "PENDING",
                    "lead_status_at_request": (
                        lead.status
                    ),
                    "lead_moved_to_researching": False,
                },
            )
        )

        now = datetime.now(timezone.utc)

        candidate.status = "ACCEPTED"
        candidate.accepted_lead_id = lead.id
        candidate.duplicate_lead_id = None
        candidate.existing_company_id = company.id
        candidate.reviewed_at = now
        candidate.reviewed_by = (
            data.reviewed_by.strip()
        )
        candidate.review_notes = (
            clean_optional_text(
                data.review_notes
            )
        )
        candidate.updated_at = now

        db.add(
            Event(
                event_type="lead_candidate_accepted",
                entity_type="LEAD_CANDIDATE",
                entity_id=candidate.id,
                actor_type="USER",
                actor_id=candidate.reviewed_by,
                metadata_json={
                    "lead_id": str(lead.id),
                    "company_id": str(company.id),
                    "primary_contact_id": (
                        str(contact.id)
                        if contact
                        else None
                    ),
                    "icp_profile_id": str(
                        icp_profile_id
                    ),
                },
            )
        )

        from app.services.product_automation import managed, schedule
        if managed(db):
            research = db.scalar(select(LeadResearch).where(
                LeadResearch.lead_id == lead.id, LeadResearch.research_status == 'PENDING'
            ))
            if research:
                schedule(db, 'RESEARCH', research.id)
        db.commit() if commit else db.flush()
        db.refresh(candidate)
        db.refresh(lead)

        return {
            "outcome": "ACCEPTED",
            "candidate": candidate,
            "lead_id": lead.id,
        }

    except CandidateContactConflictError:
        db.rollback()
        raise

    except IntegrityError as exc:
        db.rollback()
        raise ValueError(
            "Candidate acceptance conflicts "
            "with an existing record."
        ) from exc

    except Exception:
        db.rollback()
        raise
