"""Brave discovery, bounded Python crawling and evidence-backed xKiro assessment."""

import re
from urllib.parse import urljoin, urlsplit, urlunsplit
from typing import Literal
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


def blocked(host):
    return any(host == h or host.endswith("." + h) for h in DIRECTORIES | SOCIAL)


def listing(row):
    try:
        checked_url(row.get("url", ""))
    except (FetchError, ValueError, TypeError, AttributeError):
        return True
    return blocked(domain(row.get("url", ""))) or bool(
        re.search(
            r"\b(top\s+\d+|best\s+\d+|list of companies|companies in|company directory)\b",
            (row.get("title", "") + " " + urlsplit(row.get("url", "")).path).lower(),
        )
    )


def search_query(query, known):
    # All operators originate from validated workspace domains, never scraped text.
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
    raw = [
        f"{original} transport fleet operator company {country}",
        *[
            f"{item['name']} operator logistics fleet company {country}"
            for item in catalog
            if item["kind"] == "ICP"
        ],
    ]
    return list(dict.fromkeys(search_query(query, known) for query in raw))[:3]


def excluded(memory, context_hash):
    if memory.outcome in {"KNOWN", "ACCEPTED", "REJECTED"}:
        return True
    if memory.context_hash != context_hash:
        return False
    return memory.outcome == "READY_FOR_REVIEW" or bool(
        memory.retry_after and memory.retry_after > now()
    )


class Assessment(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    suitable: bool = Field(strict=True)
    prospect_type: Literal[
        "FLEET_OPERATOR",
        "LOGISTICS_PROVIDER",
        "TRANSPORT_BUYER",
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
            value = text[offset : offset + 1000]
            if len(value) >= 40:
                result.append(
                    {
                        "excerpt_id": f"P{index + 1}_E{offset // 800 + 1}",
                        "source_url": page["source_url"],
                        "text": value,
                    }
                )
    return result


def assess(raw, sources, icps, host):
    try:
        value = Assessment.model_validate(raw).model_dump()
    except (ValueError, TypeError):
        raise ProviderFailure("MODEL_OUTPUT_INVALID") from None
    source = next((s for s in sources if s["excerpt_id"] == value["excerpt_id"]), None)
    if (
        not source
        or domain(source["source_url"]) != host
        or normalize(value["company_name"]).lower()
        not in normalize(source["text"]).lower()
        or value["icp_code"] not in icps
        or not value["official_company"]
    ):
        raise ProviderFailure("CANDIDATE_NOT_SUPPORTED")
    # ICP similarity alone is not enough: discovery is for potential buyers of
    # LorrySystem, not companies selling competing software to those buyers.
    if value["prospect_type"] not in {
        "FLEET_OPERATOR",
        "LOGISTICS_PROVIDER",
        "TRANSPORT_BUYER",
    }:
        return None
    if not value["suitable"] or value["confidence"] < 50:
        return None
    return {
        **value,
        "website": urlunsplit((*urlsplit(source["source_url"])[:2], "/", "", "")),
        "source_url": source["source_url"],
        "evidence_quote": source["text"],
        "domain": host,
    }


def discover(job, providers):
    # Import lazily to avoid coupling the stage dispatcher to scraper implementation.
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
                select(Lead).where(Lead.workspace_id == job.workspace_id)
            )
        )
    country = ctx["preferences"].get("country", "MY")
    # Search for actual operators/buyers instead of broadly searching a
    # vertical, which otherwise returns the software vendors serving it.
    queries = discovery_queries(original, ctx["catalog"], country, known)
    rows, search_errors = [], []
    if job.payload.get("retry_domain"):
        queries = []
        rows = [{"url": job.payload["retry_url"], "title": "", "text": ""}]
    for index, query in enumerate(queries):
        try:
            rows.extend(
                providers.search(
                    f"discovery-{index}",
                    query,
                    count=20,
                    country=ctx["preferences"].get("country", "MY"),
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
        raise ProviderFailure(search_errors[0], True)
    # Filter before budgeting; homepages first, preserving Brave order otherwise.
    rows = [r for r in rows if not listing(r)]
    rows.sort(key=lambda r: bool(urlsplit(r.get("url", "")).path.strip("/")))
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
        if counters["pages_attempted"] >= 10 or len(seen) >= min(
            10, max(3, target * 2)
        ):
            break
        seen.add(host)
        counters["websites_attempted"] += 1
        origin = urlunsplit((*urlsplit(url)[:2], "/", "", ""))
        pages, pending, visited = [], [origin, url], set()
        last_failure = "FETCH_UNAVAILABLE"
        while pending and len(visited) < 3 and counters["pages_attempted"] < 10:
            current = pending.pop(0)
            if current in visited:
                continue
            visited.add(current)
            counters["pages_attempted"] += 1
            fetched = page(providers, current)
            if domain(fetched["source_url"]) != host or fetched.get("unavailable"):
                continue
            if len(fetched["text"]) < 40:
                last_failure = "JAVASCRIPT_REQUIRED"
            if len(fetched["text"]) < 150 and browser_enabled():
                render_key = "render:" + current
                rendered = providers.cache.get(render_key)
                if rendered is None:
                    try:
                        body = render_public(fetched["source_url"])
                        parser = Links()
                        parser.feed(body)
                        rendered = {
                            "text": readable(body)
                            or normalize(" ".join(parser.parts))[:12000],
                            "links": parser.links[:100],
                        }
                    except FetchError as exc:
                        rendered = {"text": "", "reason": exc.reason}
                    providers.remember(render_key, rendered)
                if rendered.get("reason"):
                    last_failure = rendered["reason"]
                if len(rendered["text"]) > len(fetched["text"]):
                    fetched = {
                        **fetched,
                        "text": rendered["text"],
                        "links": rendered.get("links", []),
                    }
            pages.append(fetched)
            for href in fetched.get("links", []):
                try:
                    following = urljoin(current, href).split("#", 1)[0]
                    checked_url(following)
                except (FetchError, ValueError, TypeError):
                    continue
                if domain(following) == host and re.search(
                    r"about|company|services|solutions|contact",
                    urlsplit(following).path,
                    re.I,
                ):
                    pending.append(following)
        sources = excerpts(pages)
        if not sources:
            evaluated.append(
                {"domain": host, "source_url": origin, "reason": last_failure}
            )
            continue
        counters["assessments_attempted"] += 1
        try:
            raw = providers.model(
                "discovery:" + host,
                "Assess ONE company's public evidence against the actual catalog and ICPs as a potential customer. Return exactly one JSON object with every key: suitable (boolean), prospect_type (string), company_name (string), icp_code (string), confidence (integer 0-100), official_company (boolean), excerpt_id (string), industry (string), reasoning (string), unknowns (array of strings). Do not omit keys or use markdown. prospect_type must be one of FLEET_OPERATOR, LOGISTICS_PROVIDER, TRANSPORT_BUYER, SOFTWARE_VENDOR, CONSULTANT, OTHER, UNKNOWN. FLEET_OPERATOR means it operates/owns/manages vehicles to sell transport or passenger services. LOGISTICS_PROVIDER means it provides transport/3PL/haulage services itself, not software for providers. TRANSPORT_BUYER means a manufacturer, distributor, retailer or other business whose own evidence shows it operates or manages delivery/transport. SOFTWARE_VENDOR means it sells software, platforms, telematics, fleet technology or consulting to transport operators; never recommend this type as a LorrySystem lead. A company merely describing software for bus operators (such as a transit-management SaaS) is a vendor, not a bus operator. If direct evidence does not establish an operator/buyer role, use UNKNOWN or OTHER and set suitable=false. Select an existing excerpt_id containing the exact company name and supporting both its identity and buyer/operator role. Never write a quote or invent capabilities, contacts or buying intent. Assess customer relevance, not proof of purchase interest. These are recommendations for human review only.",
                {"context": ctx, "excerpts": sources},
            )
            candidate = assess(
                raw,
                sources,
                {c["code"] for c in ctx["catalog"] if c["kind"] == "ICP"},
                host,
            )
        except ProviderFailure as exc:
            if exc.code not in {
                "MODEL_OUTPUT_INVALID",
                "CANDIDATE_NOT_SUPPORTED",
                "MODEL_UNAVAILABLE",
                "MODEL_TRANSPORT_ERROR",
            }:
                raise
            evaluated.append({"domain": host, "source_url": origin, "reason": exc.code})
            continue
        if candidate:
            candidates.append(candidate)
        else:
            evaluated.append(
                {"domain": host, "source_url": origin, "reason": "NO_MATCH"}
            )
        if len(candidates) >= target:
            break
    counters["candidates_ready"] = len(candidates)
    outcome = (
        "CANDIDATES_READY"
        if candidates
        else (
            "PARTIAL_FAILURE"
            if any(v["reason"] != "NO_MATCH" for v in evaluated) or search_errors
            else "NO_NEW_MATCHES"
        )
    )
    return {
        "candidates": candidates,
        "evaluated_domains": evaluated,
        "coverage": "Up to three searches, ten fetched pages and three pages per company. Human acceptance required.",
        "counts": counters,
        "outcome": outcome,
        "human_review_required": True,
    }
