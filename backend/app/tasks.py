from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update
import redis
from .celery_app import celery
from .config import settings
from .db import SessionLocal
from .models import Source, Job
from . import pipeline, settings_store
from .collectors import CollectError
from .wordpress import WordPress, WPError
from .logs import record

r = redis.Redis.from_url(settings.redis_url)

def _lock(name, ttl):
    return r.set(f"kazi:lock:{name}", "1", nx=True, ex=ttl)

def _unlock(name):
    r.delete(f"kazi:lock:{name}")

@celery.task(name="app.tasks.tick")
def tick():
    """Runs every minute. Decides what is due based on DB state, so restarts lose nothing."""
    db = SessionLocal()
    try:
        cfg = settings_store.get_all(db)
        if not cfg["automation_enabled"]:
            return "disabled"
        now = datetime.now(timezone.utc)
        for s in db.scalars(select(Source).where(Source.enabled.is_(True))):
            interval = s.interval_minutes or cfg["collect_interval_minutes"]
            last = s.last_run_at
            if last and last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if not last or now - last >= timedelta(minutes=interval):
                collect_source.delay(s.id)
        pipeline.expire_jobs(db)
        if cfg["auto_publish"]:
            # Recover jobs stuck in 'publishing' (worker crashed) after 15 minutes
            db.execute(update(Job).where(Job.status == "publishing", Job.updated_at < now - timedelta(minutes=15))
                       .values(status="validated"))
            db.commit()
            ids = db.scalars(select(Job.id).where(Job.status.in_(["validated", "failed"]),
                                                  Job.publish_attempts < cfg["max_publish_attempts"])
                             .order_by(Job.id).limit(20)).all()
            for jid in ids:
                publish_job.delay(jid)
        return "ok"
    finally:
        db.close()

@celery.task(name="app.tasks.collect_source", bind=True, max_retries=3, default_retry_delay=300)
def collect_source(self, source_id: int):
    if not _lock(f"src:{source_id}", 900):
        return "already running"
    db = SessionLocal()
    try:
        s = db.get(Source, source_id)
        if not s or not s.enabled:
            return "skipped"
        return {k: v for k, v in pipeline.run_source(db, s).items() if k != "preview"}
    except CollectError as e:
        if e.temporary:
            raise self.retry(exc=e)
        return f"error: {e}"
    finally:
        db.close()
        _unlock(f"src:{source_id}")

@celery.task(name="app.tasks.publish_job", bind=True, max_retries=3, default_retry_delay=120)
def publish_job(self, job_id: int, force: bool = False):
    db = SessionLocal()
    try:
        cfg = settings_store.get_all(db)
        # Atomic claim prevents two workers publishing the same job
        allowed = ["validated", "failed"] + (["rejected"] if force else [])
        claimed = db.execute(update(Job).where(Job.id == job_id, Job.status.in_(allowed), Job.wp_post_id.is_(None))
                             .values(status="publishing", publish_attempts=Job.publish_attempts + 1)).rowcount
        db.commit()
        if not claimed:
            return "not publishable"
        job = db.get(Job, job_id)
        src = db.get(Source, job.source_id) if job.source_id else None
        allow_img = bool(src and (src.config or {}).get("allow_featured_image"))
        try:
            res = WordPress().publish(job, cfg, allow_img)
        except WPError as e:
            job.status = "failed"
            job.last_error = str(e)
            record(db, "ERROR", "publish_failed", f"{job.title[:120]}: {e}", job_id=job.id)
            if e.temporary and job.publish_attempts < cfg["max_publish_attempts"]:
                raise self.retry(exc=e)
            return f"failed: {e}"
        job.status = "published"
        job.wp_post_id = res["id"]
        job.wp_link = res.get("link")
        job.last_error = None
        record(db, "INFO", "published", f"{job.title[:120]} -> WP #{res['id']}{' (already existed)' if res['duplicate'] else ''}", job_id=job.id)
        return res
    finally:
        db.close()
