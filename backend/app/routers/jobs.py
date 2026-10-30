from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Job, Source, Log
from ..schemas import JobOut
from ..deps import require
from ..wordpress import WordPress, WPError
from .. import settings_store
from ..logs import record

router = APIRouter(prefix="/api", tags=["jobs"])
Status = Literal["collected", "validated", "rejected", "expired", "publishing", "published", "failed"]

@router.get("/stats")
def stats(db: Session = Depends(get_db), _=Depends(require("viewer"))):
    counts = dict(db.execute(select(Job.status, func.count()).group_by(Job.status)).all())
    pub_ok = db.scalar(select(func.count()).select_from(Log).where(Log.event == "published")) or 0
    pub_fail = db.scalar(select(func.count()).select_from(Log).where(Log.event == "publish_failed")) or 0
    by_country = dict(db.execute(select(Job.country, func.count()).group_by(Job.country)).all())
    return {
        "total": sum(counts.values()), "by_status": counts,
        "published": counts.get("published", 0), "rejected": counts.get("rejected", 0),
        "expired": counts.get("expired", 0), "pending": counts.get("validated", 0) + counts.get("failed", 0),
        "active_sources": db.scalar(select(func.count()).select_from(Source).where(Source.enabled.is_(True))),
        "total_sources": db.scalar(select(func.count()).select_from(Source)),
        "publish_success": pub_ok, "publish_failure": pub_fail,
        "by_country": {k or "Unknown": v for k, v in by_country.items()},
    }

@router.get("/jobs")
def list_jobs(status: Status | None = None, q: str | None = Query(None, max_length=200),
              country: str | None = Query(None, max_length=40), page: int = Query(1, ge=1),
              page_size: int = Query(25, ge=1, le=100), db: Session = Depends(get_db), _=Depends(require("viewer"))):
    stmt = select(Job)
    if status:
        stmt = stmt.where(Job.status == status)
    if country:
        stmt = stmt.where(Job.country == country)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Job.title.ilike(like), Job.employer.ilike(like), Job.location.ilike(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Job.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "items": [JobOut.model_validate(r) for r in rows]}

@router.get("/jobs/{jid}", response_model=JobOut)
def get_job(jid: int, db: Session = Depends(get_db), _=Depends(require("viewer"))):
    j = db.get(Job, jid)
    if not j:
        raise HTTPException(404, "Not found")
    return j

@router.post("/jobs/{jid}/publish")
def publish_now(jid: int, force: bool = False, db: Session = Depends(get_db), _=Depends(require("editor"))):
    """Publish synchronously (used for testing). force=True allows publishing a rejected job manually."""
    from ..tasks import publish_job
    res = publish_job.apply(args=[jid, force]).get(propagate=False)
    j = db.get(Job, jid); db.refresh(j)
    return {"result": res if not isinstance(res, Exception) else str(res), "job": JobOut.model_validate(j)}

@router.post("/jobs/{jid}/requeue")
def requeue(jid: int, db: Session = Depends(get_db), _=Depends(require("editor"))):
    j = db.get(Job, jid)
    if not j or j.wp_post_id:
        raise HTTPException(400, "Job not found or already published")
    j.status = "validated"; j.publish_attempts = 0; j.last_error = None
    db.commit()
    return {"ok": True}

@router.delete("/jobs/{jid}", status_code=204)
def delete_job(jid: int, db: Session = Depends(get_db), _=Depends(require("admin"))):
    j = db.get(Job, jid)
    if j:
        db.delete(j); db.commit()

@router.get("/logs")
def logs(level: Literal["INFO", "WARNING", "ERROR"] | None = None, event: str | None = Query(None, max_length=60),
         page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
         db: Session = Depends(get_db), _=Depends(require("viewer"))):
    stmt = select(Log)
    if level:
        stmt = stmt.where(Log.level == level)
    if event:
        stmt = stmt.where(Log.event == event)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Log.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    from ..schemas import LogOut
    return {"total": total, "items": [LogOut.model_validate(r) for r in rows]}

@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _=Depends(require("viewer"))):
    return settings_store.get_all(db)

@router.put("/settings")
def put_settings(body: dict, db: Session = Depends(get_db), user=Depends(require("admin"))):
    try:
        out = settings_store.update(db, body)
    except ValueError as e:
        raise HTTPException(400, str(e))
    record(db, "INFO", "settings_changed", f"{user.email} updated: {', '.join(body.keys())}")
    return out

@router.get("/wordpress")
def wp_info(_=Depends(require("viewer"))):
    from ..config import settings
    u = settings.wp_username
    return {"configured": bool(settings.wp_url and u and settings.wp_app_password),
            "url": settings.wp_url, "username": (u[:2] + "***") if u else None}

@router.post("/wordpress/test")
def wp_test(db: Session = Depends(get_db), _=Depends(require("editor"))):
    try:
        res = WordPress().test()
        record(db, "INFO", "wp_test_ok", f"Connected as {res['user']}")
        return res
    except WPError as e:
        record(db, "ERROR", "wp_test_failed", str(e))
        return {"ok": False, "error": str(e)}
