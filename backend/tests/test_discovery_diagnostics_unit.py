"""Synthetic discovery validation and fetch diagnostics; no network or database."""
import unittest
from unittest.mock import Mock, patch

from marketing_backend.discovery import assess, listing_reason, search_priority
from marketing_backend.public_fetch import FetchError
from marketing_backend.research import ProviderFailure
from marketing_backend.stages import page


class DiscoveryDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.raw = dict(suitable=True, prospect_type="PRODUCT_BUYER", company_name="Example Company",
                        icp_code="BUYER", confidence=85, official_company=True, excerpt_id="P1_E1",
                        industry="Transport", reasoning="The company operates transport services.", unknowns=[])
        self.sources = [dict(excerpt_id="P1_E1", source_url="https://example.com/",
                             text="Example Company operates transport services in Malaysia.")]

    def test_evidence_failures_are_distinct(self):
        cases = [({"excerpt_id": "missing"}, self.sources, {"BUYER"}, "UNKNOWN_EXCERPT"),
                 ({}, [{**self.sources[0], "source_url": "https://other.com/"}], {"BUYER"}, "WRONG_DOMAIN"),
                 ({"company_name": "Different Company"}, self.sources, {"BUYER"}, "COMPANY_NAME_MISMATCH"),
                 ({"icp_code": "OTHER"}, self.sources, {"BUYER"}, "UNKNOWN_CUSTOMER_PROFILE"),
                 ({"official_company": False}, self.sources, {"BUYER"}, "OFFICIAL_COMPANY_NOT_ESTABLISHED")]
        for updates, sources, icps, expected in cases:
            with self.subTest(expected=expected), self.assertRaises(ProviderFailure) as caught:
                assess({**self.raw, **updates}, sources, icps, "example.com")
            self.assertEqual(caught.exception.code, "CANDIDATE_NOT_SUPPORTED")
            self.assertEqual(caught.exception.details[0]["category"], expected)

    def test_schema_diagnostics_do_not_include_supplied_value(self):
        with self.assertRaises(ProviderFailure) as caught:
            assess({**self.raw, "confidence": "synthetic-secret"}, self.sources, {"BUYER"}, "example.com")
        self.assertEqual(caught.exception.details[0]["field"], "confidence")
        self.assertNotIn("synthetic-secret", repr(caught.exception.details))

    def test_supported_candidate_and_no_match(self):
        self.assertIsNotNone(assess(self.raw, self.sources, {"BUYER"}, "example.com"))
        self.assertIsNone(assess({**self.raw, "suitable": False}, self.sources, {"BUYER"}, "example.com"))

    def test_search_filters_and_deprioritizes_without_excluding_associations(self):
        self.assertEqual(listing_reason({"url": "https://mot.gov.my/", "title": "Ministry"}), "GOVERNMENT_SITE")
        self.assertEqual(listing_reason({"url": "https://clutch.co/", "title": "Directory"}), "DIRECTORY_OR_SOCIAL")
        association = {"url": "https://buses.org/", "title": "Bus Association"}
        self.assertIsNone(listing_reason(association))
        self.assertGreater(search_priority(association), search_priority({"url": "https://example.com/", "title": "Example Company"}))

    def test_fetch_failure_reasons_are_preserved(self):
        for reason in ("TIMEOUT", "ROBOTS_DISALLOWED", "UNSUPPORTED_CONTENT_TYPE", "HTTP_403"):
            with self.subTest(reason=reason), patch("marketing_backend.stages.fetch_public", side_effect=FetchError(reason)):
                providers = Mock(spec=["cache", "remember"])
                providers.cache = {}
                providers.remember.side_effect = lambda key, value: value
                self.assertEqual(page(providers, "https://example.com/")["failure_reason"], reason)


if __name__ == "__main__":
    unittest.main()
