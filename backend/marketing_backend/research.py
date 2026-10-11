import os, json, re
from html.parser import HTMLParser
import httpx
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from .public_fetch import fetch_public, FetchError, checked_url


class ProviderFailure(Exception):
    def __init__(self, code, retryable=False):
        self.code, self.retryable = code, retryable


class Fact(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    category: Literal[
        "COMPANY", "SERVICES", "FLEET", "TECHNOLOGY", "LOCATION", "PAIN_POINT", "SIGNAL"
    ]
    statement: str = Field(min_length=8, max_length=1000)
    evidence_quote: str = Field(min_length=8, max_length=500)
    confidence: int = Field(ge=0, le=100, strict=True)
    kind: Literal["OBSERVED", "INFERRED"]


class Brief(BaseModel):
    model_config = ConfigDict(extra="forbid")
    facts: list[Fact] = Field(max_length=30)
    unknowns: list[str] = Field(max_length=20)


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def normalize(value):
    return re.sub(r"\s+", " ", value).strip()


def validate_brief(raw, evidence):
    brief = Brief.model_validate(raw)
    for fact in brief.facts:
        if normalize(fact.evidence_quote) not in evidence:
            raise ProviderFailure("UNSUPPORTED_CITATION")
    if any(len(value) > 500 for value in brief.unknowns):
        raise ProviderFailure("MODEL_OUTPUT_INVALID")
    return brief.model_dump()


def research(job, save):
    # Standalone manual research uses the same provider ledger as managed stages.
    from .providers import Providers

    providers = Providers(job, save)
    providers.ready()
    page = providers.cache.get("page")
    if not page:
        try:
            fetched = fetch_public(job.payload["website"])
        except FetchError as exc:
            raise ProviderFailure("FETCH_" + exc.reason) from None
        if fetched["fetch_status"] != "SUCCESS":
            raise ProviderFailure("WEBSITE_UNAVAILABLE")
        parser = PageText()
        parser.feed(fetched["body"])
        page = {
            "source_url": fetched["final_url"],
            "text": normalize(" ".join(parser.parts))[:16000],
        }
        providers.remember("page", page)
    if len(page["text"]) < 100:
        raise ProviderFailure("INSUFFICIENT_EVIDENCE")
    instructions = "Research the supplied company using only the supplied page. Return JSON with facts (category,statement,evidence_quote,confidence integer0-100,kind OBSERVED or INFERRED) and unknowns. Categories COMPANY,SERVICES,FLEET,TECHNOLOGY,LOCATION,PAIN_POINT,SIGNAL. Quotes must be exact contiguous page text. Existing capability is not an unmet need or purchase intention. Do not invent contacts, prices or guarantees."
    raw = providers.model(
        "research",
        instructions,
        {
            "company": job.payload["company_name"],
            "catalog_and_icps": job.payload["context"],
            "source": page,
        },
    )
    try:
        brief = validate_brief(raw, page["text"])
    except ProviderFailure:
        raise
    except (ValueError, TypeError):
        raise ProviderFailure("MODEL_OUTPUT_INVALID") from None
    for fact in brief["facts"]:
        fact["source_url"] = page["source_url"]
    brief["coverage"] = (
        "Manual homepage research. Use native preparation for deeper research and later stages."
    )
    return brief
