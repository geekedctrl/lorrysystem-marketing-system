"""Conservative, source-backed corroboration for candidate website identity.

This conservatively looks for same-clause company/domain claims on the
candidate's first-party page and an allowlisted independent registry page. It
is a text heuristic for review, not proof of association or legal ownership.
"""
import hashlib
import json
import re
from urllib.parse import urlsplit

from .pipeline import domain
from .public_fetch import checked_url, FetchError
from .research import normalize, ProviderFailure


# Only known registry/company-register sources are accepted for corroboration.
# Search snippets alone never count as evidence.
REGISTRY_SOURCES = {
    "opencorporates.com",
    "companieshouse.gov.uk",
    "ssm.com.my",
    "ssm-einfo.my",
    "acra.gov.sg",
    "bizfile.gov.sg",
    "sec.gov",
    "asic.gov.au",
    "companies-register.companiesoffice.govt.nz",
    "cr.gov.hk",
    "ahu.go.id",
}

DOMAIN_RE = re.compile(r"(?<![\w.-])(?:www\.)?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}(?![\w.-])", re.I)
RELATION_RE = re.compile(r"\b(?:official\s+)?(?:website|web\s+site|homepage|company\s+site|internet\s+domain)\b", re.I)


def registry_host(value):
    host = domain(value if "://" in value else "https://" + value)
    return any(host == item or host.endswith("." + item) for item in REGISTRY_SOURCES)


def _company_clauses(text, company_name):
    value = str(text or "").lower()
    needle = normalize(company_name).lower()
    if not needle:
        return []
    clauses = re.split(r"(?<=[.!?;])\s+|\s*\|\s*|[\r\n]+", value)
    return [normalize(clause).lower() for clause in clauses if needle in clause]


def domain_claims(text, company_name):
    """Return same-clause website claims; distant company/domain co-occurrence is ignored."""
    claims = set()
    needle = normalize(company_name).lower()
    for clause in _company_clauses(text, company_name):
        company_positions = [m.start() for m in re.finditer(re.escape(needle), clause)]
        for relation in RELATION_RE.finditer(clause):
            if not any(abs(position - relation.start()) <= 120 for position in company_positions):
                continue
            for match in DOMAIN_RE.finditer(clause):
                if abs(match.start() - relation.end()) <= 120 or abs(relation.start() - match.end()) <= 120:
                    claims.add(domain("https://" + match.group(0)))
    return claims


def evidence_quote(text, company_name, claimed_domain, limit=500):
    """Extract a short bounded passage suitable for review, never the full page."""
    normalized = normalize(text)
    needle = normalize(company_name)
    lower = normalized.lower()
    position = lower.find(needle.lower())
    while position >= 0:
        end = min(len(normalized), position + len(needle) + 360)
        start = max(0, end - limit)
        excerpt = normalized[start:end]
        if claimed_domain in domain_claims(excerpt, company_name):
            return excerpt[:limit]
        position = lower.find(needle.lower(), position + len(needle))
    return None


def evidence_digest(company_name, website, company_quote, registry_evidence):
    payload = {
        "company_name": normalize(company_name),
        "website": website,
        "company_quote": company_quote,
        "registry_evidence": registry_evidence,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def corroborate(company_name, website, company_quote, providers, fetch_page, country="MY", *, max_results=8, max_fetches=2):
    """Search and fetch a bounded number of allowlisted registries.

    Returns state plus compact evidence. Failed/unavailable verification is
    UNCERTAIN; explicit disagreement in a trusted registry is CONFLICTING.
    """
    try:
        checked_url(website)
    except (FetchError, ValueError, TypeError):
        return {"state": "UNCERTAIN", "evidence": [], "reason": "INVALID_CANDIDATE_WEBSITE", "pages_attempted": 0, "searches_attempted": 0}
    candidate_domain = domain(website)
    if not candidate_domain:
        return {"state": "UNCERTAIN", "evidence": [], "reason": "CANDIDATE_DOMAIN_MISMATCH", "pages_attempted": 0, "searches_attempted": 0}
    if candidate_domain not in domain_claims(company_quote, company_name):
        # The company page must itself explicitly identify its domain before
        # any independent source can corroborate it.
        return {"state": "UNCERTAIN", "evidence": [], "reason": "COMPANY_SITE_IDENTITY_UNCLEAR", "pages_attempted": 0, "searches_attempted": 0}

    try:
        results = providers.search(
            "ownership:" + candidate_domain,
            f'"{company_name}" official website company registry {country}',
            count=max_results,
            country=country,
        )
    except ProviderFailure as exc:
        if exc.code not in {
            "SEARCH_NOT_CONFIGURED", "SEARCH_UNAVAILABLE",
            "SEARCH_TRANSPORT_ERROR", "SEARCH_OUTPUT_INVALID",
        }:
            raise
        return {"state": "UNCERTAIN", "evidence": [], "reason": "REGISTRY_SEARCH_UNAVAILABLE", "pages_attempted": 0, "searches_attempted": 1}

    registry_urls = []
    registry_hosts = set()
    for result in results:
        url = result.get("url", "")
        try:
            checked_url(url)
        except (FetchError, ValueError, TypeError):
            continue
        host = domain(url)
        if registry_host(url) and host != candidate_domain and host not in registry_hosts:
            registry_urls.append(url)
            registry_hosts.add(host)
        if len(registry_urls) >= max_fetches:
            break

    evidence = []
    conflict = False
    pages_attempted = 0
    for url in registry_urls:
        if pages_attempted >= max_fetches:
            break
        pages_attempted += 1
        try:
            fetched = fetch_page(url)
        except FetchError:
            continue
        if not isinstance(fetched, dict) or fetched.get("unavailable"):
            continue
        final_url = fetched.get("source_url", url)
        try:
            checked_url(final_url)
        except (FetchError, ValueError, TypeError):
            continue
        source_domain = domain(final_url)
        if source_domain == candidate_domain or not registry_host(final_url):
            continue
        text = fetched.get("text", "")
        claims = domain_claims(text, company_name)
        matching_quote = evidence_quote(text, company_name, candidate_domain)
        other_domains = claims - {candidate_domain}
        if matching_quote:
            evidence.append({
                "source_url": final_url[:1500],
                "source_domain": source_domain[:254],
                "evidence_quote": matching_quote,
                "relationship": "REGISTRY_WEBSITE_LISTING",
            })
        if other_domains:
            conflict = True
            # Keep a bounded description of the conflicting domain only.
            evidence.append({
                "source_url": final_url[:1500],
                "source_domain": source_domain[:254],
                "evidence_quote": (evidence_quote(text, company_name, next(iter(other_domains))) or "")[:500],
                "relationship": "REGISTRY_DOMAIN_CONFLICT",
            })

    if conflict:
        return {"state": "CONFLICTING", "evidence": evidence[:2], "reason": "REGISTRY_DOMAIN_CONFLICT", "pages_attempted": pages_attempted, "searches_attempted": 1}
    if evidence:
        return {"state": "CORROBORATED", "evidence": evidence[:2], "reason": None, "pages_attempted": pages_attempted, "searches_attempted": 1}
    return {"state": "UNCERTAIN", "evidence": [], "reason": "INDEPENDENT_REGISTRY_EVIDENCE_UNAVAILABLE", "pages_attempted": pages_attempted, "searches_attempted": 1}


def valid_saved_evidence(candidate):
    """Re-evaluate saved evidence and digest before human acceptance."""
    if candidate.get("verification_state") != "CORROBORATED":
        return False
    company = candidate.get("company_name", "")
    website = candidate.get("website", "")
    try:
        checked_url(website)
        checked_url(candidate.get("source_url", ""))
    except (FetchError, ValueError, TypeError):
        return False
    host = domain(website)
    if not host or domain(candidate["source_url"]) != host:
        return False
    company_quote = candidate.get("evidence_quote", "")
    if normalize(company).lower() not in normalize(company_quote).lower() or host not in domain_claims(company_quote, company):
        return False
    evidence = candidate.get("ownership_evidence")
    if not isinstance(evidence, list) or not evidence or len(evidence) > 2:
        return False
    valid = False
    for item in evidence:
        if not isinstance(item, dict):
            return False
        if item.get("relationship") == "REGISTRY_DOMAIN_CONFLICT":
            return False
        if item.get("relationship") != "REGISTRY_WEBSITE_LISTING":
            continue
        url, quote, source_host = item.get("source_url", ""), item.get("evidence_quote", ""), item.get("source_domain", "")
        try:
            checked_url(url)
        except (FetchError, ValueError, TypeError):
            return False
        if domain(url) != source_host or not registry_host(url) or source_host == host:
            return False
        if len(quote) > 500 or host not in domain_claims(quote, company):
            return False
        valid = True
    expected = evidence_digest(company, website, company_quote, evidence)
    return valid and candidate.get("ownership_evidence_digest") == expected
