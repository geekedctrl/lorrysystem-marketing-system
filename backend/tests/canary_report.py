"""Aggregate synthetic canary evidence without exporting company or contact data."""
import json
import os
from pathlib import Path
from sqlalchemy import select
from marketing_backend.models import Job,StageArtifact,ProviderUsage
from marketing_backend.artifacts import consume_artifact
from marketing_backend.stage_contracts import ContractViolation


def collect(db, groups):
    """Read only the explicitly identified discovery jobs before context rollback."""
    from marketing_backend.db import engine
    if os.getenv("APP_ENV")!="test" or engine.url.database!="marketing_rebuild_test":
        raise RuntimeError("Synthetic canary collection requires the disposable test database")
    result={}
    for label,job_ids in groups.items():
        jobs=list(db.scalars(select(Job).where(Job.id.in_(job_ids))))
        if len(jobs)!=len(job_ids) or not jobs or any(j.kind!="DISCOVERY" for j in jobs):
            raise ValueError("Identify completed discovery jobs explicitly")
        rows=list(db.scalars(select(StageArtifact).where(StageArtifact.job_id.in_(job_ids),
            StageArtifact.contract_name=="discovery.candidate")))
        valid=0;domains=[]
        for row in rows:
            try:
                candidate=consume_artifact(db,row.id,row.workspace_id,row.product_line_id,row.context_version,row.context_hash)
                valid+=1;domains.append(candidate["domain"])
            except ContractViolation:
                continue
        usage=list(db.scalars(select(ProviderUsage).where(ProviderUsage.job_id.in_(job_ids))))
        calls={name:sum(j.checkpoint.get("synthetic_provider_calls",{}).get(name,0) for j in jobs)
            for name in ("MODEL","SEARCH")}
        duplicates=len(domains)-len(set(domains))
        result[label]=dict(discovery_jobs=len(jobs),completed_jobs=sum(j.status=="COMPLETED" for j in jobs),
            candidates=len(rows),evidence_valid_candidates=valid,
            evidence_validity_rate=valid/len(rows) if rows else None,
            duplicate_candidates=duplicates,duplicate_rate=duplicates/len(rows) if rows else None,
            failed_jobs=sum(j.status=="FAILED" for j in jobs),
            quarantined_jobs=sum(j.status=="QUARANTINED" for j in jobs),
            synthetic_provider_calls=calls,synthetic_provider_requests=sum(calls.values()),
            provider_reservations=len(usage),reserved_microusd=sum(u.estimated_microusd for u in usage),
            query_versions=sorted({r.strategy_versions.get("query","unknown") for r in rows}))
    return dict(report_version=1,mode="synthetic",scope="Explicit discovery jobs before rollback",
        measurements=result,proof={},limits=[
            "Provider requests are counted fake adapter invocations, not external calls.",
            "Reservation totals describe the test ledger, not measured provider bills.",
            "Evidence validity means the fixture passed candidate and artifact validation, not independent factual verification.",
            "Small deterministic fixtures do not establish real-world search quality or conversion rates."])


def evaluate(report):
    before,after=(report["measurements"][k] for k in ("baseline","canary"))
    checks=dict(all_discovery_jobs_completed=all(x["completed_jobs"]==x["discovery_jobs"] for x in (before,after)),
        candidates_available=before["candidates"]>0 and after["candidates"]>0,
        candidate_count_preserved=after["candidates"]>=before["candidates"],
        evidence_valid=before["evidence_validity_rate"]==after["evidence_validity_rate"]==1,
        no_duplicate_candidates=before["duplicate_candidates"]==after["duplicate_candidates"]==0,
        no_failures_or_quarantine=all(x[k]==0 for x in (before,after) for k in ("failed_jobs","quarantined_jobs")),
        fake_request_count_not_increased=after["synthetic_provider_requests"]<=before["synthetic_provider_requests"],
        no_provider_reservations=before["provider_reservations"]==after["provider_reservations"]==0,
        downstream_compatible=report["proof"].get("downstream_research_outputs")==2,
        historical_artifacts_retained=report["proof"].get("historical_artifacts_retained") is True,
        human_acceptance_retained=report["proof"].get("human_acceptance_retained") is True,
        rollback_routes_to_baseline=report["proof"].get("rollback_query_strategy")=="baseline")
    report["checks"]=checks;report["passed"]=all(checks.values())
    return report


def markdown(report):
    metrics=report["measurements"];lines=["# Synthetic discovery canary comparison","",
        "Result: "+("PASS" if report["passed"] else "FAIL"),"",
        "| Metric | Baseline | Canary |","| --- | --- | --- |"]
    for key,label in (("query_versions","Query strategy"),("candidates","Candidates"),
        ("evidence_valid_candidates","Valid candidate evidence"),("evidence_validity_rate","Evidence validity rate"),
        ("duplicate_candidates","Duplicate candidates"),("duplicate_rate","Duplicate rate"),
        ("failed_jobs","Failed jobs"),("quarantined_jobs","Quarantined jobs"),
        ("synthetic_provider_requests","Fake provider requests"),("provider_reservations","Provider reservations"),
        ("reserved_microusd","Reserved microusd")):
        values=[metrics[k][key] for k in ("baseline","canary")]
        if key.endswith("_rate"):values=[f"{v:.0%}" if v is not None else "Not available" for v in values]
        lines.append("| "+label+" | "+" | ".join(", ".join(v) if isinstance(v,list) else str(v) for v in values)+" |")
    lines.extend(["","## Compatibility and rollback",""])
    lines.extend("- "+key.replace("_"," ")+": "+str(value) for key,value in report["proof"].items())
    lines.extend(["","## Measurement limits",""]+['- '+v for v in report['limits']])
    return "\n".join(lines)+"\n"


def export(report, directory):
    folder=Path(directory);folder.mkdir(parents=True,exist_ok=True)
    (folder/"canary-comparison.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    (folder/"canary-comparison.md").write_text(markdown(report),encoding="utf-8")
