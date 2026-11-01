"""Local process readiness without exposing credentials or application data."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import threading
import time


def path_for(pool):
    return Path(os.getenv("WORKER_HEALTH_DIR", tempfile.gettempdir())) / ("native-pool-" + pool + ".json")


def publish(pool, ready, concurrency):
    target = path_for(pool)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = dict(pool=pool, pid=os.getpid(), ready=bool(ready), concurrency=concurrency, updated_at=time.time())
    fd, name = tempfile.mkstemp(dir=target.parent, prefix="pool-health-")
    try:
        with os.fdopen(fd, "w") as output:
            json.dump(data, output)
        os.replace(name, target)
    finally:
        Path(name).unlink(missing_ok=True)


def check(pool):
    from .pools import get_pool
    get_pool(pool)
    data = json.loads(path_for(pool).read_text())
    os.kill(data["pid"], 0)
    return data["pool"] == pool and data["ready"] is True and 0 <= time.time()-data["updated_at"] < 20


def monitor(pool, concurrency, stop, futures):
    from sqlalchemy import text
    from .db import Session
    from .pools import get_pool
    kind=get_pool(pool).kind
    probe={"stage":"SELECT kind,status,lease_until FROM jobs LIMIT 0",
        "delivery":"SELECT channel,status,trace_id FROM deliveries LIMIT 0",
        "scheduler":"SELECT next_discovery_at FROM product_lines LIMIT 0"}[kind]
    while not stop.is_set():
        ready = all(not f.done() for f in futures)
        try:
            with Session() as db:
                db.execute(text(probe))
        except Exception:
            ready = False
        publish(pool, ready, concurrency)
        stop.wait(5)
    publish(pool, False, concurrency)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", required=True)
    args = parser.parse_args()
    try:
        success = check(args.pool)
    except (OSError, ValueError, KeyError, TypeError):
        success = False
    raise SystemExit(0 if success else 1)


if __name__ == "__main__":
    main()
