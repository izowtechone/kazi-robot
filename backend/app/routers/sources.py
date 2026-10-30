from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Source
from ..schemas import SourceIn, SourceOut
from ..deps import require
from .. import pipeline
from ..collectors import CollectError

router = APIRouter(prefix="/api/sources", tags=["sources"])

def _get(db, sid):
    s = db.get(Source, sid)
    if not s:
        raise HTTPException(404, "Source not found")
    return s

@router.get("", response_model=list[SourceOut])
def list_sources(db: Session = Depends(get_db), _=Depends(require("viewer"))):
    return db.query(Source).order_by(Source.id).all()

@router.post("", response_model=SourceOut, status_code=201)
def create(body: SourceIn, db: Session = Depends(get_db), _=Depends(require("editor"))):
    s = Source(**{**body.model_dump(), "url": str(body.url)})
    db.add(s); db.commit()
    return s

@router.put("/{sid}", response_model=SourceOut)
def update(sid: int, body: SourceIn, db: Session = Depends(get_db), _=Depends(require("editor"))):
    s = _get(db, sid)
    for k, v in body.model_dump().items():
        setattr(s, k, str(v) if k == "url" else v)
    db.commit()
    return s

@router.delete("/{sid}", status_code=204)
def delete(sid: int, db: Session = Depends(get_db), _=Depends(require("admin"))):
    db.delete(_get(db, sid)); db.commit()

@router.post("/{sid}/test")
def test(sid: int, db: Session = Depends(get_db), _=Depends(require("editor"))):
    """Fetch and process without saving: shows what would be collected."""
    try:
        stats = pipeline.run_source(db, _get(db, sid), dry_run=True)
    except CollectError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "fetched": stats["fetched"], "preview": stats["preview"][:10]}

@router.post("/{sid}/run")
def run_now(sid: int, db: Session = Depends(get_db), _=Depends(require("editor"))):
    """Collect immediately (synchronously) and store results."""
    try:
        stats = pipeline.run_source(db, _get(db, sid))
    except CollectError as e:
        return {"ok": False, "error": str(e)}
    stats.pop("preview")
    return {"ok": True, **stats}
