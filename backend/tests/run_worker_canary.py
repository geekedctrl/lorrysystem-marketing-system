"""Run the guarded synthetic canary and export its measured comparison."""
import argparse
import os
from pathlib import Path
import sys
import unittest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",required=True)
    args=parser.parse_args()
    from marketing_backend.db import engine
    if os.getenv("APP_ENV")!="test" or engine.url.database!="marketing_rebuild_test":
        raise RuntimeError("Use only the dedicated backend test service and database")
    os.environ["SYNTHETIC_CANARY_REPORT_DIR"]=str(Path(args.output_dir).resolve())
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    suite=unittest.defaultTestLoader.loadTestsFromName(
        "test_worker_pools.WorkerPoolTests.test_synthetic_discovery_canary_preserves_candidate_contract_and_history")
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__=="__main__":main()
