"""Offline runtime-boundary checks (requires imports, never a database connection)."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, MagicMock, patch
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.dialects.postgresql.psycopg import dialect

from marketing_backend.diagnostics import classify
from marketing_backend.stage_contracts import ContractViolation
from marketing_backend.worker_contracts import event_version, validate_task
from test_stage_contracts import envelope


class WorkerRuntimeUnitTests(unittest.TestCase):
    def job(self, value):
        return SimpleNamespace(task_envelope=value, payload={}, id=UUID(value["job_id"]),
            workspace_id=UUID(value["workspace_id"]), product_line_id=UUID(value["product_line_id"]),
            trace_id=UUID(value["trace_id"]), lead_id=UUID(value["lead_id"]),
            kind=value["stage"], idempotency_key=value["idempotency_key"], max_attempts=value["max_attempts"])

    def test_failure_categories_cover_required_boundaries(self):
        cases = {"PROVIDER_NOT_CONFIGURED": "configuration", "MODEL_TRANSPORT_ERROR": "provider_transport",
                 "SEARCH_RATE_LIMITED": "provider_throttling", "MODEL_OUTPUT_SCHEMA_INVALID": "provider_schema",
                 "UNSUPPORTED_CITATION": "evidence", "PROVIDER_BUDGET_EXHAUSTED": "budget",
                 "CONTEXT_CHANGED": "context", "LEASE_EXPIRED": "lease",
                 "UNSUPPORTED_CONTRACT": "contract", "HANDLER_ERROR": "internal"}
        for code, category in cases.items():
            self.assertEqual(classify(code, True).category, category)

    def test_unknown_errors_never_return_sensitive_input(self):
        for code in (None, {"body": "synthetic-secret"}, "contact@example.test", "provider response synthetic-secret"):
            value = classify(code)
            self.assertEqual(value.code, "HANDLER_ERROR")
            self.assertNotIn("synthetic-secret", repr(value))
        self.assertFalse(classify("BUDGET_EXHAUSTED", True).retryable)
        self.assertTrue(classify("MODEL_TRANSPORT_ERROR", True).retryable)

    def test_unknown_versions_can_be_reported_without_coercion(self):
        for version, expected in ((999, 999), (True, 0), ("2", 0), (-1, 0), (2**40, 0)):
            self.assertEqual(event_version(SimpleNamespace(task_envelope={"schema_version": version})), expected)
        self.assertEqual(event_version(SimpleNamespace(task_envelope=None)), 0)

    def test_invalid_discovery_batch_raises_contract_violation(self):
        from marketing_backend.worker_contracts import store_output
        task = Mock(contract_name="discovery.candidate")
        task.model_dump.return_value = {}
        with patch("marketing_backend.worker_contracts.validate_task", return_value=task):
            with self.assertRaises(ContractViolation) as caught:
                store_output(Mock(), SimpleNamespace(attempts=1), {"raw": "synthetic-secret"})
        self.assertEqual(caught.exception.code, "STAGE_PAYLOAD_INVALID")
        self.assertNotIn("synthetic-secret", str(caught.exception))

    def test_legacy_mode_is_explicit_and_does_not_touch_database(self):
        db = Mock()
        self.assertIsNone(validate_task(db, SimpleNamespace(task_envelope=None)))
        self.assertEqual(db.mock_calls, [])

    def test_malformed_and_unknown_envelopes_fail_before_database_or_provider_access(self):
        for value, code in (({"raw": "synthetic-secret"}, "TASK_ENVELOPE_INVALID"), (envelope(version=999), "UNSUPPORTED_CONTRACT")):
            db = Mock()
            with self.assertRaises(ContractViolation) as caught:
                validate_task(db, SimpleNamespace(task_envelope=value))
            self.assertEqual(caught.exception.code, code)
            self.assertEqual(db.mock_calls, [])
            self.assertNotIn("synthetic-secret", str(caught.exception))

    def test_identity_and_trace_mismatch_fail_before_line_lock(self):
        value = envelope()
        for field in ("workspace_id", "product_line_id", "job_id", "lead_id", "trace_id"):
            job = self.job(value)
            job.task_envelope = {**value, field: str(uuid4())}
            with patch("marketing_backend.worker_contracts.artifacts._line") as line:
                with self.assertRaises(ContractViolation):
                    validate_task(Mock(), job)
                line.assert_not_called()

    def test_supported_task_validates_pinned_context(self):
        value = envelope()
        with patch("marketing_backend.worker_contracts.artifacts._line") as line:
            parsed = validate_task(Mock(), self.job(value))
        self.assertEqual(parsed.schema_version, 2)
        self.assertEqual(line.call_args.args[1:], (UUID(value["workspace_id"]), UUID(value["product_line_id"]), 1, value["context_hash"]))

    def test_quarantine_migration_sql_has_no_unintended_bind_parameters(self):
        path = Path(__file__).resolve().parents[1] / "migrations/versions/015_worker_quarantine.py"
        spec = importlib.util.spec_from_file_location("worker_quarantine_sql_check", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        statements = []
        with patch.object(module.op, "execute", side_effect=statements.append):
            module.upgrade()
        self.assertGreater(len(statements), 10)
        for statement in statements:
            with self.subTest(statement=statement.splitlines()[0]):
                self.assertEqual(text(statement).compile(dialect=dialect()).construct_params(), {})

    def execution_job(self, task=None):
        return SimpleNamespace(id=uuid4(), workspace_id=uuid4(), product_line_id=uuid4(),
            trace_id=uuid4(), task_envelope=task, kind="RESEARCH", managed=False,
            attempts=1, max_attempts=3, lease_token="synthetic-token")

    def test_worker_quarantines_invalid_header_before_handler(self):
        from marketing_backend.worker import execute
        job = self.execution_job({"raw": "synthetic-private-marker"})
        handler = Mock()
        with patch("marketing_backend.worker.Session", return_value=MagicMock()), \
             patch("marketing_backend.worker.queue.owned", return_value=job), \
             patch("marketing_backend.worker.queue.quarantine") as quarantine, \
             self.assertLogs("marketing-worker", level="INFO") as logs:
            execute(job, handler)
        handler.assert_not_called()
        self.assertEqual(quarantine.call_args.args[3], "TASK_ENVELOPE_INVALID")
        self.assertNotIn("synthetic-private-marker", " ".join(logs.output))

    def test_worker_internal_failure_logs_only_sanitized_diagnostics(self):
        from marketing_backend.worker import execute
        job = self.execution_job()
        handler = Mock(side_effect=RuntimeError("synthetic-private-marker"))
        with patch("marketing_backend.worker.Session", return_value=MagicMock()), \
             patch("marketing_backend.worker.queue.owned", return_value=job), \
             patch("marketing_backend.worker.queue.fail") as fail, \
             self.assertLogs("marketing-worker", level="INFO") as logs:
            execute(job, handler)
        self.assertEqual(fail.call_args.args[3], "HANDLER_ERROR")
        self.assertNotIn("synthetic-private-marker", " ".join(logs.output))

    def test_worker_completes_research_with_checkpoint(self):
        from marketing_backend.worker import execute
        job = self.execution_job()
        result = {"summary": "synthetic"}

        def handler(current, save):
            self.assertIs(current, job)
            save({"step": 1})
            return result

        with patch("marketing_backend.worker.Session", return_value=MagicMock()), \
             patch("marketing_backend.worker.queue.owned", return_value=job), \
             patch("marketing_backend.worker.queue.checkpoint") as checkpoint, \
             patch("marketing_backend.worker.queue.complete") as complete:
            execute(job, handler)
        self.assertEqual(checkpoint.call_args.args[1:], (job.id, job.lease_token, {"step": 1}))
        self.assertEqual(complete.call_args.args[1:], (job.id, job.lease_token, result))
        self.assertTrue(complete.call_args.kwargs["review"])
        self.assertGreaterEqual(complete.call_args.kwargs["duration_ms"], 0)

    def test_worker_records_retryable_provider_failure(self):
        from marketing_backend.research import ProviderFailure
        from marketing_backend.worker import execute
        job = self.execution_job()
        handler = Mock(side_effect=ProviderFailure("MODEL_TRANSPORT_ERROR", True))
        with patch("marketing_backend.worker.Session", return_value=MagicMock()), \
             patch("marketing_backend.worker.queue.owned", return_value=job), \
             patch("marketing_backend.worker.queue.fail") as fail, \
             patch("marketing_backend.worker.queue.complete") as complete:
            execute(job, handler)
        self.assertEqual(fail.call_args.args[1:], (job.id, job.lease_token, "MODEL_TRANSPORT_ERROR", True))
        complete.assert_not_called()

    def test_managed_worker_checks_context_before_handler_and_completes(self):
        from marketing_backend.worker import execute
        job = self.execution_job()
        job.managed = True
        events = []
        handler = Mock(side_effect=lambda current, save: events.append("handler") or {"ok": True})
        with patch("marketing_backend.worker.Session", return_value=MagicMock()), \
             patch("marketing_backend.worker.queue.owned", side_effect=lambda *args: events.append("owned") or job), \
             patch("marketing_backend.pipeline.valid_context", side_effect=lambda *args: events.append("context")), \
             patch("marketing_backend.worker.queue.complete") as complete:
            execute(job, handler)
        self.assertEqual(events, ["owned", "owned", "context", "handler"])
        self.assertFalse(complete.call_args.kwargs["review"])

    def test_unsupported_unmanaged_job_fails_without_handler(self):
        from marketing_backend.worker import execute
        job = self.execution_job()
        job.kind = "UNKNOWN"
        handler = Mock()
        with patch("marketing_backend.worker.Session", return_value=MagicMock()), \
             patch("marketing_backend.worker.queue.owned", return_value=job), \
             patch("marketing_backend.worker.queue.fail") as fail:
            execute(job, handler)
        handler.assert_not_called()
        self.assertEqual(fail.call_args.args[3], "UNSUPPORTED_JOB_KIND")

    def test_worker_does_not_save_result_after_lease_loss(self):
        from marketing_backend.worker import execute
        from marketing_backend.queue import LeaseLost
        job = self.execution_job()
        handler = Mock()
        with patch("marketing_backend.worker.Session", return_value=MagicMock()), \
             patch("marketing_backend.worker.queue.owned", side_effect=LeaseLost()), \
             patch("marketing_backend.worker.queue.complete") as complete, \
             patch("marketing_backend.worker.queue.fail") as fail:
            execute(job, handler)
        handler.assert_not_called()
        complete.assert_not_called()
        fail.assert_not_called()


if __name__ == "__main__":
    unittest.main()
