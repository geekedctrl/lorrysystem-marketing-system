"""Narrow code-owned strategy interfaces; no user-supplied import paths."""
from typing import Protocol


class QueryStrategy(Protocol):
    version: str
    def queries(self, original, catalog, country, known): ...


class FetchStrategy(Protocol):
    version: str
    def fetch(self, providers, url): ...


class ExtractionStrategy(Protocol):
    version: str
    def extract(self, html): ...


class AssessmentStrategy(Protocol):
    version: str
    def assess(self, raw, sources, icps, host): ...


class ExistingQueries:
    version="icp-queries.1"
    def queries(self,*args):
        from .discovery import discovery_queries
        return discovery_queries(*args)


class GuardedPages:
    version="guarded-pages.1"
    def fetch(self,*args):
        from .stages import page
        return page(*args)


class ReadableExtraction:
    version="readable.1"
    def extract(self,html):
        from .scraping import readable
        return readable(html)


class EvidenceAssessment:
    version="evidence-assessment.1"
    def assess(self,*args):
        from .discovery import assess
        return assess(*args)


queries=ExistingQueries()
fetcher=GuardedPages()
extractor=ReadableExtraction()
assessment=EvidenceAssessment()


def versions():
    return dict(query=queries.version,fetch=fetcher.version,extraction=extractor.version,assessment=assessment.version)
