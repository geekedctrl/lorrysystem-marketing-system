"""Offline checks for the full Day 1 stage/line boundary contracts."""
import hashlib,json,importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from sqlalchemy import text
from sqlalchemy.dialects.postgresql.psycopg import dialect
from test_stage_contracts import envelope
from marketing_backend.stage_contracts import validate_payload,validate_input,validate_envelope,ContractViolation,STAGE_CONTRACTS


class ProductLineContractTests(unittest.TestCase):
    def test_all_seven_stage_outputs_have_current_and_previous_schemas(self):
        citation=dict(source_url="https://example.test/",evidence_quote="Exact synthetic source evidence.")
        examples={
          "setup.output":dict(discovery_query="Manufacturing businesses Malaysia",icps=[]),
          "contact.output":dict(people=[],selected_contact=None,unavailable_queries=0,stop_reason="SUPPORTED_CONTACT_REQUIRED"),
          "scoring.output":dict(criteria=[dict(criterion="icp_fit",points=0,rationale="No supported fit evidence.",evidence=[])],unknowns=[],score=0,relevance=0,opportunity=0,adjustments=[],stop_reason="QUALIFICATION_BELOW_POLICY"),
          "matching.output":dict(matches=[],selected_product=None,stop_reason="PRODUCT_MATCH_REQUIRED"),
          "content.output":dict(subject="Synthetic draft",body="This is a synthetic draft prepared for a human reviewer.",evidence=[citation],channel="EMAIL",recipient="person@example.test",product_code="PRODUCT",status="PENDING_APPROVAL")}
        self.assertEqual(len(STAGE_CONTRACTS),7)
        for name,value in examples.items():
            for version in (1,2):
                with self.subTest(name=name,version=version):self.assertEqual(validate_payload(name,version,value),value)

    def payload(self):
        header=envelope()
        context=dict(catalog=[dict(kind="ICP",code="ICP",name="Synthetic customers",description="A documented customer segment",rules={},version=1)],
            preferences=dict(language="বাংলা"),product_line=dict(id=header["product_line_id"],version=1,context_hash=header["context_hash"]),
            company=dict(id=header["lead_id"],company_name="Example company",website="https://example.test/"))
        value=dict(product_line_id=header["product_line_id"],context=context,
            context_hash=hashlib.sha256(json.dumps(context,sort_keys=True,separators=(",",":")).encode()).hexdigest(),
            company_name="Example company",website="https://example.test/",icp_code="ICP")
        return value,validate_envelope(header)

    def test_typed_inputs_preserve_unicode_and_company_line_identity(self):
        value,header=self.payload()
        self.assertEqual(validate_input(value,header).context.preferences["language"],"বাংলা")
        for changes in ({"icp_code":"WRONG_LINE"},{"company_name":"Another company"},{"checkpoint":{}},{"product_line_id":header.job_id.hex}):
            with self.assertRaises(ContractViolation):validate_input({**value,**changes},header)

    def test_score_totals_are_not_silently_coerced(self):
        value=dict(criteria=[dict(criterion="icp_fit",points=10,rationale="Supported synthetic evidence",evidence=[])],unknowns=[],score=50,relevance=50,opportunity=0,adjustments=[],stop_reason=None)
        with self.assertRaises(ContractViolation):validate_payload("scoring.output",2,value)

    def test_asset_type_is_an_additive_v2_field(self):
        value=dict(subject="Synthetic draft",body="This is a synthetic draft prepared for a human reviewer.",
            evidence=[dict(source_url="https://example.test/",evidence_quote="Exact source evidence")],
            channel="EMAIL",recipient="person@example.test",product_code="PRODUCT",status="PENDING_APPROVAL",asset_type="EMAIL_TEXT")
        self.assertEqual(validate_payload("content.output",2,value),value)
        with self.assertRaises(ContractViolation):validate_payload("content.output",1,value)

    def test_full_line_migration_statements_compile_without_bind_parameters(self):
        path=Path(__file__).resolve().parents[1]/"migrations/versions/016_product_lines.py"
        spec=importlib.util.spec_from_file_location("product_lines_sql",path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        statements=[]
        with patch.object(module.op,"execute",side_effect=statements.append):module.upgrade()
        self.assertGreater(len(statements),80)
        for statement in statements:
            with self.subTest(sql=statement.splitlines()[0]):self.assertEqual(text(statement).compile(dialect=dialect()).construct_params(),{})
