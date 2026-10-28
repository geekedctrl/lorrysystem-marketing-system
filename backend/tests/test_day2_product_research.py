
"""Day 2 regression tests for product-neutral setup and company research.

All providers and website pages are synthetic.
No live API requests, network fetching, or database writes are made.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from marketing_backend import stages


BASE_URL = "https://beauty.example.com/"
COMPANY_NAME = "Beauty Retail Sdn Bhd"

HOME_TEXT = (
    "Beauty Retail Sdn Bhd operates cosmetics retail stores in Malaysia. "
    "The company sells skincare products and beauty accessories through "
    "its retail outlets and official website."
)

PRODUCT_TEXT = (
    "Beauty Retail Sdn Bhd offers skincare products and cosmetics "
    "for customers through its official retail business."
)


class FakeProviders:
    """Synthetic AI provider that records instructions without making API calls."""

    def __init__(self):
        self.calls = []

    def model(self, operation, instructions, data):
        self.calls.append(
            {
                "operation": operation,
                "instructions": instructions,
                "data": data,
            }
        )

        if operation == "setup":
            return {
                "discovery_query": "Cosmetics retailers in Malaysia",
                "icps": [
                    {
                        "code": "COSMETICS_RETAIL",
                        "name": "Cosmetics Retailers",
                        "description": (
                            "Retail businesses selling skincare and "
                            "cosmetics products to customers."
                        ),
                    }
                ],
            }

        if operation == "research":
            return {
                "facts": [
                    {
                        "category": "SERVICES",
                        "statement": (
                            "The company offers cosmetics and skincare products."
                        ),
                        "source_url": BASE_URL + "products",
                        "evidence_quote": PRODUCT_TEXT,
                        "confidence": 90,
                        "kind": "OBSERVED",
                    }
                ],
                "people": [],
                "unknowns": [],
            }

        raise AssertionError(f"Unexpected model operation: {operation}")


class Day2ProductResearchTests(unittest.TestCase):

    def make_job(self):
        return SimpleNamespace(
            payload={
                "company_name": COMPANY_NAME,
                "website": BASE_URL,
                "context": {
                    "catalog": [
                        {
                            "kind": "PRODUCT",
                            "code": "COSMETICS",
                            "description": (
                                "Cosmetics and skincare products for "
                                "retail distribution."
                            ),
                        }
                    ],
                    "country": "MY",
                },
            }
        )

    def test_setup_uses_product_neutral_instructions(self):
        job = self.make_job()
        providers = FakeProviders()

        result = stages.setup(job, providers)

        self.assertEqual(
            result["discovery_query"],
            "Cosmetics retailers in Malaysia",
        )

        self.assertEqual(
            result["icps"][0]["code"],
            "COSMETICS_RETAIL",
        )

        self.assertEqual(len(providers.calls), 1)

        instructions = providers.calls[0]["instructions"].lower()

        self.assertIn("products", instructions)
        self.assertIn("customer", instructions)
        self.assertIn("geography", instructions)

        self.assertIn(
            "do not assume",
            instructions,
        )

    def test_research_visits_cosmetics_product_pages(self):
        job = self.make_job()
        providers = FakeProviders()

        pages = {
            BASE_URL: {
                "source_url": BASE_URL,
                "text": HOME_TEXT,
                "links": [
                    "/products",
                    "/contact",
                ],
            },
            BASE_URL + "products": {
                "source_url": BASE_URL + "products",
                "text": PRODUCT_TEXT,
                "links": [],
            },
            BASE_URL + "contact": {
                "source_url": BASE_URL + "contact",
                "text": (
                    "Beauty Retail Sdn Bhd provides customer support "
                    "through its official contact page."
                ),
                "links": [],
            },
        }

        requested_urls = []

        def fake_page(provider, url):
            requested_urls.append(url)
            return pages[url]

        with patch(
            "marketing_backend.stages.page",
            side_effect=fake_page,
        ):
            result = stages.research(job, providers)

        self.assertIn(BASE_URL + "products", requested_urls)

        self.assertEqual(
            result["coverage"]["pages_attempted"],
            3,
        )

        self.assertEqual(len(result["facts"]), 1)

        self.assertEqual(
            result["facts"][0]["category"],
            "SERVICES",
        )

        self.assertIsNone(result.get("stop_reason"))

    def test_research_rejects_external_websites(self):
        job = self.make_job()
        providers = FakeProviders()

        homepage = {
            "source_url": BASE_URL,
            "text": HOME_TEXT,
            "links": [
                "https://external.example.org/products",
                "/products",
            ],
        }

        product_page = {
            "source_url": BASE_URL + "products",
            "text": PRODUCT_TEXT,
            "links": [],
        }

        requested_urls = []

        def fake_page(provider, url):
            requested_urls.append(url)

            if url == BASE_URL:
                return homepage

            if url == BASE_URL + "products":
                return product_page

            raise AssertionError(
                f"Unexpected external page requested: {url}"
            )

        with patch(
            "marketing_backend.stages.page",
            side_effect=fake_page,
        ):
            result = stages.research(job, providers)

        self.assertEqual(
            requested_urls,
            [BASE_URL, BASE_URL + "products"],
        )

        self.assertEqual(
            result["coverage"]["pages_attempted"],
            2,
        )

    def test_research_preserves_six_page_limit(self):
        job = self.make_job()
        providers = FakeProviders()

        links = [
            f"/products-{number}"
            for number in range(1, 11)
        ]

        requested_urls = []

        def fake_page(provider, url):
            requested_urls.append(url)

            if url == BASE_URL:
                return {
                    "source_url": BASE_URL,
                    "text": HOME_TEXT,
                    "links": links,
                }

            return {
                "source_url": url,
                "text": PRODUCT_TEXT,
                "links": [],
            }

        with patch(
            "marketing_backend.stages.page",
            side_effect=fake_page,
        ):
            result = stages.research(job, providers)

        self.assertEqual(len(requested_urls), 6)

        self.assertEqual(
            result["coverage"]["pages_attempted"],
            6,
        )

    def test_existing_transport_pages_remain_supported(self):
        job = self.make_job()
        providers = FakeProviders()

        transport_page = BASE_URL + "fleet"

        requested_urls = []

        def fake_page(provider, url):
            requested_urls.append(url)

            if url == BASE_URL:
                return {
                    "source_url": BASE_URL,
                    "text": HOME_TEXT,
                    "links": ["/fleet", "/products"],
                }

            if url == transport_page:
                return {
                    "source_url": url,
                    "text": (
                        "Beauty Retail Sdn Bhd operates its own "
                        "delivery fleet for store distribution."
                    ),
                    "links": [],
                }

            if url == BASE_URL + "products":
                return {
                    "source_url": url,
                    "text": PRODUCT_TEXT,
                    "links": [],
                }

            raise AssertionError(f"Unexpected URL: {url}")

        with patch(
            "marketing_backend.stages.page",
            side_effect=fake_page,
        ):
            stages.research(job, providers)

        self.assertIn(transport_page, requested_urls)
        self.assertIn(BASE_URL + "products", requested_urls)


if __name__ == "__main__":
    unittest.main()
