import logging
from sqlalchemy.orm import Session
from .models import Log

logger = logging.getLogger("kazirobot")

def record(db: Session, level: str, event: str, message: str, job_id=None, source_id=None, commit=True):
    getattr(logger, level.lower() if level.lower() in ("info", "warning", "error") else "info")(f"[{event}] {message}")
    db.add(Log(level=level.upper(), event=event, message=message[:5000], job_id=job_id, source_id=source_id))
    if commit:
        db.commit()
