"""Regressions for current actions versus historical automation outcomes."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.ux_presenter import preparation_summary


class PreparationSummaryTests(unittest.TestCase):
    def test_approved_outreach_does_not_keep_historical_pending_label(self):
        state = {
            "automation_jobs": [
                {"status": "COMPLETED", "outcome": "AWAITING_HUMAN_APPROVAL"}
            ]
        }
        self.assertEqual(
            preparation_summary({}, state, [{"status": "APPROVED"}])["label"],
            "Outreach approved",
        )

    def test_requested_changes_are_a_draft_not_an_approval(self):
        self.assertEqual(
            preparation_summary({}, {}, [{"status": "DRAFT"}])["label"],
            "Draft needs review",
        )

    def test_active_preparation_and_closed_leads_take_precedence(self):
        state = {"automation_jobs": [{"status": "RUNNING", "kind": "SCORING"}]}
        self.assertEqual(preparation_summary({}, state)["label"], "Scoring in progress")
        self.assertEqual(
            preparation_summary({"status": "LOST"}, state)["label"], "Lost"
        )

    def test_resolved_older_failure_does_not_override_newer_completion(self):
        state = {
            "matching_current": True,
            "automation_jobs": [{"status": "COMPLETED"}, {"status": "FAILED"}],
        }
        self.assertEqual(preparation_summary({}, state)["label"], "Products matched")

    def test_missing_evidence_is_distinct_from_paused_automation(self):
        self.assertEqual(
            preparation_summary({}, {"automation_jobs": [{"status": "NEEDS_REVIEW"}]})[
                "label"
            ],
            "Needs attention",
        )
        self.assertEqual(
            preparation_summary({}, {"managed": True, "automation_enabled": False})[
                "label"
            ],
            "Automation paused",
        )


if __name__ == "__main__":
    unittest.main()
