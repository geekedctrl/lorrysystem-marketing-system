import argparse
from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import dialect
from marketing_backend.pools import POOLS,STAGES,get_pool
from marketing_backend.runner import parse_args,tick,scheduler_tick
from marketing_backend.runtime_health import publish,check,path_for
from marketing_backend.channels import adapter_for,AdapterUnavailable


class PoolRuntimeUnitTests(unittest.TestCase):
    def test_registry_routes_each_stage_and_channel_exactly_once(self):
        self.assertEqual(len(POOLS),11)
        self.assertEqual([p.stages[0] for p in POOLS.values() if p.kind=="stage"],list(STAGES))
        self.assertEqual({c for p in POOLS.values() for c in p.channels},{"EMAIL","LINKEDIN","MESSAGING"})
        for name in ("",None,"ALL","research","arbitrary.module"):
            with self.assertRaises(ValueError):get_pool(name)

    def test_cli_requires_one_pool_and_bounded_concurrency(self):
        with patch.dict(os.environ,{},clear=True),patch("sys.stderr"):
            for args in ([],["--pool","ALL"],["--pool","RESEARCH","--concurrency","0"],
                ["--pool","RESEARCH","--concurrency","9"],["--pool","SCHEDULER","--concurrency","2"]):
                with self.assertRaises(SystemExit):parse_args(args)
        self.assertEqual(parse_args(["--pool","DISCOVERY","--concurrency","2"]).concurrency,2)

    def test_stage_tick_never_claims_delivery_or_schedules(self):
        @contextmanager
        def session():yield Mock()
        with patch("marketing_backend.db.Session",session),patch("marketing_backend.queue.claim",return_value=None) as claim,\
             patch("marketing_backend.sending.claim_attempt") as delivery,patch("marketing_backend.pipeline.schedule") as schedule:
            self.assertFalse(tick("SCORING"))
            self.assertEqual(claim.call_args.kwargs,{"pool":"SCORING"})
            delivery.assert_not_called();schedule.assert_not_called()

    def test_scheduler_attempts_other_recoveries_after_one_operation_fails(self):
        @contextmanager
        def session():yield Mock()
        with patch("marketing_backend.db.Session",session),patch("marketing_backend.queue.recover_expired",side_effect=RuntimeError) as jobs,\
             patch("marketing_backend.sending.recover_expired") as deliveries,patch("marketing_backend.pipeline.schedule") as schedule,\
             patch("marketing_backend.runner.log"):
            with self.assertRaises(RuntimeError):scheduler_tick()
            jobs.assert_called_once();deliveries.assert_called_once();schedule.assert_called_once()

    def test_readiness_rejects_wrong_pool_stopped_and_stale_process(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{"WORKER_HEALTH_DIR":folder}):
            publish("RESEARCH",True,1);self.assertTrue(check("RESEARCH"))
            publish("RESEARCH",False,1);self.assertFalse(check("RESEARCH"))
            publish("RESEARCH",True,1)
            with patch("marketing_backend.runtime_health.time.time",return_value=10**12):self.assertFalse(check("RESEARCH"))
            with self.assertRaises(OSError):check("DISCOVERY")

    def test_fake_channels_are_explicit_and_disabled_outside_acceptance(self):
        delivery=SimpleNamespace(channel="LINKEDIN",id="fixture",snapshot={"body":"synthetic"})
        for env in ({},{"APP_ENV":"production","DELIVERY_ADAPTER_MODE":"synthetic"}):
            with patch.dict(os.environ,env,clear=True):
                with self.assertRaises(AdapterUnavailable):adapter_for("LINKEDIN")
        with patch.dict(os.environ,{"APP_ENV":"test","DELIVERY_ADAPTER_MODE":"synthetic"},clear=True):
            adapter=adapter_for("LINKEDIN")
            self.assertEqual(adapter.handoff(delivery),adapter.handoff(delivery))
            with self.assertRaises(AdapterUnavailable):adapter_for("EMAIL")

    def test_pool_migration_has_no_implicit_sql_bind_parameters(self):
        path=Path(__file__).resolve().parents[1]/"migrations/versions/017_worker_pools.py"
        spec=importlib.util.spec_from_file_location("pool_migration",path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        rows=[]
        with patch.object(module.op,"execute",side_effect=rows.append):module.upgrade()
        for sql in rows:self.assertEqual(text(sql).compile(dialect=dialect()).construct_params(),{})

    def test_query_canary_can_route_back_to_prior_strategy(self):
        from marketing_backend.discovery_strategies import select_queries
        job=SimpleNamespace(payload={"context":{"preferences":{"discovery_query_strategy":"official"}}})
        self.assertEqual(select_queries(job).version,"icp-queries.2")
        job.payload["context"]["preferences"]["discovery_query_strategy"]="baseline"
        self.assertEqual(select_queries(job).version,"icp-queries.1")
