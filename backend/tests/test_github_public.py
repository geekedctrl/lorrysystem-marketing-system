import unittest
from unittest.mock import patch
from marketing_backend.github_public import enrich, organization_slugs


class GithubPublicTests(unittest.TestCase):
    def test_only_linked_public_orgs_are_selected(self):
        self.assertEqual(organization_slugs([
            "https://example.com/github/acme",
            "https://github.com/acme",
            "https://github.com/acme/other",
            "https://github.com/settings",
        ]), ["acme"])

    @patch("marketing_backend.github_public._get")
    def test_enrichment_returns_cited_org_and_public_member_pages(self, get):
        get.side_effect = [
            {"login": "acme", "name": "Acme", "description": "Transport tools", "location": "MY"},
            [{"login": "alice"}],
            {"login": "alice", "name": "Alice Tan", "company": "Acme", "bio": "Operations lead"},
        ]
        pages = enrich(["https://github.com/acme"])
        self.assertEqual([p["source_url"] for p in pages], [
            "https://api.github.com/orgs/acme", "https://github.com/alice"
        ])
        self.assertIn("Transport tools", pages[0]["text"])
        self.assertIn("alice", pages[1]["text"])
        self.assertIn("Operations lead", pages[1]["text"])


if __name__ == "__main__":
    unittest.main()
