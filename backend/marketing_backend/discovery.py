
"""Brave discovery, bounded Python crawling and evidence-backed xKiro assessment."""

import re
from typing import Literal
from urllib.parse import urljoin, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from .db import Session
from .models import DiscoveryMemory, Lead, now
from .pipeline import domain
from .research import ProviderFailure, normalize
from .public_fetch import checked_url, FetchError


DIRECTORIES = {
    "ensun.io",
    "clutch.co",
    "goodfirms.co",
    "yellowpages.my",
    "zoominfo.com",
    "crunchbase.com",
    "yelp.com",
    "tracxn.com",
    "lusha.com",
    "mordorintelligence.com",
}

SOCIAL = {
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "youtube.com",
}

COUNTRY_NAMES = {
    "MY": "Malaysia",
    "SG": "Singapore",
    "ID": "Indonesia",
    "TH": "Thailand",
    "PH": "Philippines",
    "VN": "Vietnam",
    "BN": "Brunei",
    "US": "United States",
    "GB": "United Kingdom",
    "AU": "Australia",
}

# Existing classifications remain supported for backward compatibility.
# PRODUCT_BUYER supports buyers of non-transport product lines.
ELIGIBLE_PROSPECT_TYPES = {
    "FLEET_OPERATOR",
    "LOGISTICS_PROVIDER",
    "TRANSPORT_BUYER",
    "PRODUCT_BUYER",
}

REJECTED_PROSPECT_TYPES = {
    "SOFTWARE_VENDOR",
    "CONSULTANT",
    "OTHER",
    "UNKNOWN",
}

ASSESSMENT_INSTRUCTIONS = (
    "Assess ONE company's public evidence against the actual workspace "
    "catalog, products and Ideal Customer Profiles (ICPs). "
    "Evaluate the company as a potential customer of the configured "
    "product line, not as a customer of a hardcoded industry. "
    "A cosmetics workspace must be assessed using its cosmetics product "
    "and ICP context, while a transport workspace must be assessed using "
    "its transport product and ICP context. "
    "Never reuse a different product line's target customer requirements. "

    "Return exactly one JSON object with every required key: "
    "suitable (boolean), prospect_type (string), company_name (string), "
    "icp_code (string), confidence (integer 0-100), "
    "official_company (boolean), excerpt_id (string), "
    "industry (string), reasoning (string), unknowns (array of strings). "
    "Do not omit fields or use markdown. "

    "prospect_type must be one of: "
    "FLEET_OPERATOR, LOGISTICS_PROVIDER, TRANSPORT_BUYER, "
    "PRODUCT_BUYER, SOFTWARE_VENDOR, CONSULTANT, OTHER, UNKNOWN. "

    "FLEET_OPERATOR means a company operating or managing vehicles "
    "to provide commercial transport or passenger services. "
    "LOGISTICS_PROVIDER means a company providing transport, "
    "haulage or third-party logistics services itself. "
    "TRANSPORT_BUYER means a manufacturer, distributor, retailer "
    "or other business whose public evidence establishes that it "
    "operates or manages its own delivery or transport operations. "

    "PRODUCT_BUYER means a business with evidence-supported activities "
    "matching the configured product's actual ICP, where an existing "
    "transport-specific category is not appropriate. "
    "For example, a cosmetics retailer may be a PRODUCT_BUYER "
    "when its public evidence establishes the retail activities "
    "required by a cosmetics product's selected ICP. "
    "Do not assign PRODUCT_BUYER merely because a company operates "
    "in the same broad industry. "

    "SOFTWARE_VENDOR means a business whose relevant offering is "
    "software or a platform sold to the target industry rather than "
    "the actual operating or buying role requested by the selected ICP. "
    "CONSULTANT means a business providing advisory or consulting "
    "services instead of performing the selected customer role. "
    "Classify unrelated businesses as OTHER or UNKNOWN. "

    "Select icp_code from the actual ICP codes supplied in the context. "
    "Do not invent an ICP or select one belonging to another workspace. "
    "Only set suitable=true when the company's public evidence supports "
    "its business identity, its classified role, and its relevance "
    "to the selected product and ICP. "
    "If the evidence is insufficient, set suitable=false, "
    "use OTHER or UNKNOWN as appropriate, and describe missing "
    "information in unknowns. "

    "Select an existing excerpt_id from the supplied excerpts. "
    "The chosen excerpt must contain the exact company name "
    "and support the company's relevant business activities. "
    "Do not fabricate evidence, company capabilities, contacts, "
    "operating scale or buying intent. "
    "Confidence must reflect the strength of the available evidence. "
    "Assess potential customer relevance, not proof that the company "
    "wants to purchase immediately. "

    "All suitable companies are recommendations for human review only. "
    "Do not automatically accept leads or authorize outreach."
)


def blocked(host):
    return any(
        host == h or host.endswith("." + h)
        for h in DIRECTORIES | SOCIAL
    )


def listing(row):
    try:
        checked_url(row.get("url", ""))
    except (FetchError, ValueError, TypeError, AttributeError):
        return True

    return blocked(domain(row.get("url", ""))) or bool(
        re.search(
            r"\b(top\s+\d+|best\s+\d+|list of companies|companies in|company directory)\b",
            (
                row.get("title", "")
                + " "
                + urlsplit(row.get("url", "")).path
            ).lower(),
        )
    )


def search_query(query, known):
    # Preserve existing query length and provider budget limits.
    # Domain exclusions originate from validated workspace domains.
    query = " ".join(str(query).split())[:300]
    query = " ".join(query.split()[:35])

    for suffix in [
        "official company website",
        *[
            "-site:" + h
            for h in sorted(known)[:20]
            if re.fullmatch(r"[a-z0-9.-]+", h) and "." in h
        ],
        "-site:ensun.io",
        "-site:clutch.co",
    ]:
        trial = query + " " + suffix

        if len(trial) <= 400 and len(trial.split()) <= 50:
            query = trial

    return query


def discovery_queries(original, catalog, country, known):
    """
    Generate product-neutral discovery queries from the configured
    discovery target, ICP names, and country.

    Do not inject transport terminology into unrelated product lines.
    """
    country_name = COUNTRY_NAMES.get(country.upper(), country)

    profiles = [
        item
        for item in catalog
        if item["kind"] == "ICP"
    ]

    # Keep geography explicit even when the search provider
    # also receives the country parameter.
    raw = [
        f"{original} {country_name} company"
    ]

    if profiles:
        midpoint = (len(profiles) + 1) // 2

        groups = (
            profiles[:midpoint],
            profiles[midpoint:],
        )

        for group in groups:
            if group:
                labels = " OR ".join(
                    item["name"] for item in group
                )

                raw.append(
                    f"{country_name} ({labels}) company"
                )

    return list(
        dict.fromkeys(
            search_query(query, known)
            for query in raw
        )
    )[:3]


def excluded(memory, context_hash):
    if memory.outcome in {
        "KNOWN",
        "ACCEPTED",
        "REJECTED",
    }:
        return True

    if memory.context_hash != context_hash:
        return False

    return (
        memory.outcome == "READY_FOR_REVIEW"
        or bool(
            memory.retry_after
            and memory.retry_after > now()
        )
    )


class Assessment(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    suitable: bool = Field(strict=True)

    # Keep existing classifications and add the generic buyer type.
    prospect_type: Literal[
        "FLEET_OPERATOR",
        "LOGISTICS_PROVIDER",
        "TRANSPORT_BUYER",
        "PRODUCT_BUYER",
        "SOFTWARE_VENDOR",
        "CONSULTANT",
        "OTHER",
        "UNKNOWN",
    ]

    company_name: str = Field(min_length=2, max_length=200)
    icp_code: str = Field(min_length=1, max_length=80)
    confidence: int = Field(ge=0, le=100, strict=True)
    official_company: bool = Field(strict=True)
    excerpt_id: str = Field(max_length=30)
    industry: str = Field(min_length=2, max_length=150)
    reasoning: str = Field(min_length=15, max_length=1500)
    unknowns: list[str] = Field(max_length=10)


def excerpts(pages):
    result = []

    for index, page in enumerate(pages):
        text = page["text"][:6000]

        for offset in range(0, len(text), 800):
            value = text[offset:offset + 1000]

            if len(value) >= 40:
                result.append(
                    {
                        "excerpt_id": (
                            f"P{index + 1}_E{offset // 800 + 1}"
                        ),
                        "source_url": page["source_url"],
                        "text": value,
                    }
                )

    return result


def assess(raw, sources, icps, host):
    """
    Validate model output using the existing evidence rules.

    Accept transport buyers and generic product buyers only when
    model suitability, ICP membership, official company evidence,
    and confidence checks succeed.

    This function proposes candidates; it never accepts leads.
    """
    try:
        value = Assessment.model_validate(raw).model_dump()
    except (ValueError, TypeError):
        raise ProviderFailure(
            "MODEL_OUTPUT_SCHEMA_INVALID"
        ) from None

    source = next(
        (
            s
            for s in sources
            if s["excerpt_id"] == value["excerpt_id"]
        ),
        None,
    )

    if (
        not source
        or domain(source["source_url"]) != host
        or normalize(value["company_name"]).lower()
        not in normalize(source["text"]).lower()
        or value["icp_code"] not in icps
        or not value["official_company"]
    ):
        raise ProviderFailure("CANDIDATE_NOT_SUPPORTED")

    # Exclude software vendors, consultants, unrelated and unknown
    # companies from the review-candidate list.
    if value["prospect_type"] not in ELIGIBLE_PROSPECT_TYPES:
        return None

    # Retain the original suitability and minimum confidence gates.
    if not value["suitable"] or value["confidence"] < 50:
        return None

    return {
        **value,
        "website": urlunsplit(
            (*urlsplit(source["source_url"])[:2], "/", "", "")
        ),
        "source_url": source["source_url"],
        "evidence_quote": source["text"],
        "domain": host,
    }


def discover(job, providers):
    # Import lazily to preserve the existing stage dispatcher.
    from .stages import page, Links
    from .scraping import readable, render_public, browser_enabled

    ctx = job.payload["context"]
    original = ctx["preferences"].get("discovery_query")

    if not original:
        raise ProviderFailure("TARGETING_NOT_READY")

    with Session() as db:
        known = {
            m.domain
            for m in db.scalars(
                select(DiscoveryMemory).where(
                    DiscoveryMemory.workspace_id == job.workspace_id
                )
            )
            if excluded(m, job.payload["context_hash"])
        }

        known.update(
            domain(l.website)
            for l in db.scalars(
                select(Lead).where(
                    Lead.workspace_id == job.workspace_id
                )
            )
        )

    country = ctx["preferences"].get("country", "MY")

    queries = discovery_queries(
        original,
        ctx["catalog"],
        country,
        known,
    )

    rows, search_errors = [], []

    # Direct retry uses the original candidate URL and avoids
    # unnecessary search-provider calls.
    if job.payload.get("retry_domain"):
        queries = []
        rows = [
            {
                "url": job.payload["retry_url"],
                "title": "",
                "text": "",
            }
        ]

    for index, query in enumerate(queries):
        try:
            rows.extend(
                providers.search(
                    f"discovery-{index}",
                    query,
                    count=20,
                    country=country,
                )
            )
        except ProviderFailure as exc:
            if exc.code in {
                "SEARCH_UNAVAILABLE",
                "SEARCH_TRANSPORT_ERROR",
                "SEARCH_OUTPUT_INVALID",
            }:
                search_errors.append(exc.code)
            else:
                raise

    if not rows and search_errors:
        raise ProviderFailure(
            search_errors[0],
            True,
        )

    # Preserve directory and social-platform filtering.
    rows = [r for r in rows if not listing(r)]

    # Prefer homepages; preserve provider order otherwise.
    rows.sort(
        key=lambda r: bool(
            urlsplit(r.get("url", "")).path.strip("/")
        )
    )

    evaluated, candidates, seen = [], [], set()

    target = (
        1
        if job.payload.get("retry_domain")
        else ctx["preferences"].get("batch_size", 3)
    )

    counters = {
        "searches_attempted": len(queries),
        "searches_unavailable": len(search_errors),
        "websites_attempted": 0,
        "pages_attempted": 0,
        "assessments_attempted": 0,
        "candidates_ready": 0,
    }

    for row in rows:
        url = row.get("url", "")

        try:
            checked_url(url)
        except FetchError:
            continue

        host = domain(url)

        if not host or host in known or host in seen:
            continue

        # Retain existing resource and provider budgets.
        if (
            counters["pages_attempted"] >= 10
            or len(seen) >= min(10, max(3, target * 2))
        ):
            break

        seen.add(host)
        counters["websites_attempted"] += 1

        origin = urlunsplit(
            (*urlsplit(url)[:2], "/", "", "")
        )

        pages, pending, visited = [], [origin, url], set()
        last_failure = "FETCH_UNAVAILABLE"

        while (
            pending
            and len(visited) < 3
            and counters["pages_attempted"] < 10
        ):
            current = pending.pop(0)

            if current in visited:
                continue

            visited.add(current)
            counters["pages_attempted"] += 1

            fetched = page(providers, current)

            if (
                domain(fetched["source_url"]) != host
                or fetched.get("unavailable")
            ):
                continue

            if len(fetched["text"]) < 40:
                last_failure = "JAVASCRIPT_REQUIRED"

            if (
                len(fetched["text"]) < 150
                and browser_enabled()
            ):
                render_key = "render:" + current
                rendered = providers.cache.get(render_key)

                if rendered is None:
                    try:
                        body = render_public(
                            fetched["source_url"]
                        )

                        parser = Links()
                        parser.feed(body)

                        rendered = {
                            "text": (
                                readable(body)
                                or normalize(
                                    " ".join(parser.parts)
                                )[:12000]
                            ),
                            "links": parser.links[:100],
                        }

                    except FetchError as exc:
                        rendered = {
                            "text": "",
                            "reason": exc.reason,
                        }

                    providers.remember(
                        render_key,
                        rendered,
                    )

                if rendered.get("reason"):
                    last_failure = rendered["reason"]

                if (
                    len(rendered["text"])
                    > len(fetched["text"])
                ):
                    fetched = {
                        **fetched,
                        "text": rendered["text"],
                        "links": rendered.get("links", []),
                    }

            pages.append(fetched)

            # Crawl a bounded set of same-domain pages.
            for href in fetched.get("links", []):
                try:
                    following = urljoin(
                        current,
                        href,
                    ).split("#", 1)[0]

                    checked_url(following)

                except (FetchError, ValueError, TypeError):
                    continue

                if (
                    domain(following) == host
                    and re.search(
                        r"about|company|services|solutions|contact",
                        urlsplit(following).path,
                        re.I,
                    )
                ):
                    pending.append(following)

        sources = excerpts(pages)

        if not sources:
            evaluated.append(
                {
                    "domain": host,
                    "source_url": origin,
                    "reason": last_failure,
                }
            )
            continue

        counters["assessments_attempted"] += 1

        # Product-independent instructions use the current context.
        instructions = ASSESSMENT_INSTRUCTIONS

        assessment_data = {
            "context": ctx,
            "excerpts": sources,
        }

        icps = {
            c["code"]
            for c in ctx["catalog"]
            if c["kind"] == "ICP"
        }

        try:
            try:
                raw = providers.model(
                    "discovery:" + host,
                    instructions,
                    assessment_data,
                )

                candidate = assess(
                    raw,
                    sources,
                    icps,
                    host,
                )

            except ProviderFailure as exc:
                if exc.code not in {
                    "MODEL_OUTPUT_INVALID_JSON",
                    "MODEL_OUTPUT_TRUNCATED",
                    "MODEL_OUTPUT_INCOMPLETE",
                    "MODEL_OUTPUT_SCHEMA_INVALID",
                }:
                    raise

                # Retain one separately-accounted repair attempt
                # for formatting or schema errors only.
                repair_instructions = (
                    instructions
                    + " Your previous response did not satisfy the required JSON contract. "
                    + "Return one compact valid JSON object now. Include every required key, "
                    + "use exact boolean/integer/array types, and use UNKNOWN with suitable=false "
                    + "when the evidence does not prove relevance to the selected ICP."
                )

                raw = providers.model(
                    "discovery-repair:" + host,
                    repair_instructions,
                    assessment_data,
                )

                candidate = assess(
                    raw,
                    sources,
                    icps,
                    host,
                )

        except ProviderFailure as exc:
            if exc.code not in {
                "MODEL_OUTPUT_INVALID",
                "MODEL_OUTPUT_INVALID_JSON",
                "MODEL_OUTPUT_TRUNCATED",
                "MODEL_OUTPUT_INCOMPLETE",
                "MODEL_OUTPUT_SCHEMA_INVALID",
                "CANDIDATE_NOT_SUPPORTED",
                "MODEL_UNAVAILABLE",
                "MODEL_TRANSPORT_ERROR",
            }:
                raise

            evaluated.append(
                {
                    "domain": host,
                    "source_url": origin,
                    "reason": exc.code,
                }
            )
            continue

        if candidate:
            candidates.append(candidate)
        else:
            evaluated.append(
                {
                    "domain": host,
                    "source_url": origin,
                    "reason": "NO_MATCH",
                }
            )

        if len(candidates) >= target:
            break

    counters["candidates_ready"] = len(candidates)

    outcome = (
        "CANDIDATES_READY"
        if candidates
        else (
            "PARTIAL_FAILURE"
            if (
                any(
                    v["reason"] != "NO_MATCH"
                    for v in evaluated
                )
                or search_errors
            )
            else "NO_NEW_MATCHES"
        )
    )

    return {
        "candidates": candidates,
        "evaluated_domains": evaluated,
        "coverage": (
            "Up to three searches, ten fetched pages and "
            "three pages per company. Human acceptance required."
        ),
        "counts": counters,
        "outcome": outcome,
        "human_review_required": True,
    }
