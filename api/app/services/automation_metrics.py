"""Observed request usage and optional estimates; never infer provider invoices."""

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from sqlalchemy import select
from app.db.session import ControlSession
from app.models.automation import AutomationJob, AutomationWorker
from app.services.automation_status import describe_job


def rate(name):
    try:
        value = Decimal(os.getenv(name, ""))
        return value if value.is_finite() and 0 <= value <= 100000 else None
    except InvalidOperation:
        return None


def usage_snapshot(usage):
    cost = Decimal(0)
    known = True
    for count, variable, divisor in (
        (usage["search_requests"], "AUTOMATION_SEARCH_USD_PER_REQUEST", 1),
        (usage["input_tokens"], "AUTOMATION_LLM_INPUT_USD_PER_MILLION", 1000000),
        (usage["output_tokens"], "AUTOMATION_LLM_OUTPUT_USD_PER_MILLION", 1000000),
    ):
        if count == 0:
            continue
        price = rate(variable)
        if count is None or price is None:
            known = False
        else:
            cost += Decimal(count) * price / divisor
    if not usage["model_requests"]:
        known = (
            usage["search_requests"] == 0
            or rate("AUTOMATION_SEARCH_USD_PER_REQUEST") is not None
        )
    return {
        **usage,
        "estimated_cost_usd": (
            str(cost.quantize(Decimal("0.000001"))) if known else None
        ),
        "cost_basis": (
            "configured_rates" if known else "rates_or_token_usage_unavailable"
        ),
    }


def operational_summary(db, jobs, current_ids, enabled):
    now = datetime.now(timezone.utc)
    with ControlSession() as control:
        workers = list(
            control.scalars(
                select(AutomationWorker).where(AutomationWorker.active.is_(True))
            )
        )
        seen = max(
            (worker.last_seen_at for worker in workers if worker.last_seen_at),
            default=None,
        )
    state = (
        "NOT_CONNECTED"
        if not workers
        else "ONLINE" if seen and seen >= now - timedelta(minutes=3) else "OFFLINE"
    )
    week = list(
        db.scalars(
            select(AutomationJob)
            .where(AutomationJob.created_at >= now - timedelta(days=7))
            .order_by(AutomationJob.created_at.desc())
        )
    )
    measured = [job for job in week if job.usage]
    total = {
        key: sum(job.usage.get(key) or 0 for job in measured)
        for key in (
            "search_requests",
            "fetch_requests",
            "model_requests",
            "input_tokens",
            "output_tokens",
        )
    }
    estimates = [
        Decimal(job.usage["estimated_cost_usd"])
        for job in measured
        if job.usage.get("estimated_cost_usd") is not None
    ]
    providers = {}
    for provider in ("search", "model"):
        observed = next(
            (
                job
                for job in measured
                if job.usage.get(provider + "_status") in ("OK", "ERROR")
            ),
            None,
        )
        providers[provider] = {
            "status": observed.usage[provider + "_status"] if observed else "UNKNOWN",
            "observed_at": observed.finished_at if observed else None,
        }
    stalled = [
        describe_job(job, True, enabled, now)
        for job in jobs
        if job.id in current_ids and describe_job(job, True, enabled, now)["stalled"]
    ]
    return {
        "worker_state": state,
        "worker_last_seen_at": seen,
        "providers": providers,
        "stalled_jobs": stalled,
        "period_days": 7,
        "usage": total,
        "measured_jobs": len(measured),
        "unmeasured_finished_jobs": sum(
            job.status in ("COMPLETED", "FAILED", "NEEDS_REVIEW") and not job.usage
            for job in week
        ),
        "estimated_cost_usd": str(sum(estimates, Decimal(0))) if estimates else None,
        "cost_complete": bool(measured) and len(estimates) == len(measured),
        "token_usage_complete": all(
            job.usage.get("input_tokens") is not None
            and job.usage.get("output_tokens") is not None
            for job in measured
            if job.usage.get("model_requests")
        ),
    }
