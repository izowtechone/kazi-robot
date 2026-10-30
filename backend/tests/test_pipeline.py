"""Run: docker compose exec backend pytest -q   (or locally with sqlite)"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
from datetime import date
from pathlib import Path
from unittest import mock
import pytest
from fastapi.testclient import TestClient
from app.db import engine, SessionLocal
from app.models import Base, Source, Job, User
from app import pipeline, processing, settings_store
from app.security import hash_password
import feedparser

SAMPLE = (Path(__file__).parents[1] / "app" / "sample_feed.xml").read_bytes()

@pytest.fixture()
def db():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    s = SessionLocal(); yield s; s.close()

def fake_fetch(url, headers=None):
    return mock.Mock(content=SAMPLE, text=SAMPLE.decode(), status_code=200)

def make_source(db):
    s = Source(name="Sample", type="rss", url="http://backend:8000/api/sample-feed.xml", country="Tanzania", reliability=90, config={})
    db.add(s); db.commit(); return s

def test_collect_process_and_duplicates(db):
    src = make_source(db)
    with mock.patch("app.collectors._fetch", fake_fetch):
        st = pipeline.run_source(db, src)
        assert st["fetched"] == 4
        assert st["duplicates"] == 1           # same title+employer+country
        jobs = {j.title: j for j in db.query(Job).all()}
        dev = jobs["[TEST] Software Developer"]
        assert dev.status == "validated" and dev.country == "Tanzania" and dev.category == "Information Technology"
        assert dev.deadline == date(2099, 12, 31)
        assert "Python" in (dev.qualifications or "")
        assert jobs["[TEST] Registered Nurse"].status == "expired" and jobs["[TEST] Registered Nurse"].country == "Kenya"
        acc = jobs["[TEST] Accountant"]
        assert acc.status == "rejected" and "missing:employer" in acc.rejection_reasons
        assert acc.employer is None            # never fabricated
        st2 = pipeline.run_source(db, src)     # second run: all duplicates
        assert st2["new"] == 0 and st2["duplicates"] == 4

def test_low_reliability_rejected(db):
    cfg = settings_store.get_all(db)
    job = processing.enrich({"title": "Driver", "employer": "X", "description": "Driver job in Kigali",
                             "source_url": "https://a.b/c", "apply_url": "https://a.b/apply"}, None)
    assert processing.validate(job, cfg, 90)[0] == "validated"
    status, reasons = processing.validate(job, cfg, 10)
    assert status == "rejected" and "low_source_reliability:10" in reasons

def test_publish_once(db):
    src = make_source(db)
    with mock.patch("app.collectors._fetch", fake_fetch):
        pipeline.run_source(db, src)
    job = db.query(Job).filter(Job.status == "validated").first()
    fake_wp = mock.Mock(); fake_wp.publish.return_value = {"id": 42, "link": "https://wp/x", "duplicate": False}
    with mock.patch("app.tasks.WordPress", return_value=fake_wp):
        from app.tasks import publish_job
        publish_job.apply(args=[job.id]).get()
        assert publish_job.apply(args=[job.id]).get() == "not publishable"
    db.refresh(job)
    assert job.status == "published" and job.wp_post_id == 42
    assert fake_wp.publish.call_count == 1

def test_api_auth_and_roles(db):
    db.add(User(email="a@x.io", hashed_password=hash_password("supersecret1"), role="admin"))
    db.add(User(email="v@x.io", hashed_password=hash_password("supersecret1"), role="viewer")); db.commit()
    from app.main import app
    c = TestClient(app)
    assert c.get("/api/stats").status_code == 401
    assert c.post("/api/auth/login", json={"email": "a@x.io", "password": "wrong"}).status_code == 401
    t = c.post("/api/auth/login", json={"email": "a@x.io", "password": "supersecret1"}).json()["access_token"]
    assert c.get("/api/stats", headers={"Authorization": f"Bearer {t}"}).status_code == 200
    vt = c.post("/api/auth/login", json={"email": "v@x.io", "password": "supersecret1"}).json()["access_token"]
    assert c.get("/api/users", headers={"Authorization": f"Bearer {vt}"}).status_code == 403
    assert "app_password" not in str(c.get("/api/wordpress", headers={"Authorization": f"Bearer {t}"}).json())
