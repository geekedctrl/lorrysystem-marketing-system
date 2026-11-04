import unittest

from marketing_backend.domain_corroboration import (
    corroborate, domain_claims, evidence_digest, valid_saved_evidence,
)
from marketing_backend.research import ProviderFailure


class RegistryProvider:
    def __init__(self, urls):
        self.urls = urls
        self.operations = []

    def search(self, operation, query, **options):
        self.operations.append((operation, query, options))
        return [{"url": value} for value in self.urls]


class DomainCorroborationTests(unittest.TestCase):
    company = "Example Logistics"
    website = "https://example.com/"
    company_quote = "Example Logistics official website: https://example.com/"
    registry_url = "https://opencorporates.com/companies/gb/123"
    registry_quote = "Example Logistics official website: https://example.com/"

    def test_only_explicit_company_domain_relation_counts(self):
        self.assertEqual(domain_claims(self.registry_quote, self.company), {"example.com"})
        self.assertEqual(
            domain_claims("Example Logistics is described here. A directory links to https://example.com/", self.company),
            set(),
        )

    def test_neighboring_companies_do_not_share_another_companys_domain_claim(self):
        text = (
            "Acme Freight operates in Malaysia. Beta Transport official website: "
            "https://beta.example/"
        )
        self.assertEqual(domain_claims(text, "Acme Freight"), set())

    def test_multiple_nearby_company_domain_claims_fail_closed_as_conflicting(self):
        providers = RegistryProvider([self.registry_url])
        registry_text = (
            "Example Logistics official website: https://example.com/ and "
            "Beta Transport official website: https://beta.example/"
        )
        result = corroborate(
            self.company, self.website, self.company_quote, providers,
            lambda url: {"source_url": url, "text": registry_text},
        )
        self.assertEqual(result["state"], "CONFLICTING")

    def test_provider_budget_and_unexpected_errors_propagate(self):
        for error in (
            ProviderFailure("PROVIDER_BUDGET_EXHAUSTED"),
            ProviderFailure("PRODUCT_LINE_RATE_LIMITED", True),
            ProviderFailure("LEASE_LOST"),
        ):
            providers = RegistryProvider([self.registry_url])
            providers.search = lambda *args, failure=error, **kwargs: (_ for _ in ()).throw(failure)
            with self.subTest(code=error.code), self.assertRaises(ProviderFailure):
                corroborate(self.company, self.website, self.company_quote, providers, lambda _: {})

        providers = RegistryProvider([self.registry_url])
        with self.assertRaises(ProviderFailure) as caught:
            corroborate(
                self.company, self.website, self.company_quote, providers,
                lambda _: (_ for _ in ()).throw(ProviderFailure("FETCH_PAGE_LIMIT")),
            )
        self.assertEqual(caught.exception.code, "FETCH_PAGE_LIMIT")

        providers = RegistryProvider([self.registry_url])
        with self.assertRaises(RuntimeError):
            corroborate(
                self.company, self.website, self.company_quote, providers,
                lambda _: (_ for _ in ()).throw(RuntimeError("unexpected fetch failure")),
            )

    def test_known_search_unavailability_becomes_uncertain(self):
        providers = RegistryProvider([self.registry_url])
        providers.search = lambda *args, **kwargs: (_ for _ in ()).throw(ProviderFailure("SEARCH_UNAVAILABLE", True))
        result = corroborate(self.company, self.website, self.company_quote, providers, lambda _: {})
        self.assertEqual(result["state"], "UNCERTAIN")

    def test_registry_page_corroborates_and_evidence_is_integrity_checked(self):
        providers = RegistryProvider([self.registry_url])
        fetched = []

        def fetch(url):
            fetched.append(url)
            return {"source_url": url, "text": self.registry_quote}

        result = corroborate(self.company, self.website, self.company_quote, providers, fetch)
        self.assertEqual(result["state"], "CORROBORATED")
        self.assertEqual(result["pages_attempted"], 1)
        evidence = result["evidence"]
        candidate = {
            "company_name": self.company,
            "website": self.website,
            "source_url": self.website,
            "evidence_quote": self.company_quote,
            "verification_state": "CORROBORATED",
            "ownership_evidence": evidence,
            "ownership_evidence_digest": evidence_digest(self.company, self.website, self.company_quote, evidence),
        }
        self.assertTrue(valid_saved_evidence(candidate))
        candidate["ownership_evidence"][0]["evidence_quote"] += " altered"
        self.assertFalse(valid_saved_evidence(candidate))
        self.assertEqual(fetched, [self.registry_url])

    def test_conflicting_registry_domain_fails_closed(self):
        providers = RegistryProvider([self.registry_url])
        result = corroborate(
            self.company, self.website, self.company_quote, providers,
            lambda url: {"source_url": url, "text": "Example Logistics official website: https://other.example/"},
        )
        self.assertEqual(result["state"], "CONFLICTING")
        self.assertEqual(result["reason"], "REGISTRY_DOMAIN_CONFLICT")

    def test_alias_and_cooccurrence_do_not_corroborate(self):
        providers = RegistryProvider([self.registry_url])
        result = corroborate(
            "Example Logistics Pty Ltd", self.website,
            "Example Logistics Pty Ltd official website: https://example.com/",
            providers,
            lambda url: {"source_url": url, "text": "Example Logistics Ltd has a registered office. Website https://example.com/"},
        )
        self.assertEqual(result["state"], "UNCERTAIN")
        self.assertEqual(result["reason"], "INDEPENDENT_REGISTRY_EVIDENCE_UNAVAILABLE")

    def test_same_registry_host_is_fetched_once(self):
        providers = RegistryProvider([
            self.registry_url,
            "https://www.opencorporates.com/companies/gb/123?view=2",
        ])
        fetched = []
        result = corroborate(
            self.company, self.website, self.company_quote, providers,
            lambda url: (fetched.append(url) or {"source_url": url, "text": self.registry_quote}),
        )
        self.assertEqual(result["pages_attempted"], 1)
        self.assertEqual(len(fetched), 1)


if __name__ == "__main__":
    unittest.main()
