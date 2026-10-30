"""Sanitized shared taxonomy and conservative delivery retry metadata."""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from uuid import uuid4
from marketing_backend.diagnostics import classify,delivery_failure,DELIVERY_CATEGORIES
from marketing_backend.delivery_events import record,public_failure,event_read


class DeliveryDiagnosticTests(unittest.TestCase):
    def test_every_delivery_code_uses_shared_failure_taxonomy(self):
        for code,category in DELIVERY_CATEGORIES.items():
            self.assertEqual(classify(code).category,category)
            self.assertEqual(public_failure(code)["error_category"],category)
            self.assertEqual(public_failure(code)["error_code"],code)

    def test_only_known_connection_failure_can_offer_bounded_human_retry(self):
        for code in DELIVERY_CATEGORIES:
            self.assertEqual(delivery_failure(code,1).retryable,code=="SMTP_CONNECTION_FAILED")
        self.assertTrue(delivery_failure("SMTP_CONNECTION_FAILED",2).retryable)
        for attempt in (3,0,True,"1"):
            self.assertFalse(delivery_failure("SMTP_CONNECTION_FAILED",attempt).retryable)
        self.assertFalse(public_failure("SMTP_CONNECTION_FAILED")["automatic_retry"])

    def test_unknown_values_are_sanitized_without_echoing_payload(self):
        for code in (None,{"password":"private"},"private body person@example.test"):
            result=public_failure(code)
            self.assertNotIn("private",json.dumps(result))
            self.assertFalse(result["retryable"])

    def test_structured_event_log_has_category_and_never_content(self):
        delivery=SimpleNamespace(id=uuid4(),workspace_id=uuid4(),product_line_id=uuid4(),
            trace_id=uuid4(),channel="EMAIL",snapshot={"body":"private-body","recipient":"private@example.test"})
        attempt=SimpleNamespace(id=uuid4(),attempt_number=1)
        db=Mock()
        with self.assertLogs("marketing-delivery",level="INFO") as captured:
            record(db,delivery,attempt,"FAILURE","SMTP_CONNECTION_FAILED",17)
        message=captured.records[0].getMessage();value=json.loads(message)
        self.assertEqual(value["error_category"],"provider_transport")
        self.assertTrue(value["retryable"]);self.assertFalse(value["automatic_retry"])
        self.assertEqual(value["duration_ms"],17)
        self.assertNotIn("private",message)
        self.assertEqual(db.add.call_args.args[0].error_code,"SMTP_CONNECTION_FAILED")

    def test_historical_events_gain_metadata_without_mutation(self):
        values=dict(id=uuid4(),delivery_id=uuid4(),product_line_id=uuid4(),event="FAILURE",pool="EMAIL",
            channel="EMAIL",trace_id=uuid4(),attempt=1,schema_version=1,duration_ms=1,created_at=None,
            error_code="SMTP_CONNECTION_FAILED")
        event=SimpleNamespace(**values)
        result=event_read(event)
        self.assertEqual(result["error_category"],"provider_transport")
        self.assertEqual(vars(event),values)
