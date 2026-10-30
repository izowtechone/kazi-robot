from sqlalchemy.orm import Session
from .models import Setting

DEFAULTS = {
    "automation_enabled": True,
    "collect_interval_minutes": 60,
    "auto_publish": True,
    "wp_post_status": "publish",          # publish | draft | pending
    "wp_default_categories": ["Jobs"],
    "wp_extra_tags": [],
    "use_job_category_as_wp_category": True,
    "use_country_as_tag": True,
    "required_fields": ["title", "employer", "description", "source_url"],
    "require_apply_method": True,          # apply_url OR how_to_apply
    "min_source_reliability": 50,
    "max_publish_attempts": 5,
    "max_job_age_days": 45,
    "allowed_countries": ["Tanzania", "Kenya", "Uganda", "Rwanda", "Burundi"],
}

def get_all(db: Session) -> dict:
    data = dict(DEFAULTS)
    for s in db.query(Setting).all():
        data[s.key] = s.value
    return data

def get(db: Session, key: str):
    s = db.get(Setting, key)
    return s.value if s else DEFAULTS.get(key)

def update(db: Session, values: dict) -> dict:
    for k, v in values.items():
        if k not in DEFAULTS:
            raise ValueError(f"Unknown setting: {k}")
        s = db.get(Setting, k)
        if s:
            s.value = v
        else:
            db.add(Setting(key=k, value=v))
    db.commit()
    return get_all(db)
