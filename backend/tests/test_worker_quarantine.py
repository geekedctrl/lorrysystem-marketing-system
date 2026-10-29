"""Synthetic PostgreSQL/HTTP worker quarantine and replay acceptance checks."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import threading
from unittest.mock import Mock, patch
from uuid import uuid4

from sqlalchemy import select, text, func
from test_backend import BackendFixtures
from test_stage_contracts import envelope, research, candidate
from marketing_backend.db import Session
from marketing_backend.models import Job, JobReplay, ProductLine, StageEvent, StageArtifact, PreparationRun, Workspace, Lead
from marketing_backend import queue, pipeline
from marketing_backend.stage_contracts import SCHEMAS
from marketing_backend.worker import execute


class WorkerQuarantineTests(BackendFixtures):
    def setUp(self):
        super().setUp()
        self.jid = self.enqueue("quarantine-fixture")
        with Session() as db:
            line = db.scalar(select(ProductLine).where(ProductLine.workspace_id == self.wid))
            line.paused = False
            self.line_id = line.id
            db.commit()
        self.url = f"/workspaces/{self.wid}/jobs/{self.jid}"

    def set_task(self, **changes):
        with Session() as db:
            job = db.get(Job, self.jid)
            line = db.get(ProductLine, self.line_id)
            value = {**envelope(), "workspace_id": str(self.wid), "product_line_id": str(self.line_id),
                "job_id": str(job.id), "lead_id": str(job.lead_id) if job.lead_id else None,
                "stage": job.kind, "trace_id": str(job.trace_id), "idempotency_key": job.idempotency_key,
                "context_version": line.context_version, "context_hash": line.context_hash,
                "attempt": 0, "max_attempts": job.max_attempts}
            value.update(changes)
            job.task_envelope = value
            db.commit()

    def run_job(self, handler):
        with Session() as db:
            job = queue.claim(db)
            self.assertEqual(job.id, self.jid)
        execute(job, handler=handler)
        with Session() as db:
            return db.get(Job, self.jid)

    def events(self):
        with Session() as db:
            return list(db.scalars(select(StageEvent).where(StageEvent.job_id == self.jid).order_by(StageEvent.created_at)))

    def quarantine_bad_output(self):
        self.set_task()
        job = self.run_job(lambda job, save: {"facts": "synthetic-private-marker"})
        self.assertEqual(job.status, "QUARANTINED")
        return job

    def test_malformed_task_quarantines_without_calling_handler_or_leaking_payload(self):
        with Session() as db:
            db.get(Job, self.jid).task_envelope = {"raw": "synthetic-private-marker"}
            db.commit()
        handler = Mock()
        with self.assertLogs("marketing-worker", level="INFO") as logs:
            job = self.run_job(handler)
        handler.assert_not_called()
        self.assertEqual(job.quarantine_reason, "TASK_ENVELOPE_INVALID")
        self.assertIsNone(job.lease_token)
        self.assertEqual([row.event for row in self.events()], ["CLAIM", "QUARANTINE"])
        self.assertNotIn("synthetic-private-marker", " ".join(logs.output))
        for path in (self.url, self.url+"/events"):
            response = self.client.get(path, headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("synthetic-private-marker", response.text)
            self.assertNotIn("lease_token", response.text)
            self.assertNotIn("task_envelope", response.text)

    def test_unsupported_contract_is_held_and_normal_retry_cannot_bypass(self):
        self.set_task(schema_version=999)
        handler = Mock()
        job = self.run_job(handler)
        handler.assert_not_called()
        self.assertEqual(job.quarantine_reason, "UNSUPPORTED_CONTRACT")
        self.assertEqual(self.events()[-1].schema_version, 999)
        with Session() as db:
            self.assertIsNone(queue.claim(db))
        self.assertEqual(self.client.post(self.url+"/retry", headers=self.headers).status_code, 409)
        response = self.client.post(self.url+"/replay", headers=self.headers, json={"idempotency_key": "unsupported-replay"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "UNSUPPORTED_CONTRACT")

    def test_output_validation_rolls_back_artifacts_and_downstream_state(self):
        self.quarantine_bad_output()
        with Session() as db:
            self.assertEqual(db.get(Job, self.jid).result, {})
            self.assertEqual(list(db.scalars(select(StageArtifact))), [])
            self.assertEqual(db.scalar(select(func.count()).select_from(PreparationRun)), 0)

    def test_replay_is_audited_and_idempotent_before_and_after_completion(self):
        job = self.quarantine_bad_output()
        body = {"idempotency_key": "audited-replay-key"}
        first = self.client.post(self.url+"/replay", headers=self.headers, json=body)
        self.assertEqual(first.status_code, 202, first.text)
        second = self.client.post(self.url+"/replay", headers=self.headers, json=body)
        self.assertEqual(second.status_code, 202, second.text)
        self.assertEqual(first.json()["replay_id"], second.json()["replay_id"])
        self.assertTrue(second.json()["already_recorded"])
        self.assertEqual(self.run_job(lambda job, save: research()).status, "NEEDS_REVIEW")
        repeated = self.client.post(self.url+"/replay", headers=self.headers, json=body)
        self.assertEqual(repeated.status_code, 202)
        with Session() as db:
            rows = list(db.scalars(select(JobReplay)))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].actor_id, self.uid)
            self.assertEqual(rows[0].previous_attempts, 1)
            self.assertEqual(db.get(Job, self.jid).trace_id, job.trace_id)
            self.assertEqual(db.get(Job, self.jid).replay_generation, 1)
            self.assertEqual(db.scalar(select(func.count()).select_from(StageArtifact)), 1)
        self.assertEqual([row.event for row in self.events()].count("REPLAY"), 1)

    def test_consumer_upgrade_allows_replay_without_mutating_original_envelope(self):
        self.set_task()
        schema = SCHEMAS.pop(("research.output", 2))
        try:
            handler = Mock()
            job = self.run_job(handler)
            self.assertEqual(job.quarantine_reason, "UNSUPPORTED_CONTRACT")
            handler.assert_not_called()
        finally:
            SCHEMAS["research.output", 2] = schema
        original = job.task_envelope
        response = self.client.post(self.url+"/replay", headers=self.headers, json={"idempotency_key": "consumer-upgrade"})
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(self.run_job(lambda job, save: research()).status, "NEEDS_REVIEW")
        with Session() as db:
            self.assertEqual(db.get(Job, self.jid).task_envelope, original)

    def test_changed_input_cannot_be_reinterpreted_as_original_task(self):
        self.quarantine_bad_output()
        with Session() as db:
            job = db.get(Job, self.jid)
            job.payload = {**job.payload, "company_name": "Changed company"}
            db.commit()
        response = self.client.post(self.url+"/replay", headers=self.headers, json={"idempotency_key": "changed-input"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "REPLAY_INPUT_CHANGED")

    def test_changed_context_or_paused_line_blocks_replay(self):
        self.quarantine_bad_output()
        with Session() as db:
            line = db.get(ProductLine, self.line_id)
            line.context_version += 1
            line.context_hash = "c" * 64
            db.commit()
        response = self.client.post(self.url+"/replay", headers=self.headers, json={"idempotency_key": "changed-context"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "STALE_CONTEXT")
        with Session() as db:
            self.assertEqual(db.get(Job, self.jid).status, "QUARANTINED")
            self.assertEqual(db.scalar(select(func.count()).select_from(JobReplay)), 0)

    def test_replay_role_scope_and_request_validation(self):
        self.quarantine_bad_output()
        viewer = {"Authorization": "Bearer "+self.login("viewer@example.test")}
        body = {"idempotency_key": "role-scope-replay"}
        self.assertEqual(self.client.post(self.url+"/replay", json=body).status_code, 401)
        self.assertEqual(self.client.post(self.url+"/replay", headers=viewer, json=body).status_code, 403)
        self.assertEqual(self.client.post(f"/workspaces/{self.other}/jobs/{self.jid}/replay", headers=self.headers, json=body).status_code, 404)
        self.assertEqual(self.client.post(self.url+"/replay", headers=self.headers, json={**body, "replacement_envelope": {}}).status_code, 422)
        self.assertEqual(self.client.get(self.url+"/events?limit=201", headers=self.headers).status_code, 422)

    def test_replay_concurrency_serializes_same_key_and_rejects_different_key(self):
        self.quarantine_bad_output()
        barrier = threading.Barrier(2)
        def attempt(_):
            barrier.wait()
            return self.client.post(self.url+"/replay", headers=self.headers, json={"idempotency_key": "concurrent-same-key"})
        with ThreadPoolExecutor(2) as workers:
            results = list(workers.map(attempt, range(2)))
        self.assertEqual([r.status_code for r in results], [202, 202])
        self.assertEqual(results[0].json()["replay_id"], results[1].json()["replay_id"])
        other = self.client.post(self.url+"/replay", headers=self.headers, json={"idempotency_key": "concurrent-other-key"})
        self.assertEqual(other.status_code, 409)

    def test_total_replays_are_bounded(self):
        self.set_task()
        for index in range(3):
            self.assertEqual(self.run_job(lambda job, save: {"bad": True}).status, "QUARANTINED")
            response = self.client.post(self.url+"/replay", headers=self.headers, json={"idempotency_key": f"bounded-replay-{index}"})
            self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(self.run_job(lambda job, save: {"bad": True}).status, "QUARANTINED")
        response = self.client.post(self.url+"/replay", headers=self.headers, json={"idempotency_key": "bounded-replay-final"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "REPLAY_LIMIT_REACHED")

    def test_current_and_previous_versions_execute_with_immutable_artifacts(self):
        self.set_task(schema_version=1)
        self.assertEqual(self.run_job(lambda job, save: research()).status, "NEEDS_REVIEW")
        with Session() as db:
            self.assertEqual(db.scalar(select(StageArtifact)).schema_version, 1)

    def test_legacy_jobs_get_events_without_being_relabelled(self):
        job = self.run_job(lambda job, save: {"facts": [], "unknowns": []})
        self.assertEqual(job.status, "NEEDS_REVIEW")
        self.assertEqual([row.event for row in self.events()], ["CLAIM", "COMPLETION"])
        self.assertTrue(all(row.schema_version == 0 for row in self.events()))
        data = self.client.get(self.url, headers=self.headers).json()
        self.assertEqual(data["contract_mode"], "LEGACY")
        with Session() as db:
            self.assertEqual(list(db.scalars(select(StageArtifact))), [])

    def test_expired_lease_records_loss_and_retry_without_stale_artifact(self):
        self.set_task()
        with Session() as db:
            job = queue.claim(db)
            token = job.lease_token
            job.lease_until = job.lease_until-timedelta(hours=1)
            db.commit()
        with Session() as db:
            with self.assertRaises(queue.LeaseLost):
                queue.complete(db, self.jid, token, research())
        with Session() as db:
            self.assertIsNone(queue.claim(db))
            self.assertEqual(list(db.scalars(select(StageArtifact))), [])
        self.assertEqual([row.event for row in self.events()], ["CLAIM", "LEASE_LOSS", "RETRY"])

    def test_checkpoint_contents_are_not_written_to_events(self):
        self.set_task()
        def handler(job, save):
            save({"model:bad": "synthetic-private-marker", "page:cache": "synthetic-evidence"})
            return {"bad": True}
        self.run_job(handler)
        body = self.client.get(self.url+"/events", headers=self.headers).text
        self.assertNotIn("synthetic-private-marker", body)
        self.assertIn("CHECKPOINT", body)
        response = self.client.post(self.url+"/replay", headers=self.headers, json={"idempotency_key": "clear-bad-model"})
        self.assertEqual(response.status_code, 202, response.text)
        with Session() as db:
            checkpoint = db.get(Job, self.jid).checkpoint
            self.assertNotIn("model:bad", checkpoint)
            self.assertIn("page:cache", checkpoint)

    def managed_job(self):
        with Session() as db:
            db.get(Job, self.jid).status = "FAILED"
            db.get(Workspace, self.wid).automation_enabled = True
            db.flush()
            run = pipeline.start(db, db.get(Lead, self.lid), "versioned-managed")
            db.flush()
            job = db.scalar(select(Job).where(Job.run_id == run.id))
            self.jid, self.rid = job.id, run.id
            db.commit()
        self.url = f"/workspaces/{self.wid}/jobs/{self.jid}"
        self.set_task()

    def test_artifact_and_next_stage_roll_back_together_on_finalize_error(self):
        self.managed_job()
        with patch("marketing_backend.pipeline.finalize", side_effect=RuntimeError("synthetic-private-marker")):
            job = self.run_job(lambda job, save: research())
        self.assertEqual(job.failure_code, "HANDLER_ERROR")
        with Session() as db:
            self.assertEqual(list(db.scalars(select(StageArtifact))), [])
            self.assertEqual(db.get(PreparationRun, self.rid).results, {})

    def test_next_stage_reads_immutable_research_instead_of_mutated_legacy_cache(self):
        self.managed_job()
        self.assertEqual(self.run_job(lambda job, save: research()).status, "COMPLETED")
        with Session() as db:
            run = db.get(PreparationRun, self.rid)
            run.results = {"RESEARCH": {"bad": True}}
            next_job = db.scalar(select(Job).where(Job.run_id == self.rid, Job.kind == "CONTACT_SEARCH"))
            self.assertEqual(next_job.product_line_id, self.line_id)
            db.commit()
        from marketing_backend.stages import result
        self.assertEqual(result(next_job, "RESEARCH"), research())

    def discovery_job(self):
        with Session() as db:
            db.get(Job, self.jid).status = "FAILED"
            db.get(Workspace, self.wid).automation_enabled = True
            snapshot = pipeline.context(db, self.wid)
            job = Job(workspace_id=self.wid, product_line_id=self.line_id, kind="DISCOVERY", managed=True,
                      idempotency_key="versioned-discovery", payload={"context": snapshot, "context_hash": pipeline.fingerprint(snapshot)})
            db.add(job)
            db.flush()
            self.jid = job.id
            db.commit()
        self.url = f"/workspaces/{self.wid}/jobs/{self.jid}"
        self.set_task(contract_name="discovery.candidate")
        return dict(candidates=[candidate()], evaluated_domains=[], coverage="Synthetic source-backed candidate fixture",
                    counts=dict(searches_attempted=1, searches_unavailable=0, websites_attempted=1,
                                pages_attempted=1, assessments_attempted=1, candidates_ready=1),
                    outcome="CANDIDATES_READY", human_review_required=True)

    def test_discovery_candidate_artifact_does_not_accept_or_send(self):
        batch = self.discovery_job()
        self.assertEqual(self.run_job(lambda job, save: batch).status, "COMPLETED")
        from marketing_backend.models import DiscoveryMemory, Approval
        with Session() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(StageArtifact)), 1)
            memory = db.scalar(select(DiscoveryMemory).where(DiscoveryMemory.workspace_id == self.wid))
            self.assertEqual(memory.outcome, "READY_FOR_REVIEW")
            self.assertIsNone(memory.accepted_lead_id)
            self.assertEqual(db.scalar(select(func.count()).select_from(Lead)), 1)
            self.assertEqual(list(db.scalars(select(Approval))), [])

    def test_duplicate_discovery_candidates_quarantine_before_persistence(self):
        batch = self.discovery_job()
        batch["candidates"] *= 2
        batch["counts"]["candidates_ready"] = 2
        self.assertEqual(self.run_job(lambda job, save: batch).status, "QUARANTINED")
        with Session() as db:
            self.assertEqual(list(db.scalars(select(StageArtifact))), [])
