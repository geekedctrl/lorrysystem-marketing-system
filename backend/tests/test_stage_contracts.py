"""Offline contract tests: no engine, credentials, providers or network needed."""

import copy
import json
import unittest
from uuid import uuid4

from marketing_backend.stage_contracts import (
    ContractViolation, content_hash, validate_envelope, validate_payload,
)


def candidate():
    return dict(
        suitable=True, prospect_type="PRODUCT_BUYER", company_name="Example Retail",
        icp_code="RETAIL", confidence=50, official_company=True, excerpt_id="P1_E0",
        industry="Retail", reasoning="Company activities match the configured retail ICP.",
        unknowns=[], website="https://example.test/", domain="example.test",
        source_url="https://example.test/about", evidence_quote="Example Retail operates retail stores.",
    )


def research():
    return dict(facts=[], people=[], unknowns=["No supported named contacts"], pages=[
        dict(source_url="https://example.test/", text="Example Retail operates retail stores.")
    ])


def envelope(stage="RESEARCH", version=2):
    return dict(
        workspace_id=str(uuid4()), product_line_id=str(uuid4()), job_id=str(uuid4()),
        lead_id=str(uuid4()) if stage == "RESEARCH" else None,
        stage=stage, idempotency_key="synthetic-key", trace_id=str(uuid4()),
        contract_name="research.output" if stage == "RESEARCH" else "discovery.candidate",
        schema_version=version, producer_version="foundation.1", context_version=1,
        context_hash="a" * 64, attempt=1, max_attempts=3,
    )


class StageContractTests(unittest.TestCase):
    def assert_code(self, code, call):
        with self.assertRaises(ContractViolation) as caught:
            call()
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(str(caught.exception), code)

    def test_current_and_previous_versions_preserve_payload(self):
        for version in (1, 2):
            for name, value in (("discovery.candidate", candidate()), ("research.output", research())):
                with self.subTest(version=version, name=name):
                    self.assertEqual(validate_payload(name, version, value), value)
                    self.assertEqual(validate_envelope(envelope(version=version)).schema_version, version)

    def test_v2_addition_is_not_silently_accepted_by_v1(self):
        for name, value in (("discovery.candidate", candidate()), ("research.output", research())):
            value["source_artifact_ids"] = [str(uuid4())]
            self.assertEqual(validate_payload(name, 2, value), value)
            self.assert_code("STAGE_PAYLOAD_INVALID", lambda: validate_payload(name, 1, value))

    def test_unsupported_versions_and_names_fail_closed(self):
        for version in (0, 3, True, "2", 2.0, None):
            self.assert_code("UNSUPPORTED_CONTRACT", lambda: validate_payload("research.output", version, research()))
        self.assert_code("UNSUPPORTED_CONTRACT", lambda: validate_payload("research.unknown", 2, research()))
        value = envelope(version=3)
        self.assert_code("UNSUPPORTED_CONTRACT", lambda: validate_envelope(value))

    def test_envelope_requires_line_context_trace_and_idempotency(self):
        for field in ("workspace_id", "product_line_id", "job_id", "context_version", "context_hash", "trace_id", "idempotency_key"):
            value = envelope()
            del value[field]
            self.assert_code("TASK_ENVELOPE_INVALID", lambda: validate_envelope(value))

    def test_invalid_identity_hash_stage_and_retry_bounds(self):
        for changes in (
            {"attempt": 4, "max_attempts": 3}, {"max_attempts": 6}, {"attempt": True},
            {"context_version": "1"}, {"schema_version": True}, {"context_hash": "not-a-hash"},
            {"lead_id": None}, {"stage": "SCORING"}, {"product_line_id": "bad-id"},
        ):
            value = {**envelope(), **changes}
            self.assert_code("TASK_ENVELOPE_INVALID", lambda: validate_envelope(value))

    def test_prior_artifact_references_are_bounded_and_unique(self):
        value = envelope()
        ref = dict(artifact_id=str(uuid4()), contract_name="research.output", schema_version=1, content_hash="b" * 64)
        value["prior_artifacts"] = [ref, ref]
        self.assert_code("TASK_ENVELOPE_INVALID", lambda: validate_envelope(value))
        value["prior_artifacts"] = [ref]
        self.assertEqual(len(validate_envelope(value).prior_artifacts), 1)

    def test_rejects_checkpoints_extra_fields_and_sensitive_payloads(self):
        for field in ("checkpoint", "provider_payload", "message_body"):
            value = {**research(), field: "synthetic-private-marker"}
            self.assert_code("STAGE_PAYLOAD_INVALID", lambda: validate_payload("research.output", 2, value))

    def test_no_boolean_or_numeric_coercion_in_candidate(self):
        for changes in ({"confidence": "75"}, {"confidence": True}, {"official_company": 1}, {"suitable": 1}):
            value = {**candidate(), **changes}
            self.assert_code("STAGE_PAYLOAD_INVALID", lambda: validate_payload("discovery.candidate", 2, value))

    def test_current_confidence_policy_preserved(self):
        for confidence in (50, 74, 100):
            value = {**candidate(), "confidence": confidence}
            self.assertEqual(validate_payload("discovery.candidate", 2, value)["confidence"], confidence)
        self.assert_code("STAGE_PAYLOAD_INVALID", lambda: validate_payload("discovery.candidate", 2, {**candidate(), "confidence": 49}))

    def test_candidate_domain_and_evidence_must_agree(self):
        for changes in ({"source_url": "https://other.test/about"}, {"website": "file:///etc/passwd"}, {"source_url": "https://user:pass@example.test/"}):
            value = {**candidate(), **changes}
            self.assert_code("STAGE_PAYLOAD_INVALID", lambda: validate_payload("discovery.candidate", 2, value))

    def test_research_stops_and_six_page_limit(self):
        value = {**research(), "stop_reason": "INSUFFICIENT_COMPANY_EVIDENCE"}
        self.assertEqual(validate_payload("research.output", 2, value), value)
        value["pages"] *= 7
        self.assert_code("STAGE_PAYLOAD_INVALID", lambda: validate_payload("research.output", 2, value))

    def test_research_nested_fields_are_strict(self):
        for change in ({"unavailable": "false"}, {"checkpoint": {}}, {"text": None}):
            value = research()
            value["pages"][0].update(change)
            self.assert_code("STAGE_PAYLOAD_INVALID", lambda: validate_payload("research.output", 2, value))
        value = {**research(), "coverage": {"pages_attempted": 1, "unavailable_pages": 2}}
        self.assert_code("STAGE_PAYLOAD_INVALID", lambda: validate_payload("research.output", 2, value))

    def test_hash_is_order_independent_sensitive_to_content(self):
        value = research()
        reordered = dict(reversed(list(value.items())))
        self.assertEqual(content_hash(value), content_hash(reordered))
        changed = copy.deepcopy(value)
        changed["pages"][0]["text"] += " Changed."
        self.assertNotEqual(content_hash(value), content_hash(changed))

    def test_validation_does_not_change_inputs(self):
        value = research()
        before = json.dumps(value)
        validate_payload("research.output", 2, value)
        self.assertEqual(json.dumps(value), before)

    def test_migration_sql_has_no_accidental_bind_parameters(self):
        import importlib.util
        from pathlib import Path
        from unittest.mock import patch
        from sqlalchemy import text
        from sqlalchemy.dialects.postgresql.psycopg import dialect

        path = Path(__file__).resolve().parents[1] / "migrations/versions/014_contract_foundation.py"
        spec = importlib.util.spec_from_file_location("contract_foundation_sql_check", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        statements = []
        with patch.object(module.op, "execute", side_effect=statements.append):
            module.upgrade()
        self.assertGreater(len(statements), 20)
        for statement in statements:
            with self.subTest(statement=statement.splitlines()[0]):
                compiled = text(statement).compile(dialect=dialect())
                self.assertEqual(compiled.construct_params(), {})


if __name__ == "__main__":
    unittest.main()
