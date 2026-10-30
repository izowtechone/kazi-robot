from celery import Celery
from .config import settings

celery = Celery("kazirobot", broker=settings.redis_url, backend=settings.redis_url, include=["app.tasks"])
celery.conf.update(
    task_acks_late=True,               # re-delivered if worker dies mid-task
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    timezone="Africa/Dar_es_Salaam",
    beat_schedule={
        # A single tick each minute; real intervals are read from DB settings so they
        # can be changed from the dashboard and survive restarts.
        "tick": {"task": "app.tasks.tick", "schedule": 60.0},
    },
)
app = celery
