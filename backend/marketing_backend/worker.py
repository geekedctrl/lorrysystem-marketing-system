import logging, signal, threading
from .db import Session
from . import queue
from .research import research, ProviderFailure

log = logging.getLogger("marketing-worker")
stop = threading.Event()


def execute(job, handler=None):
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
            queue.complete(db, job.id, job.lease_token, result, review=not job.managed)
    except queue.LeaseLost:
        log.warning("Lease lost for job %s; no stale result saved", job.id)
    except ProviderFailure as exc:
        try:
            from .pipeline import schedule

            with Session() as db:
                schedule(db)
            with Session() as db:
                queue.fail(db, job.id, job.lease_token, exc.code, exc.retryable)
        except queue.LeaseLost:
            log.warning("Lease lost for job %s", job.id)
    except Exception:
        # Never log source/provider payloads or credentials.
        log.error("Unhandled handler error for job %s", job.id)
        try:
            with Session() as db:
                queue.fail(db, job.id, job.lease_token, "HANDLER_ERROR")
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
                schedule(db)
                job = queue.claim(db)
            if job:
                execute(job)
            else:
                stop.wait(2)
        except Exception:
            log.error("Queue unavailable; waiting before reconnect")
            stop.wait(5)


if __name__ == "__main__":
    main()
