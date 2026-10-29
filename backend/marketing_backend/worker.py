import json, logging, signal, threading, time
from .db import Session
from . import queue
from .research import research, ProviderFailure
from .stage_contracts import ContractViolation

log = logging.getLogger("marketing-worker")
stop = threading.Event()


def execution_log(job, event, started, code=None, retryable=False):
    from .diagnostics import classify
    from .worker_contracts import event_version
    failure = classify(code, retryable) if code else None
    log.info(json.dumps(dict(
        event=event, pool="LEGACY", stage=job.kind, job_id=str(job.id),
        workspace_id=str(job.workspace_id), product_line_id=str(job.product_line_id),
        attempt=job.attempts, duration_ms=max(0, int((time.monotonic()-started)*1000)),
        contract_version=event_version(job), trace_id=str(job.trace_id),
        error_code=failure.code if failure else None,
        error_category=failure.category if failure else None,
        retryable=failure.retryable if failure else False,
    ), separators=(",", ":")))


def execute(job, handler=None):
    started = time.monotonic()
    def save(value):
        with Session() as db:
            queue.checkpoint(db, job.id, job.lease_token, value)

    done = threading.Event()

    def renew():
        while not done.wait(30):
            try:
                with Session() as db:
                    queue.heartbeat(db, job.id, job.lease_token)
            except Exception:
                log.warning("Heartbeat unavailable for job %s", job.id)

    renewer = threading.Thread(target=renew, daemon=True)
    renewer.start()
    try:
        from .worker_contracts import validate_task
        with Session() as db:
            current = queue.owned(db, job.id, job.lease_token)
            validate_task(db, current)
        if job.managed:
            from .stages import dispatch
            from .pipeline import valid_context

            with Session() as db:
                queue.owned(db, job.id, job.lease_token)
                valid_context(db, job)
            handler = handler or dispatch
        elif job.kind != "RESEARCH":
            raise ProviderFailure("UNSUPPORTED_JOB_KIND")
        else:
            handler = handler or research
        result = handler(job, save)
        with Session() as db:
            queue.complete(db, job.id, job.lease_token, result, review=not job.managed,
                           duration_ms=max(0, int((time.monotonic()-started)*1000)))
        execution_log(job, "COMPLETION", started)
    except queue.LeaseLost:
        execution_log(job, "LEASE_LOSS", started, "LEASE_LOST")
        log.warning("Lease lost for job %s; no stale result saved", job.id)
    except ContractViolation as exc:
        try:
            with Session() as db:
                queue.quarantine(db, job.id, job.lease_token, exc.code,
                                 duration_ms=max(0, int((time.monotonic()-started)*1000)))
            execution_log(job, "QUARANTINE", started, exc.code)
        except queue.LeaseLost:
            execution_log(job, "LEASE_LOSS", started, "LEASE_LOST")
    except ProviderFailure as exc:
        try:
            from .pipeline import schedule

            with Session() as db:
                schedule(db)
            with Session() as db:
                queue.fail(db, job.id, job.lease_token, exc.code, exc.retryable,
                           duration_ms=max(0, int((time.monotonic()-started)*1000)))
            execution_log(job, "FAILURE_OR_RETRY", started, exc.code, exc.retryable)
        except queue.LeaseLost:
            log.warning("Lease lost for job %s", job.id)
    except Exception:
        # Never log source/provider payloads or credentials.
        log.error("Unhandled handler error for job %s", job.id)
        try:
            with Session() as db:
                queue.fail(db, job.id, job.lease_token, "HANDLER_ERROR",
                           duration_ms=max(0, int((time.monotonic()-started)*1000)))
            execution_log(job, "FAILURE", started, "HANDLER_ERROR")
        except queue.LeaseLost:
            pass
    finally:
        done.set()
        renewer.join(timeout=2)


def main():
    logging.basicConfig(level=logging.INFO)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    while not stop.is_set():
        try:
            with Session() as db:
                from .pipeline import schedule
                from .sending import recover_expired, claim_attempt
                schedule(db)
                recover_expired(db)
                delivery_attempt = claim_attempt(db)
                job = queue.claim(db)
            if delivery_attempt:
                from .sending import execute_attempt
                with Session() as db:
                    execute_attempt(db, *delivery_attempt)
            elif job:
                execute(job)
            else:
                stop.wait(2)
        except Exception:
            log.error("Queue unavailable; waiting before reconnect")
            stop.wait(5)


if __name__ == "__main__":
    main()
