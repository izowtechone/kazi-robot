"""Collect -> process -> validate -> store. Shared by Celery tasks and API 'test' endpoints."""
from datetime import datetime, timezone
from sqlalchemy import select, or_, update
from sqlalchemy.orm import Session
from .models import Source, Job
from . import collectors, processing, settings_store
from .logs import record

def run_source(db: Session, source: Source, dry_run: bool = False) -> dict:
    cfg = settings_store.get_all(db)
    stats = {"fetched": 0, "new": 0, "duplicates": 0, "validated": 0, "rejected": 0, "expired": 0, "preview": []}
    try:
        raws = collectors.collect(source)
    except collectors.CollectError as e:
        if not dry_run:
            source.last_run_at = datetime.now(timezone.utc)
            source.last_status = "error"
            source.last_message = str(e)
            source.consecutive_failures += 1
            # Source reliability check: repeated failures lower reliability
            if source.consecutive_failures >= 3:
                source.reliability = max(0, source.reliability - 5)
            record(db, "ERROR", "collect_failed", f"{source.name}: {e}", source_id=source.id)
        raise
    stats["fetched"] = len(raws)
    seen = set()
    for raw in raws:
        if not raw.get("source_url") or not raw.get("title"):
            stats["rejected"] += 1
            continue
        job = processing.enrich(raw, source.country)
        status, reasons = processing.validate(job, cfg, source.reliability)
        if dry_run:
            stats["preview"].append({**{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in job.items()},
                                     "status": status, "reasons": reasons})
            continue
        if job["fingerprint"] in seen or db.scalar(select(Job.id).where(or_(
                Job.fingerprint == job["fingerprint"], Job.source_url == job["source_url"]))):
            stats["duplicates"] += 1
            continue
        seen.add(job["fingerprint"])
        j = Job(source_id=source.id, status=status, rejection_reasons=reasons, **job)
        db.add(j)
        db.flush()
        stats["new"] += 1
        stats[status] += 1
        if status != "validated":
            record(db, "WARNING", f"job_{status}", f"{j.title[:120]}: {', '.join(reasons)}", job_id=j.id, source_id=source.id, commit=False)
    if not dry_run:
        source.last_run_at = datetime.now(timezone.utc)
        source.last_status = "ok"
        source.consecutive_failures = 0
        source.last_message = f"fetched {stats['fetched']}, new {stats['new']}, duplicates {stats['duplicates']}"
        record(db, "INFO", "collect_ok", f"{source.name}: {source.last_message}", source_id=source.id, commit=False)
        db.commit()
    return stats

def expire_jobs(db: Session) -> int:
    today = datetime.now(timezone.utc).date()
    res = db.execute(update(Job).where(Job.status.in_(["collected", "validated", "failed"]), Job.deadline < today)
                     .values(status="expired"))
    db.commit()
    return res.rowcount or 0
