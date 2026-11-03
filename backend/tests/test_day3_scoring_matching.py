
"""Day 3: explainable scoring and workspace product matching tests.

Synthetic fixtures only. No database writes or external provider calls.
"""

import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from marketing_backend import stages
from marketing_backend.research import ProviderFailure


URL = "https://example.test/"
SERVICE = "Example Retail operates cosmetics stores in Malaysia."
NEED = "Example Retail reports manual inventory reconciliation."
SIGNAL = "Example Retail is evaluating new inventory software."


def citation(quote):
    return {"source_url": URL, "evidence_quote": quote}


def company_research(include_opportunity=True):
    facts = [
        {
            "category": "SERVICES",
            "statement": SERVICE,
            "kind": "OBSERVED",
            "confidence": 90,
            **citation(SERVICE),
        }
    ]

    if include_opportunity:
        facts.extend([
            {
                "category": "PAIN_POINT",
                "statement": NEED,
                "kind": "OBSERVED",
                "confidence": 90,
                **citation(NEED),
            },
            {
                "category": "SIGNAL",
                "statement": SIGNAL,
                "kind": "OBSERVED",
                "confidence": 90,
                **citation(SIGNAL),
            },
        ])

    return {
        "facts": facts,
        "pages": [
            {
                "source_url": URL,
                "text": " ".join([SERVICE, NEED, SIGNAL]),
            }
        ],
        "people": [],
        "unknowns": [],
    }


def score_response():
    items = [
        ("icp_fit", 40, SERVICE),
        ("operational_need", 30, NEED),
        ("operating_scale", 0, SERVICE),
        ("buying_signals", 10, SIGNAL),
        ("evidence_quality", 5, SERVICE),
    ]

    return {
        "criteria": [
            {
                "criterion": code,
                "points": points,
                "rationale": "Supported by synthetic company evidence.",
                "evidence": [citation(quote)] if points else [],
            }
            for code, points, quote in items
        ],
        "unknowns": [],
    }


def match_response(product_code="COSMETICS", fit=85):
    return {
        "matches": [
            {
                "product_code": product_code,
                "fit": fit,
                "rationale": "Supported by the configured product and company evidence.",
                "evidence": [citation(SERVICE)],
            }
        ]
    }


def make_job(qualification=60, matching_fit=60):
    return SimpleNamespace(
        payload={
            "icp_code": "COSMETICS_RETAIL",
            "context": {
                "catalog": [
                    {
                        "kind": "ICP",
                        "code": "COSMETICS_RETAIL",
                        "name": "Cosmetics Retailers",
                        "description": "Companies operating cosmetics retail stores.",
                        "rules": {},
                    },
                    {
                        "kind": "PRODUCT",
                        "code": "COSMETICS",
                        "name": "Cosmetics Retail Software",
                        "description": "Inventory management for cosmetics retailers.",
                    },
                ],
                "preferences": {
                    "qualification_score": qualification,
                    "matching_fit": matching_fit,
                },
            },
        }
    )


class FakeProviders:
    def __init__(self, scoring=None, matching=None):
        self.responses = {
            "scoring": scoring if scoring is not None else score_response(),
            "matching": matching if matching is not None else match_response(),
        }
        self.calls = []

    def model(self, operation, instructions, data):
        self.calls.append((operation, instructions, data))
        return copy.deepcopy(self.responses[operation])


class Day3ScoringMatchingTests(unittest.TestCase):

    def run_scoring(self, job=None, research=None, response=None):
        job = job or make_job()
        research = research if research is not None else company_research()
        providers = FakeProviders(scoring=response)

        with patch(
            "marketing_backend.stages.result",
            return_value=research,
        ):
            result = stages.scoring(job, providers)

        return result

    def run_matching(self, job=None, response=None):
        job = job or make_job()
        providers = FakeProviders(matching=response)

        saved_results = {
            "RESEARCH": company_research(),
            "SCORING": {"score": 85},
        }

        with patch(
            "marketing_backend.stages.result",
            side_effect=lambda job, kind: saved_results[kind],
        ):
            result = stages.matching(job, providers)

        return result

    def test_scoring_matrix_totals_are_explainable(self):
        result = self.run_scoring()

        self.assertEqual(result["score"], 85)
        self.assertEqual(result["relevance"], 45)
        self.assertEqual(result["opportunity"], 40)
        self.assertIsNone(result["stop_reason"])

        self.assertEqual(
            {item["criterion"] for item in result["criteria"]},
            {
                "icp_fit",
                "operational_need",
                "operating_scale",
                "buying_signals",
                "evidence_quality",
            },
        )

        for criterion in result["criteria"]:
            self.assertTrue(criterion["rationale"])
            if criterion["points"] > 0:
                self.assertTrue(criterion["evidence"])

    def test_missing_opportunity_evidence_earns_zero(self):
        result = self.run_scoring(
            research=company_research(include_opportunity=False)
        )

        self.assertEqual(result["score"], 45)
        self.assertEqual(result["relevance"], 45)
        self.assertEqual(result["opportunity"], 0)

        self.assertEqual(
            result["stop_reason"],
            "QUALIFICATION_BELOW_POLICY",
        )

        self.assertIn("operational_need", result["adjustments"])
        self.assertIn("buying_signals", result["adjustments"])

    def test_qualification_uses_configured_threshold(self):
        accepted = self.run_scoring(
            job=make_job(qualification=80)
        )
        rejected = self.run_scoring(
            job=make_job(qualification=90)
        )

        self.assertIsNone(accepted["stop_reason"])
        self.assertEqual(
            rejected["stop_reason"],
            "QUALIFICATION_BELOW_POLICY",
        )

    def test_unsupported_scoring_citation_is_rejected(self):
        response = score_response()
        response["criteria"][0]["evidence"] = [
            citation("Invented information not found on the website.")
        ]

        with self.assertRaises(ProviderFailure):
            self.run_scoring(response=response)

    def test_positive_score_requires_evidence(self):
        response = score_response()
        response["criteria"][0]["evidence"] = []

        with self.assertRaises(ProviderFailure):
            self.run_scoring(response=response)

    def test_matching_selects_configured_product(self):
        result = self.run_matching()

        self.assertEqual(
            result["selected_product"],
            "COSMETICS",
        )
        self.assertIsNone(result["stop_reason"])

    def test_matching_rejects_unconfigured_product(self):
        response = match_response(
            product_code="UNRELATED_TRANSPORT_PRODUCT",
            fit=99,
        )

        with self.assertRaises(ProviderFailure):
            self.run_matching(response=response)

    def test_matching_uses_configured_fit_threshold(self):
        accepted = self.run_matching(
            job=make_job(matching_fit=80)
        )
        rejected = self.run_matching(
            job=make_job(matching_fit=90)
        )

        self.assertEqual(
            accepted["selected_product"],
            "COSMETICS",
        )
        self.assertIsNone(rejected["selected_product"])
        self.assertEqual(
            rejected["stop_reason"],
            "NO_SUPPORTED_PRODUCT_MATCH",
        )

    def test_matching_rejects_unsupported_citation(self):
        response = match_response()
        response["matches"][0]["evidence"] = [
            citation("Invented product requirements.")
        ]

        with self.assertRaises(ProviderFailure):
            self.run_matching(response=response)


if __name__ == "__main__":
    unittest.main()
