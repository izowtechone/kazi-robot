import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from .config import settings
from .db import engine
from .limiter import limiter
from .routers import auth, users, sources, jobs

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="Kazi Robot API", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
                   allow_methods=["*"], allow_headers=["Authorization", "Content-Type"])
for r in (auth.router, users.router, sources.router, jobs.router):
    app.include_router(r)

@app.get("/api/health")
def health():
    status = {"api": "ok"}
    try:
        with engine.connect() as c:
            c.execute(text("select 1"))
        status["database"] = "ok"
    except Exception as e:  # noqa
        status["database"] = f"error: {e.__class__.__name__}"
    try:
        import redis
        redis.Redis.from_url(settings.redis_url, socket_timeout=2).ping()
        status["redis"] = "ok"
    except Exception as e:  # noqa
        status["redis"] = f"error: {e.__class__.__name__}"
    code = 200 if all(v == "ok" for v in status.values()) else 503
    return JSONResponse(status, status_code=code)

SAMPLE = Path(__file__).parent / "sample_feed.xml"

@app.get("/api/sample-feed.xml", include_in_schema=False)
def sample_feed():
    return Response(SAMPLE.read_text(), media_type="application/rss+xml")
