"""Shared, product-driven native preparation handlers. No approval or sending handler."""

import re
from urllib.parse import urljoin, urlsplit, urlunsplit
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from .db import Session
from .models import PreparationRun, DiscoveryMemory, Lead
from .pipeline import domain
from .providers import Providers
from .research import PageText, normalize, ProviderFailure
from .public_fetch import fetch_public, FetchError, checked_url


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Citation(Strict):
    source_url: str = Field(min_length=8, max_length=1500)
    evidence_quote: str = Field(min_length=8, max_length=500)


class Finding(Citation):
    category: Literal[
        "COMPANY",
        "INDUSTRY",
        "SERVICES",
        "FLEET",
        "TECHNOLOGY",
        "LOCATION",
        "PAIN_POINT",
        "SIGNAL",
    ]
    statement: str = Field(min_length=8, max_length=1000)
    confidence: int = Field(ge=0, le=100, strict=True)
    kind: Literal["OBSERVED", "INFERRED"]


class Person(Citation):
    name: str = Field(min_length=3, max_length=150)
    role: str = Field(min_length=2, max_length=200)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=80)


class ResearchOutput(Strict):
    facts: list[Finding] = Field(max_length=30)
    people: list[Person] = Field(max_length=5)
    unknowns: list[str] = Field(max_length=20)


MAX_RESEARCH_PEOPLE = 5


class ICPInput(Strict):
    code: str = Field(pattern=r"^[A-Z0-9_]+$", max_length=80)
    name: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=15, max_length=2000)


class SetupOutput(Strict):
    discovery_query: str = Field(min_length=3, max_length=300)
    icps: list[ICPInput] = Field(max_length=5)


class Candidate(Citation):
    company_name: str = Field(min_length=2, max_length=200)
    icp_code: str = Field(max_length=80)
    confidence: int = Field(ge=75, le=100, strict=True)
    official_company: Literal[True]


class DiscoveryOutput(Strict):
    candidates: list[Candidate] = Field(max_length=10)


class Criterion(Strict):
    criterion: str = Field(max_length=60)
    points: int = Field(ge=0, le=100, strict=True)
    rationale: str = Field(min_length=8, max_length=1000)
    evidence: list[Citation] = Field(max_length=5)


class ScoreOutput(Strict):
    criteria: list[Criterion] = Field(min_length=1, max_length=10)
    unknowns: list[str] = Field(max_length=20)


class ProductMatch(Strict):
    product_code: str = Field(max_length=80)
    fit: int = Field(ge=0, le=100, strict=True)
    rationale: str = Field(min_length=8, max_length=1000)
    evidence: list[Citation] = Field(max_length=5)


class MatchOutput(Strict):
    matches: list[ProductMatch] = Field(max_length=30)


class DraftOutput(Strict):
    subject: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=30, max_length=3000)
    evidence: list[Citation] = Field(min_length=1, max_length=10)


def validated(schema, raw):
    try:
        return schema.model_validate(raw).model_dump()
    except (ValueError, TypeError):
        raise ProviderFailure("MODEL_OUTPUT_SCHEMA_INVALID") from None


def cite(value, pages):
    page = next((p for p in pages if p["source_url"] == value["source_url"]), None)
    if not page or normalize(value["evidence_quote"]) not in normalize(page["text"]):
        raise ProviderFailure("UNSUPPORTED_CITATION")


def evidence_pages(pages):
    # Navigation links are crawl checkpoints, not model evidence or dashboard output.
    return [
        {k: p[k] for k in ("source_url", "text", "unavailable") if k in p}
        for p in pages
    ]


def result(job, kind):
    with Session() as db:
        run = db.scalar(
            select(PreparationRun).where(
                PreparationRun.id == job.run_id,
                PreparationRun.workspace_id == job.workspace_id,
            )
        )
        if not run or kind not in run.results:
            raise ProviderFailure("MISSING_STAGE_INPUT")
        return run.results[kind]


class Links(PageText):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        super().handle_starttag(tag, attrs)
        if tag == "a":
            href = dict(attrs).get("href", "")
            if isinstance(href, str) and 0 < len(href) <= 1500:
                self.links.append(href)


def page(providers, url):
    key = "page:" + url
    if key in providers.cache:
        return providers.cache[key]
    existing = sum(k.startswith("page:") for k in providers.cache)
    if existing >= 10:
        raise ProviderFailure("FETCH_PAGE_LIMIT")
    try:
        fetched = fetch_public(url)
        if fetched["fetch_status"] != "SUCCESS":
            raise FetchError("UNAVAILABLE")
        from .scraping import readable

        parser = Links()
        parser.feed(fetched["body"])
        value = {
            "source_url": fetched["final_url"],
            "text": readable(fetched["body"])
            or normalize(" ".join(parser.parts))[:12000],
            "links": parser.links[:100],
        }
    except FetchError:
        value = {"source_url": url, "text": "", "links": [], "unavailable": True}
    return providers.remember(key, value)


def setup(job, providers):
    catalog = job.payload["context"]["catalog"]
    value = validated(
        SetupOutput,
        providers.model(
            "setup",
            "Prepare targeting from the real catalog and product description. Never invent capabilities. Search for companies that could buy the product: actual fleet operators, logistics/transport service providers, or businesses that operate/manage transport. Exclude software/platform vendors, consultants and technology suppliers that sell to those companies. Search observable customer business types and geography, not hypothetical buying needs. Return discovery_query and icps (code,name,description), at most five. Preserve existing ICPs by returning an empty icps array when ICPs already exist.",
            job.payload["context"],
        ),
    )
    if any(c["kind"] == "ICP" for c in catalog):
        value["icps"] = []
    elif not value["icps"]:
        raise ProviderFailure("TARGETING_EMPTY")
    if len({c["code"] for c in value["icps"]}) != len(value["icps"]):
        raise ProviderFailure("DUPLICATE_ICP")
    return value


def discovery(job, providers):
    from .discovery import discover

    return discover(job, providers)


def research(job, providers):
    homepage = page(providers, job.payload["website"])
    if len(homepage["text"]) < 100:
        return {
            "facts": [],
            "people": [],
            "pages": [homepage],
            "unknowns": ["Website unavailable or insufficient public evidence"],
            "stop_reason": "INSUFFICIENT_COMPANY_EVIDENCE",
        }
    pages = [homepage]
    urls = set([homepage["source_url"]])
    links = sorted(
        homepage["links"],
        key=lambda u: (
            0 if re.search(r"contact|team|leadership|management", u, re.I) else 1
        ),
    )
    for link in links:
        url = urljoin(homepage["source_url"], link)
        parsed = urlsplit(url)
        url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
        if (
            domain(url) != domain(homepage["source_url"])
            or url in urls
            or not re.search(
                r"about|service|contact|team|leadership|management|fleet|solution",
                url,
                re.I,
            )
        ):
            continue
        urls.add(url)
        pages.append(page(providers, url))
        if len(pages) == 6:
            break
    pages = evidence_pages(pages)
    identity = company_tokens(job.payload["company_name"])
    if not identity or not any(
        all(t in re.findall(r"[\w]+", p["text"].lower()) for t in identity)
        for p in pages
    ):
        return {
            "facts": [],
            "people": [],
            "pages": pages,
            "unknowns": [
                "Company identity was not supported by fetched official pages"
            ],
            "stop_reason": "COMPANY_IDENTITY_UNCONFIRMED",
        }
    raw = providers.model(
        "research",
        "Research only supplied official pages. Return facts(category,statement,source_url,evidence_quote,confidence integer0-100,kind OBSERVED/INFERRED), people(name,role,email optional,phone optional,source_url,evidence_quote), unknowns. Return at most five people, prioritizing named decision-makers and operational leaders. Categories COMPANY,INDUSTRY,SERVICES,FLEET,TECHNOLOGY,LOCATION,PAIN_POINT,SIGNAL. Copy exact contiguous quotes. Existing systems are not unmet needs or buying intent. Industry is a concise supported label. Only extract named public business people with a sourced role. Never infer email addresses or phone numbers. Do not invent claims.",
        {
            "company": job.payload["company_name"],
            "context": job.payload["context"],
            "pages": pages,
        },
    )
    # Contact extraction is advisory. A single incomplete contact (for
    # example, a null role) must not invalidate otherwise useful company
    # research. Validate each contact independently, then strictly validate
    # the remaining response and keep the model's original contact ordering.
    omitted_people = 0
    if isinstance(raw, dict) and isinstance(raw.get("people"), list):
        people = []
        for index, person in enumerate(raw["people"]):
            if len(people) >= MAX_RESEARCH_PEOPLE:
                omitted_people += len(raw["people"]) - index
                break
            try:
                people.append(Person.model_validate(person).model_dump())
            except (ValueError, TypeError):
                omitted_people += 1
        raw = {**raw, "people": people}
    value = validated(ResearchOutput, raw)

    # Evidence errors on one generated item must not discard every other
    # source-backed finding. Drop unsupported facts/people and report the gap.
    supported_facts = []
    omitted_facts = 0
    for fact in value["facts"]:
        try:
            cite(fact, pages)
        except ProviderFailure:
            omitted_facts += 1
            continue
        supported_facts.append(fact)
    supported_people = []
    for person in value["people"]:
        try:
            cite(person, pages)
        except ProviderFailure:
            omitted_people += 1
            continue
        quote = normalize(person["evidence_quote"]).lower()
        if (
            normalize(person["name"]).lower() not in quote
            or normalize(person["role"]).lower() not in quote
        ):
            omitted_people += 1
            continue
        for field in ("email", "phone"):
            if person[field] and normalize(person[field]).lower() not in quote:
                person[field] = None
        if person["email"] and not re.fullmatch(
            r"[^\s@]+@[^\s@]+\.[^\s@]+", person["email"]
        ):
            person["email"] = None
        supported_people.append(person)
    value["facts"] = supported_facts
    value["people"] = supported_people
    omissions = []
    if omitted_facts:
        omissions.append(
            "Some generated company facts were omitted because their exact source text could not be verified."
        )
    if omitted_people:
        omissions.append(
            "Some generated contacts were omitted or capped because their source, name, role, or contact details could not be verified."
        )
    if omissions:
        value["unknowns"] = [*value["unknowns"][:18], *omissions]
    value["pages"] = pages
    value["industry"] = next(
        (
            f
            for f in value["facts"]
            if f["category"] == "INDUSTRY"
            and f["confidence"] >= 75
            and f["kind"] == "OBSERVED"
        ),
        None,
    )
    value["coverage"] = {
        "pages_attempted": len(pages),
        "unavailable_pages": sum(bool(p.get("unavailable")) for p in pages),
    }
    return value


def company_tokens(name):
    return [
        w
        for w in re.findall(r"[\w]+", name.lower())
        if w
        not in ("sdn", "bhd", "ltd", "limited", "inc", "corp", "company", "llc", "pte")
    ]


def contacts(job, providers):
    research = result(job, "RESEARCH")
    people = []
    unavailable = 0
    for index, original in enumerate(research["people"]):
        person = {**original, "profiles": [], "profile_candidates": []}
        for label, query in [
            (
                "linkedin",
                f'"{person["name"]}" "{job.payload["company_name"]}" site:linkedin.com/in',
            ),
            (
                "professional",
                f'"{person["name"]}" "{job.payload["company_name"]}" "{person["role"]}" (site:x.com OR site:github.com OR site:instagram.com)',
            ),
        ]:
            try:
                rows = providers.search(f"person-{index}-{label}", query)
            except ProviderFailure as exc:
                if exc.code not in ("SEARCH_UNAVAILABLE", "SEARCH_TRANSPORT_ERROR"):
                    raise
                unavailable += 1
                continue
            found = {}
            for row in rows:
                title = normalize(row["title"]).lower()
                text = normalize(row["title"] + " " + row["text"]).lower()
                parsed = urlsplit(row["url"])
                host = domain(row["url"])
                allowed = (
                    (host == "linkedin.com" and parsed.path.startswith("/in/"))
                    if label == "linkedin"
                    else host in ("x.com", "twitter.com", "github.com", "instagram.com")
                )
                if (
                    not allowed
                    or parsed.username
                    or parsed.password
                    or parsed.scheme not in ("http", "https")
                    or normalize(person["name"]).lower() not in title
                    or not all(
                        t in re.findall(r"[\w]+", text)
                        for t in company_tokens(job.payload["company_name"])
                    )
                ):
                    continue
                if (
                    label != "linkedin"
                    and normalize(person["role"]).lower() not in text
                ):
                    continue
                if label != "linkedin" and (
                    len(parsed.path.strip("/").split("/")) != 1
                    or parsed.path.strip("/").lower()
                    in ("about", "login", "features", "explore", "search")
                ):
                    continue
                url = urlunsplit(
                    ("https", parsed.hostname, parsed.path.rstrip("/"), "", "")
                )
                found[url] = {
                    "url": url,
                    "platform": host,
                    "source_url": row["url"],
                    "evidence_quote": row["title"] + " " + row["text"],
                    "basis": "PUBLIC_NAME_COMPANY_MATCH",
                }
            values = list(found.values())
            person["profile_candidates"].extend(values)
            if len(values) == 1:
                person["profiles"].extend(values)
        people.append(person)
    chosen = next(
        (
            p
            for p in people
            if p["email"] or any(v["platform"] == "linkedin.com" for v in p["profiles"])
        ),
        None,
    )
    return {
        "people": people,
        "selected_contact": chosen,
        "unavailable_queries": unavailable,
        "stop_reason": (
            None
            if chosen
            else (
                "CONTACT_SEARCH_UNAVAILABLE"
                if unavailable
                else "SUPPORTED_CONTACT_REQUIRED"
            )
        ),
    }


DEFAULT_RUBRIC = [
    ("icp_fit", 40),
    ("operational_need", 30),
    ("operating_scale", 15),
    ("buying_signals", 10),
    ("evidence_quality", 5),
]


def rubric(job):
    icps = [c for c in job.payload["context"]["catalog"] if c["kind"] == "ICP"]
    rules = next(c for c in icps if c["code"] == job.payload["icp_code"]).get(
        "rules", {}
    )
    raw = rules.get("scoring_rubric") or rules.get("qualification_rules", {}).get(
        "scoring_rubric"
    )
    if not raw:
        return dict(DEFAULT_RUBRIC)
    try:
        values = {v["criterion"]: v["max_points"] for v in raw}
        if (
            not 1 <= len(raw) <= 10
            or len(values) != len(raw)
            or sum(values.values()) != 100
            or any(type(v) != int or v <= 0 for v in values.values())
            or any(not re.fullmatch("[a-z][a-z0-9_]{0,59}", k) for k in values)
        ):
            raise ValueError()
        return values
    except (ValueError, KeyError, TypeError):
        raise ProviderFailure("SCORING_RUBRIC_INVALID") from None


def normalize_score_output(raw, limits):
    """Normalize bounded response-shape variations from compatible models.

    Keep validation strict: keyed criteria must exactly match the active rubric;
    citation ``quote`` is accepted as an alias for ``evidence_quote``. All
    normalized fields still pass the same Pydantic and citation checks below.
    """
    if not isinstance(raw, dict) or "criteria" in raw:
        candidate = raw
    else:
        criterion_keys = set(raw) - {"unknowns"}
        if criterion_keys != set(limits):
            return raw
        criteria = []
        for criterion in limits:
            item = raw[criterion]
            if not isinstance(item, dict):
                return raw
            criteria.append({"criterion": criterion, **item})
        candidate = {"criteria": criteria, "unknowns": raw.get("unknowns", [])}

    if not isinstance(candidate, dict) or not isinstance(
        candidate.get("criteria"), list
    ):
        return candidate
    normalized = []
    for criterion in candidate["criteria"]:
        if not isinstance(criterion, dict) or not isinstance(
            criterion.get("evidence"), list
        ):
            normalized.append(criterion)
            continue
        citations = []
        for evidence in criterion["evidence"]:
            if (
                isinstance(evidence, dict)
                and "quote" in evidence
                and "evidence_quote" not in evidence
            ):
                evidence = {**evidence, "evidence_quote": evidence["quote"]}
                evidence.pop("quote")
            citations.append(evidence)
        normalized.append({**criterion, "evidence": citations})
    return {
        **candidate,
        "criteria": normalized,
        "unknowns": candidate.get("unknowns", []),
    }


def scoring(job, providers):
    research = result(job, "RESEARCH")
    limits = rubric(job)
    raw = providers.model(
        "scoring",
        "Score against the supplied rubric and ICPs. Return JSON with this exact shape: "
        '{"criteria":[{"criterion":"icp_fit","points":0,"rationale":"...",'
        '"evidence":[{"source_url":"https://...","evidence_quote":"exact source text"}]}],'
        '"unknowns":[]}. Include one criteria array item per rubric criterion and use its '
        "exact code. Citation objects must use source_url and evidence_quote. Do not "
        "return criterion codes as object keys. "
        "Every positive component requires exact saved citations. Operational need requires "
        "an observed PAIN_POINT; buying signals require an observed SIGNAL. Existing "
        "technology and capabilities are not unmet needs or buying intent. Unknown "
        "evidence earns zero.",
        {
            "context": job.payload["context"],
            "selected_icp": job.payload["icp_code"],
            "rubric": limits,
            "research": research,
        },
    )
    value = validated(
        ScoreOutput,
        normalize_score_output(raw, limits),
    )
    if len(value["criteria"]) != len(limits) or {
        v["criterion"] for v in value["criteria"]
    } != set(limits):
        raise ProviderFailure("SCORING_RUBRIC_INVALID")
    adjustments = []
    for item in value["criteria"]:
        if item["points"] > limits[item["criterion"]] or (
            item["points"] and not item["evidence"]
        ):
            raise ProviderFailure("SCORING_EVIDENCE_REQUIRED")
        for evidence in item["evidence"]:
            cite(evidence, research["pages"])
        category = {"operational_need": "PAIN_POINT", "buying_signals": "SIGNAL"}.get(
            item["criterion"]
        )
        supported = any(
            f["kind"] == "OBSERVED"
            and f["category"] == category
            and f["source_url"] == e["source_url"]
            and normalize(e["evidence_quote"]) in normalize(f["evidence_quote"])
            for f in research["facts"]
            for e in item["evidence"]
        )
        if category and item["points"] and not supported:
            adjustments.append(item["criterion"])
            item["points"] = 0
            item["rationale"] += " Adjusted to zero: no observed opportunity evidence."
    value["score"] = sum(c["points"] for c in value["criteria"])
    value["relevance"] = sum(
        c["points"]
        for c in value["criteria"]
        if c["criterion"] not in ("operational_need", "buying_signals")
    )
    value["opportunity"] = sum(
        c["points"]
        for c in value["criteria"]
        if c["criterion"] in ("operational_need", "buying_signals")
    )
    value["adjustments"] = adjustments
    fit = next(
        (c["points"] for c in value["criteria"] if c["criterion"] == "icp_fit"), 0
    )
    value["stop_reason"] = (
        None if value["score"] >= 60 and fit > 0 else "QUALIFICATION_BELOW_POLICY"
    )
    return value


def matching(job, providers):
    research = result(job, "RESEARCH")
    products = {
        c["code"]: c
        for c in job.payload["context"]["catalog"]
        if c["kind"] == "PRODUCT"
    }
    value = validated(
        MatchOutput,
        providers.model(
            "matching",
            "Match only supplied real active products. Return matches(product_code,fit integer0-100,rationale,evidence array source_url/evidence_quote). Positive fit needs saved evidence and documented product capability. Capability relevance is not buying opportunity. No invented offerings or improvements.",
            {
                "products": products,
                "research": research,
                "score": result(job, "SCORING"),
            },
        ),
    )
    if len({m["product_code"] for m in value["matches"]}) != len(value["matches"]):
        raise ProviderFailure("DUPLICATE_PRODUCT_MATCH")
    for item in value["matches"]:
        if item["product_code"] not in products or (
            item["fit"] and not item["evidence"]
        ):
            raise ProviderFailure("PRODUCT_NOT_SUPPORTED")
        for evidence in item["evidence"]:
            cite(evidence, research["pages"])
    suitable = sorted(
        [m for m in value["matches"] if m["fit"] >= 60],
        key=lambda m: (-m["fit"], m["product_code"]),
    )
    value["selected_product"] = suitable[0]["product_code"] if suitable else None
    value["stop_reason"] = None if suitable else "NO_SUPPORTED_PRODUCT_MATCH"
    return value


def drafting(job, providers):
    research = result(job, "RESEARCH")
    contact = result(job, "CONTACT_SEARCH")["selected_contact"]
    code = result(job, "MATCHING")["selected_product"]
    product = next(
        c
        for c in job.payload["context"]["catalog"]
        if c["kind"] == "PRODUCT" and c["code"] == code
    )
    channel = "EMAIL" if contact.get("email") else "LINKEDIN"
    recipient = (
        contact.get("email")
        if channel == "EMAIL"
        else next(
            (p["url"] for p in contact["profiles"] if p["platform"] == "linkedin.com"),
            None,
        )
    )
    if not recipient:
        raise ProviderFailure("SUPPORTED_CONTACT_REQUIRED")
    value = validated(
        DraftOutput,
        providers.model(
            "drafting",
            "Prepare one concise professional outreach draft for human approval. Return subject,body,evidence array of exact source_url/evidence_quote for company claims. Use real product capability and supplied voice/language. Acknowledge relevant existing systems. Ask a relevant exploratory question when needs are unknown. Do not invent problems, guarantees, improvements, prices or sender identity. Avoid generic repetitive introductions. Do not claim you will reduce costs or replace their current system.",
            {
                "product": product,
                "contact": contact,
                "channel": channel,
                "research": research,
                "score": result(job, "SCORING"),
                "preferences": job.payload["context"]["preferences"],
            },
        ),
    )
    for evidence in value["evidence"]:
        cite(evidence, research["pages"])
    if re.search(
        r"guarantee|will reduce|will save|replace your current", value["body"], re.I
    ):
        raise ProviderFailure("DRAFT_UNSUPPORTED_PROMISE")
    value.update(
        channel=channel,
        recipient=recipient,
        product_code=code,
        status="PENDING_APPROVAL",
    )
    return value


HANDLERS = {
    "SETUP": setup,
    "DISCOVERY": discovery,
    "RESEARCH": research,
    "CONTACT_SEARCH": contacts,
    "SCORING": scoring,
    "MATCHING": matching,
    "DRAFTING": drafting,
}


def dispatch(job, save):
    if job.kind not in HANDLERS:
        raise ProviderFailure("UNSUPPORTED_JOB_KIND")
    providers = Providers(job, save)
    providers.ready(
        search=job.kind == "CONTACT_SEARCH"
        or (job.kind == "DISCOVERY" and not job.payload.get("retry_domain"))
    )
    return HANDLERS[job.kind](job, providers)
