"""Human contact/qualification decisions and a workspace-scoped automation queue."""

import re
import json
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.db.session import get_db
from app.models.catalog import ICPProfile, Product
from app.models.companies import Company, Contact
from app.models.leads import Lead, LeadResearch, LeadScore, ProductMatch, ResearchSource
from app.models.marketing import Event
from app.models.pipeline import PipelineRun
from app.schemas.contact import ContactRead
from app.schemas.company import CompanyRead
from app.schemas.lead import LeadRead
from app.schemas.research import ResearchRead
from app.schemas.scoring import ScoreCreate
from app.schemas.product_matching import ProductMatchCreate
from app.schemas.marketing_action import MarketingActionCreate
from app.services.scoring_service import create_score, get_latest_usable_research
from app.services.product_matching_service import upsert_product_match
from app.services.marketing_action_service import create_action
from app.services.approval_service import submit_action_for_approval
from app.services.lead_service import transition_lead
from app.workspace_context import current_principal

router = APIRouter(tags=["Lead pipeline"])
ACTIVE = ("PENDING", "RUNNING")
OPEN = ("DISCOVERED", "RESEARCHING", "QUALIFIED", "READY_FOR_OUTREACH")
DEFAULT_RUBRIC = [
    {
        "criterion": "icp_fit",
        "label": "ICP fit",
        "max_points": 40,
        "description": "Documented fit to this ICP and its qualification rules",
    },
    {
        "criterion": "operational_need",
        "label": "Operational need",
        "max_points": 30,
        "description": "Observed operations and supported needs relevant to this workspace",
    },
    {
        "criterion": "scale",
        "label": "Operating scale",
        "max_points": 15,
        "description": "Documented scale or capacity relevant to the ICP; unknown size earns no points",
    },
    {
        "criterion": "buying_signals",
        "label": "Buying signals",
        "max_points": 10,
        "description": "Observed changes or activity; do not treat research hypotheses as confirmed intent",
    },
    {
        "criterion": "evidence_quality",
        "label": "Evidence quality",
        "max_points": 5,
        "description": "Official and specific public evidence supporting the company assessment",
    },
]


def scoring_rubric(icp):
    value = icp.qualification_rules.get("scoring_rubric", DEFAULT_RUBRIC)
    if (
        not isinstance(value, list)
        or not 1 <= len(value) <= 10
        or any(
            not isinstance(r, dict)
            or not isinstance(r.get("criterion"), str)
            or not re.fullmatch(r"[a-z][a-z0-9_]{2,59}", r["criterion"])
            or type(r.get("max_points")) is not int
            or not 1 <= r["max_points"] <= 100
            for r in value
        )
        or sum(r["max_points"] for r in value) != 100
        or len({r["criterion"] for r in value}) != len(value)
    ):
        raise HTTPException(
            409,
            "The ICP scoring rubric must define distinct criteria totaling 100 points",
        )
    return value


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ContactReview(Strict):
    contact_id: UUID | None = None
    research_id: UUID | None = None
    person_index: int | None = Field(default=None, ge=0, le=4, strict=True)
    linkedin_url: str | None = Field(default=None, max_length=1500)
    confirmed: Literal[True]


class QueueStage(Strict):
    stage: Literal["SCORING", "MATCHING", "DRAFTING"]
    product_id: UUID | None = None
    channel: Literal["EMAIL", "LINKEDIN"] = "EMAIL"


class Qualification(Strict):
    note: str = Field(min_length=8, max_length=1000)


class Citation(Strict):
    source_url: str = Field(min_length=8, max_length=1500)
    evidence_quote: str = Field(min_length=8, max_length=500)


class ScoreComponent(Strict):
    criterion: str = Field(min_length=3, max_length=120)
    points: int = Field(ge=0, le=100, strict=True)
    max_points: int = Field(ge=1, le=100, strict=True)
    rationale: str = Field(min_length=8, max_length=800)
    evidence: list[Citation] = Field(default_factory=list, max_length=5)


class ScoringOutput(Strict):
    components: list[ScoreComponent] = Field(min_length=1, max_length=10)
    rationale: str = Field(min_length=15, max_length=2000)
    gaps: list[str] = Field(default_factory=list, max_length=15)


class MatchItem(Strict):
    product_code: str = Field(min_length=1, max_length=100)
    fit_score: int = Field(ge=0, le=100, strict=True)
    rationale: str = Field(min_length=15, max_length=1500)
    evidence: list[Citation] = Field(default_factory=list, max_length=5)


class MatchingOutput(Strict):
    matches: list[MatchItem] = Field(min_length=1, max_length=30)


class DraftOutput(Strict):
    subject: str = Field(min_length=3, max_length=150)
    content: str = Field(min_length=30, max_length=5000)
    evidence: list[Citation] = Field(min_length=1, max_length=10)


class Complete(Strict):
    output: dict


class Failure(Strict):
    reason: str = Field(pattern=r"^[A-Z0-9_]{1,80}$")


def permit(*roles):
    principal = current_principal.get()
    if principal.automation_job_id and principal.role == "SERVICE" and "ADMIN" in roles:
        return principal
    if principal.role not in roles or (
        principal.role == "SERVICE" and not principal.actor.startswith("service:")
    ):
        raise HTTPException(
            403,
            "This stage requires a workspace team member or named automation credential",
        )
    return principal


def lead_for(db, lead_id):
    lead = db.scalar(select(Lead).where(Lead.id == lead_id).with_for_update())
    if lead is None:
        raise HTTPException(404, "Lead not found")
    if lead.status not in OPEN:
        raise HTTPException(409, "This lead is not open for preparation stages")
    return lead


def run_read(run):
    return {
        key: getattr(run, key)
        for key in (
            "id",
            "workspace_id",
            "lead_id",
            "research_id",
            "contact_id",
            "stage",
            "status",
            "result",
            "failure_reason",
            "created_at",
            "started_at",
            "finished_at",
        )
    }


def audit(db, kind, lead, **metadata):
    db.add(
        Event(
            event_type=kind,
            entity_type="LEAD",
            entity_id=lead.id,
            actor_type="API",
            actor_id=current_principal.get().actor,
            metadata_json=metadata,
        )
    )


def normalized(value):
    return " ".join(str(value or "").casefold().split())


def profile_url(value):
    try:
        url = urlsplit(value or "")
        host = (url.hostname or "").removeprefix("www.")
        return (
            value
            if url.scheme == "https"
            and not url.username
            and not url.password
            and url.port in (None, 443)
            and re.fullmatch(r"(?:[a-z]{2}\.)?linkedin\.com", host)
            and re.fullmatch(r"/in/[a-zA-Z0-9_%.-]+/?", url.path)
            else None
        )
    except ValueError:
        return None


def contact_signature(contact):
    values = {
        key: getattr(contact, key)
        for key in (
            "full_name",
            "job_title",
            "email",
            "phone",
            "linkedin_url",
            "status",
        )
    }
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


@router.post("/api/leads/{lead_id}/contact-review")
def review_contact(lead_id: UUID, data: ContactReview, db=Depends(get_db)):
    permit("ADMIN", "OPERATOR")
    lead = lead_for(db, lead_id)
    if db.scalar(
        select(PipelineRun.id).where(
            PipelineRun.lead_id == lead.id, PipelineRun.status.in_(ACTIVE)
        )
    ):
        raise HTTPException(
            409, "Wait for the current stage to finish before changing the contact"
        )
    if data.contact_id:
        if (
            data.research_id is not None
            or data.person_index is not None
            or data.linkedin_url is not None
        ):
            raise HTTPException(422, "Choose an existing contact or a research person")
        contact = db.get(Contact, data.contact_id)
        if (
            contact is None
            or contact.company_id != lead.company_id
            or contact.status != "ACTIVE"
        ):
            raise HTTPException(404, "Active company contact not found")
    else:
        report = db.get(LeadResearch, data.research_id) if data.research_id else None
        if (
            not report
            or report.lead_id != lead.id
            or report.research_status not in ("COMPLETED", "PARTIAL")
            or data.person_index is None
        ):
            raise HTTPException(404, "Usable company research person not found")
        people = report.company_facts.get("people", [])
        if (
            not isinstance(people, list)
            or data.person_index >= len(people)
            or not isinstance(people[data.person_index], dict)
        ):
            raise HTTPException(404, "Research person not found")
        person = people[data.person_index]
        name, quote = person.get("name"), person.get("evidence_quote")
        if (
            not isinstance(name, str)
            or not 3 <= len(name) <= 120
            or not isinstance(quote, str)
            or normalized(name) not in normalized(quote)
        ):
            raise HTTPException(409, "This person has insufficient saved evidence")
        urls = person.get("source_urls", [])
        if not isinstance(urls, list):
            raise HTTPException(409, "This person has no supported source links")
        sources = list(
            db.scalars(
                select(ResearchSource).where(ResearchSource.research_id == report.id)
            )
        )
        source = next(
            (
                s
                for s in sources
                if s.url in urls and normalized(quote) in normalized(s.evidence)
            ),
            None,
        )
        if source is None:
            raise HTTPException(
                409, "The person quote does not match a saved research source"
            )
        company = db.get(Company, lead.company_id)
        host = (
            urlsplit(company.website_url or "").hostname or company.domain or ""
        ).removeprefix("www.")
        company_name = re.sub(
            r"\b(sdn|bhd|berhad|limited|ltd|inc)\b", "", normalized(company.name)
        ).strip()
        title = person.get("job_title") or ""
        if (
            not isinstance(title, str)
            or len(title) > 150
            or (title and normalized(title) not in normalized(quote))
            or not (
                (urlsplit(source.url).hostname or "").removeprefix("www.") == host
                or (len(company_name) >= 3 and company_name in normalized(quote))
            )
        ):
            raise HTTPException(
                409, "The source does not support this role and company relationship"
            )
        email = person.get("business_email")
        email = (
            email.lower().strip()
            if isinstance(email, str)
            and re.fullmatch(r"[^\s@?&#]+@[^\s@?&#]+\.[^\s@?&#]+", email)
            and normalized(email) in normalized(quote)
            else None
        )
        phone = person.get("business_phone")
        phone = (
            phone
            if isinstance(phone, str)
            and len(phone) <= 60
            and len(re.sub(r"\D", "", phone)) >= 7
            and re.sub(r"\D", "", phone) in re.sub(r"\D", "", quote)
            else None
        )
        profiles = [
            p
            for key in ("professional_profiles", "profile_candidates")
            for p in (person.get(key) if isinstance(person.get(key), list) else [])
            if isinstance(p, dict) and p.get("platform") == "LinkedIn"
        ]
        allowed = {p.get("url") for p in profiles}
        if profile_url(person.get("linkedin_url")):
            allowed.add(person["linkedin_url"])
        linkedin = data.linkedin_url or person.get("linkedin_url")
        if linkedin and (linkedin not in allowed or not profile_url(linkedin)):
            raise HTTPException(
                409, "Choose a LinkedIn profile from the saved research evidence"
            )
        if linkedin:
            selected = next((p for p in profiles if p.get("url") == linkedin), None)
            if selected and (
                not selected.get("evidence_quote")
                or not any(
                    s.url in (selected.get("source_urls") or [])
                    and normalized(selected.get("evidence_quote"))
                    in normalized(s.evidence)
                    for s in sources
                )
            ):
                raise HTTPException(
                    409, "The selected profile has no saved supporting evidence"
                )
        contact = (
            db.scalar(select(Contact).where(Contact.email == email)) if email else None
        )
        if contact and (
            contact.company_id != lead.company_id
            or (contact.full_name and normalized(contact.full_name) != normalized(name))
        ):
            raise HTTPException(
                409,
                "This email is already attached to a different contact; review that contact explicitly",
            )
        if not contact:
            contact = db.scalar(
                select(Contact).where(
                    Contact.company_id == lead.company_id,
                    Contact.full_name == name,
                    Contact.source_url == source.url,
                )
            )
        if not contact:
            contact = Contact(
                company_id=lead.company_id,
                full_name=name,
                job_title=person.get("job_title"),
                email=email,
                phone=phone,
                linkedin_url=linkedin,
                source_url=source.url,
                is_primary=False,
            )
            db.add(contact)
            db.flush()
        elif contact.status != "ACTIVE":
            raise HTTPException(409, "The matching contact is inactive")
        else:
            if not contact.full_name:
                contact.full_name = name
            if not contact.job_title:
                contact.job_title = title or None
            if linkedin:
                contact.linkedin_url = linkedin
    lead.primary_contact_id = contact.id
    audit(
        db,
        "lead_contact_reviewed",
        lead,
        contact_id=str(contact.id),
        research_id=str(data.research_id) if data.research_id else None,
        person_index=data.person_index,
        profile_url=contact.linkedin_url,
        contact_signature=contact_signature(contact),
        review_mode="AUTOMATIC" if current_principal.get().automation_job_id else "HUMAN",
    )
    db.commit()
    return ContactRead.model_validate(contact)


def reviewed(db, lead):
    contact = (
        db.get(Contact, lead.primary_contact_id) if lead.primary_contact_id else None
    )
    if not contact or contact.status != "ACTIVE":
        return False
    return (
        db.scalar(
            select(Event.id)
            .where(
                Event.entity_id == lead.id,
                Event.event_type == "lead_contact_reviewed",
                Event.metadata_json["contact_id"].astext
                == str(lead.primary_contact_id),
                Event.metadata_json["contact_signature"].astext
                == contact_signature(contact),
            )
            .limit(1)
        )
        is not None
    )


def fingerprint(db, lead, contact):
    icp = db.get(ICPProfile, lead.icp_profile_id)
    products = list(
        db.scalars(
            select(Product).where(Product.active.is_(True)).order_by(Product.code)
        )
    )
    if not icp or not icp.active or not products or len(products) > 30:
        raise HTTPException(
            409, "Configure an active ICP and between one and thirty active products"
        )
    scoring_rubric(icp)
    value = {
        "icp": {
            "id": str(icp.id),
            "description": icp.description,
            "rules": icp.qualification_rules,
        },
        "products": [
            {
                "id": str(p.id),
                "code": p.code,
                "name": p.name,
                "description": p.description,
                "category": p.category,
            }
            for p in products
        ],
        "contact": {
            "name": contact.full_name,
            "title": contact.job_title,
            "email": contact.email,
            "linkedin": contact.linkedin_url,
        },
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str).encode()
    ).hexdigest()


def score_current(score, research, contact_id, context_hash):
    return bool(
        score
        and research
        and score.score_breakdown.get("research_id") == str(research.id)
        and score.score_breakdown.get("contact_id") == str(contact_id)
        and score.score_breakdown.get("context_hash") == context_hash
    )


def enqueue(db, lead, data, principal):
    if db.scalar(
        select(PipelineRun.id).where(
            PipelineRun.lead_id == lead.id, PipelineRun.status.in_(ACTIVE)
        )
    ):
        raise HTTPException(409, "A stage is already queued or running for this lead")
    research = get_latest_usable_research(db, lead_id=lead.id)
    contact = (
        db.get(Contact, lead.primary_contact_id) if lead.primary_contact_id else None
    )
    if (
        research is None
        or not contact
        or contact.company_id != lead.company_id
        or contact.status != "ACTIVE"
        or not reviewed(db, lead)
    ):
        raise HTTPException(
            409, "Complete research and confirm a primary contact first"
        )
    snapshot = {"context_hash": fingerprint(db, lead, contact)}
    score = db.scalar(
        select(LeadScore).where(
            LeadScore.lead_id == lead.id, LeadScore.is_current.is_(True)
        )
    )
    if data.stage in ("MATCHING", "DRAFTING"):
        if lead.status not in ("QUALIFIED", "READY_FOR_OUTREACH") or not score_current(
            score, research, contact.id, snapshot["context_hash"]
        ):
            raise HTTPException(409, "Review the score and qualify this lead first")
        snapshot["score_id"] = str(score.id)
    if data.stage == "DRAFTING":
        product = db.get(Product, data.product_id) if data.product_id else None
        match = (
            db.scalar(
                select(ProductMatch).where(
                    ProductMatch.lead_id == lead.id,
                    ProductMatch.product_id == data.product_id,
                )
            )
            if product
            else None
        )
        if not product or not product.active or not match or match.fit_score <= 0:
            raise HTTPException(
                409, "Choose an active, positively matched workspace product"
            )
        matching = db.scalar(
            select(PipelineRun)
            .where(
                PipelineRun.lead_id == lead.id,
                PipelineRun.stage == "MATCHING",
                PipelineRun.status == "COMPLETED",
            )
            .order_by(PipelineRun.finished_at.desc())
            .limit(1)
        )
        if (
            not matching
            or matching.research_id != research.id
            or matching.contact_id != contact.id
            or matching.input_snapshot.get("context_hash") != snapshot["context_hash"]
            or matching.input_snapshot.get("score_id") != str(score.id)
            or not any(
                m.get("id") == str(match.id) and m.get("fit_score", 0) > 0
                for m in matching.result.get("matches", [])
            )
        ):
            raise HTTPException(
                409,
                "Complete product matching with the current research and score before drafting",
            )
        if data.channel == "EMAIL" and not contact.email:
            raise HTTPException(
                409,
                "Email drafting requires a confirmed contact with a public business email",
            )
        if data.channel == "LINKEDIN" and not profile_url(contact.linkedin_url):
            raise HTTPException(
                409, "LinkedIn drafting requires a reviewed individual LinkedIn profile"
            )
        snapshot.update(
            product_id=str(product.id),
            match_id=str(match.id),
            match_fit=match.fit_score,
            match_rationale=match.rationale,
            channel=data.channel,
        )
    run = PipelineRun(
        lead_id=lead.id,
        research_id=research.id,
        contact_id=contact.id,
        stage=data.stage,
        requested_by=principal.actor,
        input_snapshot=snapshot,
    )
    db.add(run)
    db.flush()
    audit(db, "lead_stage_queued", lead, run_id=str(run.id), stage=run.stage)
    return run


@router.post("/api/leads/{lead_id}/pipeline", status_code=202)
def queue(lead_id: UUID, data: QueueStage, db=Depends(get_db)):
    principal = permit("ADMIN", "OPERATOR")
    run = enqueue(db, lead_for(db, lead_id), data, principal)
    from app.services.product_automation import managed, schedule

    if managed(db):
        schedule(db, run.stage, run.id)
    db.commit()
    return run_read(run)


@router.post("/api/leads/{lead_id}/qualify", status_code=202)
def qualify(lead_id: UUID, data: Qualification, db=Depends(get_db)):
    principal = permit("ADMIN", "OPERATOR")
    lead = lead_for(db, lead_id)
    score = db.scalar(
        select(LeadScore).where(
            LeadScore.lead_id == lead.id, LeadScore.is_current.is_(True)
        )
    )
    contact = (
        db.get(Contact, lead.primary_contact_id) if lead.primary_contact_id else None
    )
    if (
        not contact
        or not reviewed(db, lead)
        or not score_current(
            score,
            get_latest_usable_research(db, lead_id=lead.id),
            lead.primary_contact_id,
            fingerprint(db, lead, contact),
        )
    ):
        raise HTTPException(409, "Complete scoring before reviewing qualification")
    if lead.status not in ("RESEARCHING", "QUALIFIED"):
        raise HTTPException(409, "This lead is not ready for qualification")
    transition_lead(
        db, lead_id=lead.id, new_status="QUALIFIED", note=data.note, commit=False
    )
    audit(
        db,
        "lead_qualification_reviewed",
        lead,
        note=data.note,
        score=lead.current_score,
    )
    run = enqueue(db, lead, QueueStage(stage="MATCHING"), principal)
    from app.services.product_automation import managed, schedule

    if managed(db):
        schedule(db, "MATCHING", run.id)
    db.commit()
    return run_read(run)


@router.get("/api/leads/{lead_id}/pipeline")
def runs(lead_id: UUID, db=Depends(get_db)):
    if db.get(Lead, lead_id) is None:
        raise HTTPException(404, "Lead not found")
    return [
        run_read(row)
        for row in db.scalars(
            select(PipelineRun)
            .where(PipelineRun.lead_id == lead_id)
            .order_by(PipelineRun.created_at.desc())
            .limit(30)
        )
    ]


@router.get("/api/leads/{lead_id}/pipeline-state")
def state(lead_id: UUID, db=Depends(get_db)):
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    research = get_latest_usable_research(db, lead_id=lead.id)
    score = db.scalar(
        select(LeadScore).where(
            LeadScore.lead_id == lead.id, LeadScore.is_current.is_(True)
        )
    )
    matching = db.scalar(
        select(PipelineRun)
        .where(
            PipelineRun.lead_id == lead.id,
            PipelineRun.stage == "MATCHING",
            PipelineRun.status == "COMPLETED",
        )
        .order_by(PipelineRun.finished_at.desc())
        .limit(1)
    )
    contact = (
        db.get(Contact, lead.primary_contact_id) if lead.primary_contact_id else None
    )
    context_hash = None
    if contact:
        try:
            context_hash = fingerprint(db, lead, contact)
        except HTTPException:
            pass
    scored = score_current(score, research, lead.primary_contact_id, context_hash)
    current = bool(
        matching
        and research
        and scored
        and contact
        and matching.research_id == research.id
        and matching.contact_id == contact.id
        and matching.input_snapshot.get("score_id") == str(score.id)
    )
    if current:
        current = matching.input_snapshot.get("context_hash") == context_hash
    from app.models.automation import AutomationJob, ProductAutomationPlan

    plan = db.scalar(select(ProductAutomationPlan))
    related = select(LeadResearch.id).where(LeadResearch.lead_id == lead_id).union(
        select(PipelineRun.id).where(PipelineRun.lead_id == lead_id)
    )
    jobs = list(db.scalars(select(AutomationJob).where(
        AutomationJob.related_id.in_(related)
    ).order_by(AutomationJob.created_at.desc()).limit(15))) if plan else []
    from app.services.automation_status import current_job_ids, describe_job
    current_ids = current_job_ids(db, jobs) if jobs else set()
    return {
        "managed": bool(plan),
        "automation_enabled": bool(plan and plan.enabled),
        "automation_jobs": [
            {**describe_job(j, j.id in current_ids, bool(plan and plan.enabled)), "outcome": j.result.get("outcome")}
            for j in jobs
        ],
        "available": True,
        "contact_reviewed": reviewed(db, lead) if lead.primary_contact_id else False,
        "scored": scored,
        "matching_current": current,
        "draft_product_ids": [
            str(row.product_id)
            for row in db.scalars(
                select(ProductMatch).where(ProductMatch.lead_id == lead.id)
            )
            if current
            and any(
                m.get("id") == str(row.id) and m.get("fit_score", 0) > 0
                for m in matching.result.get("matches", [])
            )
        ],
    }


@router.get("/api/pipeline/health")
def health(db=Depends(get_db)):
    permit("SERVICE", "ADMIN")
    db.execute(select(PipelineRun.id).limit(1))
    return {"pipeline_version": 1}


@router.post("/api/pipeline/claim")
def claim(db=Depends(get_db)):
    principal = permit("SERVICE")
    from app.services.product_automation import managed

    if managed(db):
        return None
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:scope,0))"),
        {"scope": f"pipeline:{principal.workspace_id}"},
    )
    now = datetime.now(timezone.utc)
    for row in db.scalars(
        select(PipelineRun)
        .where(
            PipelineRun.status == "RUNNING",
            PipelineRun.started_at < now - timedelta(minutes=30),
        )
        .with_for_update()
    ):
        row.status = "FAILED"
        row.failure_reason = "WORKER_TIMEOUT"
        row.finished_at = now
    db.flush()
    if db.scalar(
        select(PipelineRun.id).where(PipelineRun.status == "RUNNING").limit(1)
    ):
        db.commit()
        return None
    run = db.scalar(
        select(PipelineRun)
        .where(PipelineRun.status == "PENDING")
        .order_by(PipelineRun.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if run:
        run.status = "RUNNING"
        run.claimed_by = principal.actor
        run.started_at = now
    db.commit()
    return run_read(run) if run else None


def owned_run(db, run_id, lock=False):
    principal = permit("SERVICE")
    statement = select(PipelineRun).where(PipelineRun.id == run_id)
    run = db.scalar(statement.with_for_update() if lock else statement)
    if not run:
        raise HTTPException(404, "Stage run not found")
    if run.claimed_by != principal.actor:
        raise HTTPException(409, "This stage belongs to another worker")
    return run


def context_for(db, run):
    lead = lead_for(db, run.lead_id)
    research = get_latest_usable_research(db, lead_id=lead.id)
    if (
        not research
        or research.id != run.research_id
        or lead.primary_contact_id != run.contact_id
    ):
        raise HTTPException(
            409, "Research or primary contact changed; request this stage again"
        )
    icp = db.get(ICPProfile, lead.icp_profile_id)
    contact = db.get(Contact, run.contact_id)
    if (
        not icp
        or not icp.active
        or not contact
        or contact.status != "ACTIVE"
        or contact.company_id != lead.company_id
        or not reviewed(db, lead)
    ):
        raise HTTPException(409, "Stage context is no longer active")
    if run.input_snapshot.get("context_hash") != fingerprint(db, lead, contact):
        raise HTTPException(
            409, "The contact or workspace catalog changed; request this stage again"
        )
    products = list(db.scalars(select(Product).where(Product.active.is_(True))))
    if not products or len(products) > 30:
        raise HTTPException(
            409, "Configure between one and thirty active catalog products"
        )
    score = db.scalar(
        select(LeadScore).where(
            LeadScore.lead_id == lead.id, LeadScore.is_current.is_(True)
        )
    )
    if run.stage in ("MATCHING", "DRAFTING") and (
        lead.status not in ("QUALIFIED", "READY_FOR_OUTREACH")
        or not score
        or str(score.id) != run.input_snapshot.get("score_id")
    ):
        raise HTTPException(
            409, "Qualification or score changed; request this stage again"
        )
    selected = next(
        (p for p in products if str(p.id) == run.input_snapshot.get("product_id")), None
    )
    if run.stage == "DRAFTING" and selected is None:
        raise HTTPException(409, "Selected product is no longer active")
    if run.stage == "DRAFTING":
        match = db.get(ProductMatch, UUID(run.input_snapshot["match_id"]))
        if (
            not match
            or match.lead_id != lead.id
            or match.product_id != selected.id
            or match.fit_score <= 0
            or match.fit_score != run.input_snapshot.get("match_fit")
            or match.rationale != run.input_snapshot.get("match_rationale")
        ):
            raise HTTPException(
                409, "The product match changed; request this stage again"
            )
    sources = list(
        db.scalars(
            select(ResearchSource).where(ResearchSource.research_id == research.id)
        )
    )
    return lead, research, contact, icp, products, score, sources


@router.get("/api/pipeline/{run_id}/context")
def context(run_id: UUID, db=Depends(get_db)):
    run = owned_run(db, run_id)
    if run.status != "RUNNING":
        raise HTTPException(409, "Stage is not running")
    lead, research, contact, icp, products, score, sources = context_for(db, run)
    return {
        "run": run_read(run),
        "input": run.input_snapshot,
        "lead": LeadRead.model_validate(lead),
        "company": CompanyRead.model_validate(db.get(Company, lead.company_id)),
        "contact": ContactRead.model_validate(contact),
        "research": ResearchRead.model_validate(research),
        "icp": {
            "id": str(icp.id),
            "code": icp.code,
            "name": icp.name,
            "description": icp.description,
            "qualification_rules": icp.qualification_rules,
        },
        "rubric": scoring_rubric(icp),
        "products": [
            {
                "id": str(p.id),
                "code": p.code,
                "name": p.name,
                "description": p.description,
                "category": p.category,
            }
            for p in products
        ],
        "score": (
            {
                "id": str(score.id),
                "total_score": score.total_score,
                "rationale": score.rationale,
            }
            if score
            else None
        ),
        "sources": [
            {"url": s.url, "evidence": (s.evidence or "")[:4000], "title": s.title}
            for s in sources[:30]
        ],
    }


def verify_evidence(evidence, sources):
    by_url = {source.url: source.evidence for source in sources}
    for item in evidence:
        if item.source_url not in by_url or normalized(
            item.evidence_quote
        ) not in normalized(by_url[item.source_url]):
            raise HTTPException(
                422, "The stage output cites unsupported research evidence"
            )


@router.patch("/api/pipeline/{run_id}/complete")
def complete(run_id: UUID, data: Complete, db=Depends(get_db)):
    run = owned_run(db, run_id, lock=True)
    if run.status == "COMPLETED":
        return run_read(run)
    if run.status != "RUNNING":
        raise HTTPException(409, "Stage is not running")
    lead, research, contact, icp, products, score, sources = context_for(db, run)
    try:
        if run.stage == "SCORING":
            output = ScoringOutput.model_validate(data.output)
            rubric = scoring_rubric(icp)
            if {c.criterion: c.max_points for c in output.components} != {
                r["criterion"]: r["max_points"] for r in rubric
            } or len({c.criterion for c in output.components}) != len(
                output.components
            ):
                raise HTTPException(
                    422, "Score criteria must be distinct and total 100 possible points"
                )
            for component in output.components:
                if component.points > component.max_points or (
                    component.points > 0 and not component.evidence
                ):
                    raise HTTPException(
                        422,
                        "Positive score points require evidence and cannot exceed their weight",
                    )
                verify_evidence(component.evidence, sources)
            total = sum(c.points for c in output.components)
            saved = create_score(
                db,
                lead_id=lead.id,
                data=ScoreCreate(
                    total_score=total,
                    score_breakdown={
                        "components": [c.model_dump() for c in output.components],
                        "rubric": rubric,
                        "gaps": output.gaps,
                        "opportunity": {
                            "status": "SIGNAL_REQUIRES_REVIEW" if any(c.criterion == "buying_signals" and c.points > 0 for c in output.components) else "UNCONFIRMED",
                            "explanation": "A preparation score measures documented fit. It does not establish purchase intent or a need to replace existing systems.",
                        },
                        "research_id": str(research.id),
                        "contact_id": str(contact.id),
                        "context_hash": run.input_snapshot["context_hash"],
                    },
                    scoring_version="workspace-evidence-v1",
                    rationale=output.rationale,
                ),
                commit=False,
            )
            result = {
                "score_id": str(saved.id),
                "total_score": total,
                "gaps": output.gaps,
            }
        elif run.stage == "MATCHING":
            output = MatchingOutput.model_validate(data.output)
            catalog = {p.code: p for p in products}
            if len({m.product_code for m in output.matches}) != len(
                output.matches
            ) or any(m.product_code not in catalog for m in output.matches):
                raise HTTPException(
                    422,
                    "Product matches must use distinct current workspace catalog codes",
                )
            result = {"matches": []}
            for match in output.matches:
                if match.fit_score > 0 and not match.evidence:
                    raise HTTPException(422, "Positive product fit requires evidence")
                verify_evidence(match.evidence, sources)
            for match in output.matches:
                saved, _ = upsert_product_match(
                    db,
                    lead_id=lead.id,
                    data=ProductMatchCreate(
                        product_id=catalog[match.product_code].id,
                        fit_score=match.fit_score,
                        rationale=match.rationale,
                    ),
                    commit=False,
                )
                result["matches"].append(
                    {
                        "id": str(saved.id),
                        "product_code": match.product_code,
                        "fit_score": match.fit_score,
                        "evidence": [e.model_dump() for e in match.evidence],
                    }
                )
        else:
            output = DraftOutput.model_validate(data.output)
            if re.search(r"\b(?:will (?:further )?(?:improve|reduce|increase|save|boost)|can further improve|guarantee(?:d)?|double your|cut your costs)\b", output.subject + " " + output.content, re.I):
                raise HTTPException(422, "The draft promises an unsupported outcome. Use neutral, exploratory language.")
            verify_evidence(output.evidence, sources)
            channel = run.input_snapshot["channel"]
            action = create_action(
                db,
                lead_id=lead.id,
                data=MarketingActionCreate(
                    contact_id=contact.id,
                    channel=channel,
                    action_type="EMAIL" if channel == "EMAIL" else "DIRECT_MESSAGE",
                    subject=output.subject,
                    content=output.content,
                    created_by=run.requested_by,
                ),
                commit=False,
            )
            approval = submit_action_for_approval(db, action_id=action.id, commit=False)
            result = {
                "action_id": str(action.id),
                "approval_id": str(approval["id"]),
                "product_id": run.input_snapshot["product_id"],
                "channel": channel,
                "evidence": [e.model_dump() for e in output.evidence],
            }
        run.result = result
        run.status = "COMPLETED"
        run.finished_at = datetime.now(timezone.utc)
        audit(
            db,
            "lead_stage_completed",
            lead,
            stage=run.stage,
            run_id=str(run.id),
            result=result,
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        # Do not expose model payloads or provider messages in API errors.
        from pydantic import ValidationError

        if isinstance(exc, ValidationError):
            raise HTTPException(422, "Invalid structured stage output") from None
        if isinstance(exc, (ValueError, IntegrityError)):
            raise HTTPException(
                409,
                "Stage prerequisites changed or output conflicts with existing records",
            ) from None
        raise
    return run_read(run)


@router.patch("/api/pipeline/{run_id}/fail")
def fail(run_id: UUID, data: Failure, db=Depends(get_db)):
    run = owned_run(db, run_id, lock=True)
    if run.status == "FAILED":
        return run_read(run)
    if run.status != "RUNNING":
        raise HTTPException(409, "Stage is not running")
    run.status = "FAILED"
    run.failure_reason = data.reason
    run.finished_at = datetime.now(timezone.utc)
    db.commit()
    return run_read(run)
