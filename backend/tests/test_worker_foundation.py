"""PostgreSQL foundation checks; run only in the existing disposable fixtures."""

from uuid import uuid4
from sqlalchemy import delete, select, text

from test_backend import BackendFixtures
from test_stage_contracts import envelope, research
from marketing_backend import artifacts, queue
from marketing_backend.db import Session
from marketing_backend.models import ProductLine, StageArtifact, StageEvent, Job, JobReplay
from marketing_backend.stage_contracts import ContractViolation


class WorkerFoundationTests(BackendFixtures):
    def setUp(self):
        # Only the disposable test owner can perform maintenance cleanup;
        # runtime roles have no UPDATE/DELETE grants on either history table.
        with Session() as db:
            db.execute(delete(JobReplay))
            db.execute(delete(StageEvent))
            db.execute(delete(StageArtifact))
            db.commit()
        super().setUp()
        self.jid = self.enqueue("contract-foundation")
        with Session() as db:
            job = queue.claim(db)
            self.assertEqual(job.id, self.jid)
            self.token = job.lease_token
            self.line = db.scalar(select(ProductLine).where(ProductLine.workspace_id == self.wid))
            self.line.paused = False
            db.commit()
            self.env = {
                **envelope(), "workspace_id": str(self.wid), "product_line_id": str(self.line.id),
                "job_id": str(self.jid), "lead_id": str(self.lid),
                "context_version": self.line.context_version, "context_hash": self.line.context_hash,
                "idempotency_key": job.idempotency_key, "attempt": job.attempts,
                "max_attempts": job.max_attempts,
            }
        self.provenance = dict(evidence_refs=[], strategy_versions={"research": "foundation.1"}, input_hashes={"input": "a" * 64})

    def tearDown(self):
        with Session() as db:
            db.execute(delete(JobReplay))
            db.execute(delete(StageEvent))
            db.execute(delete(StageArtifact))
            db.commit()
        self.client.close()

    def save(self, db, **changes):
        args = dict(job_id=self.jid, token=self.token, envelope=self.env, payload=research(), artifact_key="research", provenance=self.provenance)
        args.update(changes)
        return artifacts.persist_artifact(db, **args)

    def consume(self, db, aid, **changes):
        args = dict(artifact_id=aid, workspace_id=self.wid, product_line_id=self.line.id,
                    context_version=self.line.context_version, context_hash=self.line.context_hash)
        args.update(changes)
        return artifacts.consume_artifact(db, **args)

    def assert_code(self, code, call):
        with self.assertRaises(ContractViolation) as caught:
            call()
        self.assertEqual(caught.exception.code, code)

    def test_default_line_and_job_backwards_compatible_insert(self):
        with Session() as db:
            lines = list(db.scalars(select(ProductLine).where(ProductLine.workspace_id == self.wid)))
            self.assertEqual(len(lines), 1)
            self.assertEqual(lines[0].code, "DEFAULT")
            self.assertEqual(db.get(Job, self.jid).product_line_id, lines[0].id)

    def test_artifact_current_and_previous_versions_round_trip(self):
        for version in (1, 2):
            with Session() as db:
                artifact = self.save(db, envelope={**self.env, "schema_version": version}, artifact_key=f"research-v{version}")
                self.assertEqual(self.consume(db, artifact.id), research())
                db.commit()

    def test_duplicate_is_idempotent_and_conflict_keeps_original(self):
        with Session() as db:
            first = self.save(db)
            again = self.save(db)
            self.assertEqual(first.id, again.id)
            self.assert_code("ARTIFACT_CONFLICT", lambda: self.save(db, payload={**research(), "unknowns": ["Changed result"]}))
            self.assertEqual(self.consume(db, first.id), research())

    def test_invalid_producer_and_missing_parent_are_not_inserted(self):
        with Session() as db:
            self.assert_code("STAGE_PAYLOAD_INVALID", lambda: self.save(db, payload={**research(), "checkpoint": {}}))
            self.assert_code("ARTIFACT_SCOPE_MISMATCH", lambda: self.save(db, payload={**research(), "source_artifact_ids": [str(uuid4())]}))
            self.assertEqual(list(db.scalars(select(StageArtifact))), [])

    def test_wrong_line_and_workspace_are_rejected_at_both_boundaries(self):
        with Session() as db:
            first = self.save(db)
            self.assert_code("ARTIFACT_SCOPE_MISMATCH", lambda: self.consume(db, first.id, workspace_id=self.other))
            self.assert_code("ARTIFACT_SCOPE_MISMATCH", lambda: self.consume(db, first.id, product_line_id=uuid4()))
            self.assert_code("ARTIFACT_SCOPE_MISMATCH", lambda: self.save(db, envelope={**self.env, "product_line_id": str(uuid4())}))

    def test_context_change_and_pause_reject_old_artifact(self):
        with Session() as db:
            first = self.save(db)
            line = db.get(ProductLine, self.line.id)
            line.context_version += 1
            line.context_hash = "b" * 64
            db.flush()
            self.assert_code("STALE_CONTEXT", lambda: self.consume(db, first.id))
            self.assert_code("STALE_CONTEXT", lambda: self.save(db))
            line.context_version = self.line.context_version
            line.context_hash = self.line.context_hash
            line.paused = True
            db.flush()
            self.assert_code("STALE_CONTEXT", lambda: self.consume(db, first.id))

    def test_lease_required_and_rollback_removes_uncommitted_artifact(self):
        with Session() as db:
            with self.assertRaises(queue.LeaseLost):
                self.save(db, token="not-the-owner")
            self.save(db)
            db.rollback()
        with Session() as db:
            self.assertEqual(list(db.scalars(select(StageArtifact))), [])

    def test_api_rls_and_worker_history_immutability(self):
        with Session() as db:
            db.execute(text("SET LOCAL ROLE backend_worker"))
            artifact = self.save(db)
            aid = artifact.id
            db.commit()
        with Session() as db:
            db.execute(text("SET LOCAL ROLE backend_api"))
            db.execute(text("SELECT set_config('app.workspace_id',:wid,true)"), {"wid": str(self.other)})
            self.assertEqual(list(db.scalars(select(StageArtifact))), [])
            db.execute(text("SELECT set_config('app.workspace_id',:wid,true)"), {"wid": str(self.wid)})
            self.assertEqual(len(list(db.scalars(select(StageArtifact)))), 1)
        for command in ("UPDATE stage_artifacts SET payload='{}' WHERE id=:id", "DELETE FROM stage_artifacts WHERE id=:id"):
            with Session() as db:
                db.execute(text("SET LOCAL ROLE backend_worker"))
                with self.assertRaises(Exception):
                    db.execute(text(command), {"id": aid})
        with Session() as db:
            self.assertEqual(self.consume(db, aid), research())

    def test_event_fields_sanitized_and_no_sensitive_detail_channel(self):
        event = dict(event="COMPLETION", stage="RESEARCH", pool="RESEARCH", attempt=1,
                     schema_version=2, trace_id=self.env["trace_id"], duration_ms=12)
        with Session() as db:
            saved = artifacts.append_event(db, self.jid, self.wid, self.line.id, event)
            self.assertEqual(saved.event, "COMPLETION")
            for value in ({**event, "message_body": "synthetic-secret"}, {**event, "error_code": "synthetic-secret"}):
                self.assert_code("ARTIFACT_METADATA_INVALID", lambda: artifacts.append_event(db, self.jid, self.wid, self.line.id, value))
            db.commit()
        for command in ("UPDATE job_stage_events SET event='FAILURE'", "DELETE FROM job_stage_events"):
            with Session() as db:
                db.execute(text("SET LOCAL ROLE backend_worker"))
                with self.assertRaises(Exception):
                    db.execute(text(command))

    def test_database_rejects_cross_workspace_job_line(self):
        with Session() as db:
            other_line = db.scalar(select(ProductLine).where(ProductLine.workspace_id == self.other))
            with self.assertRaises(Exception):
                db.execute(text("UPDATE jobs SET product_line_id=:line WHERE id=:job"), {"line": other_line.id, "job": self.jid})

    def test_consumer_rejects_corrupt_hash_and_malformed_stored_payload(self):
        for key, payload, digest, expected in (
            ("corrupt-hash", research(), "0" * 64, "ARTIFACT_HASH_MISMATCH"),
            ("malformed", {"unexpected": "synthetic-private-marker"}, "0" * 64, "STAGE_PAYLOAD_INVALID"),
        ):
            with Session() as db:
                row = StageArtifact(
                    workspace_id=self.wid, product_line_id=self.line.id, job_id=self.jid,
                    artifact_key=key, contract_name="research.output", schema_version=2,
                    producer_version=self.env["producer_version"], context_version=self.line.context_version,
                    context_hash=self.line.context_hash, content_hash=digest, envelope=self.env,
                    payload=payload, **self.provenance,
                )
                db.add(row)
                db.flush()
                self.assert_code(expected, lambda: self.consume(db, row.id))
