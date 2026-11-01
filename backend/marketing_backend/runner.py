"""Common runtime for one stage, delivery channel or scheduler pool."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import os
import signal
import threading
import time
from .pools import POOLS, get_pool

log = logging.getLogger("marketing-pool")


def scheduler_tick():
    from .db import Session
    from .pipeline import schedule
    from .queue import recover_expired
    from .sending import recover_expired as recover_deliveries
    # Independent transactions ensure one failed operation does not roll back
    # or starve all other recovery responsibilities.
    failed = False
    for label,operation in (("job_recovery",recover_expired),("delivery_recovery",recover_deliveries),("discovery_schedule",schedule)):
        try:
            with Session() as db:
                operation(db)
        except Exception:
            log.error(json.dumps(dict(pool="SCHEDULER", event="RECOVERY_FAILED",
                operation=label, error_code="HANDLER_ERROR")))
            failed = True
    if failed:
        raise RuntimeError("Scheduler operation unavailable")


def tick(pool_name):
    from .db import Session
    pool = get_pool(pool_name)
    if pool.kind == "scheduler":
        scheduler_tick()
        return False
    if pool.kind == "stage":
        from . import queue
        from .worker import execute
        with Session() as db:
            job = queue.claim(db, pool=pool.name)
        if job:
            execute(job)
            return True
        return False
    from .sending import claim_attempt, execute_attempt
    with Session() as db:
        attempt = claim_attempt(db, pool=pool.name)
    if attempt:
        with Session() as db:
            execute_attempt(db, *attempt, pool=pool.name)
        return True
    return False


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", choices=tuple(POOLS), default=os.getenv("WORKER_POOL"))
    parser.add_argument("--concurrency", type=int, default=os.getenv("WORKER_CONCURRENCY", "1"))
    parser.add_argument("--once", action="store_true", help="One claim/recovery cycle per configured slot")
    args = parser.parse_args(argv)
    if args.pool not in POOLS:
        parser.error("Select exactly one --pool or WORKER_POOL")
    if not 1 <= args.concurrency <= 8:
        parser.error("Concurrency must be between 1 and 8")
    if args.pool == "SCHEDULER" and args.concurrency != 1:
        parser.error("Scheduler concurrency must be 1")
    return args


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    stopped = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stopped.set())
    def work():
        while not stopped.is_set():
            try:
                busy = tick(args.pool)
            except Exception:
                log.error(json.dumps(dict(pool=args.pool, event="POOL_UNAVAILABLE", error_code="HANDLER_ERROR")))
                if args.once:
                    raise
                stopped.wait(5)
                continue
            if args.once:
                return
            if not busy:
                stopped.wait(2)
    from .runtime_health import monitor, publish
    publish(args.pool, False, args.concurrency)
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(work) for _ in range(args.concurrency)]
        health = threading.Thread(target=monitor, args=(args.pool,args.concurrency,stopped,futures), daemon=True)
        health.start()
        try:
            for future in futures:
                future.result()
        finally:
            stopped.set()
            health.join(timeout=6)
            publish(args.pool, False, args.concurrency)


if __name__ == "__main__":
    main()
