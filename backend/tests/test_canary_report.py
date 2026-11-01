import copy
import json
from pathlib import Path
import tempfile
import unittest
from canary_report import evaluate,export


class CanaryReportTests(unittest.TestCase):
    def report(self):
        metrics=dict(discovery_jobs=1,completed_jobs=1,candidates=1,evidence_valid_candidates=1,
            evidence_validity_rate=1.0,duplicate_candidates=0,duplicate_rate=0.0,
            failed_jobs=0,quarantined_jobs=0,synthetic_provider_requests=3,provider_reservations=0,
            reserved_microusd=0,query_versions=["test"])
        return dict(measurements=dict(baseline=copy.deepcopy(metrics),canary=copy.deepcopy(metrics)),
            proof=dict(downstream_research_outputs=2,historical_artifacts_retained=True,
                human_acceptance_retained=True,rollback_query_strategy="baseline"),limits=["Synthetic fixtures only"])

    def test_regressions_in_each_requested_metric_fail_comparison(self):
        for changes in (dict(candidates=0),dict(evidence_validity_rate=.5),dict(duplicate_candidates=1),
            dict(failed_jobs=1),dict(quarantined_jobs=1),dict(synthetic_provider_requests=4),
            dict(provider_reservations=1),dict(completed_jobs=0)):
            report=self.report();report["measurements"]["canary"].update(changes)
            self.assertFalse(evaluate(report)["passed"],changes)

    def test_rollback_or_history_loss_fails_comparison(self):
        for key,value in (("historical_artifacts_retained",False),("human_acceptance_retained",False),
            ("rollback_query_strategy","official"),("downstream_research_outputs",0)):
            report=self.report();report["proof"][key]=value
            self.assertFalse(evaluate(report)["passed"])

    def test_report_exports_all_comparison_fields_and_measurement_limits(self):
        report=evaluate(self.report());self.assertTrue(report["passed"])
        with tempfile.TemporaryDirectory() as folder:
            export(report,folder)
            self.assertEqual(json.loads((Path(folder)/"canary-comparison.json").read_text()),report)
            text=(Path(folder)/"canary-comparison.md").read_text()
            for label in ("Duplicate rate","Evidence validity rate","Failed jobs","Quarantined jobs","Fake provider requests","Synthetic fixtures only"):
                self.assertIn(label,text)
