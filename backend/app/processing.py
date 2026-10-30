"""Normalization, detection and validation. Never invents data: unknown fields stay None."""
import hashlib, re
from datetime import date, datetime, timezone, timedelta
from bs4 import BeautifulSoup
from dateutil import parser as dparser

COUNTRIES = {
    "Tanzania": ["tanzania", "dar es salaam", "dodoma", "arusha", "mwanza", "zanzibar", "mbeya", "morogoro", "tanga", "moshi", "kilimanjaro", "iringa"],
    "Kenya": ["kenya", "nairobi", "mombasa", "kisumu", "nakuru", "eldoret", "thika", "machakos"],
    "Uganda": ["uganda", "kampala", "entebbe", "gulu", "mbarara", "jinja", "mbale"],
    "Rwanda": ["rwanda", "kigali", "huye", "musanze", "rubavu"],
    "Burundi": ["burundi", "bujumbura", "gitega", "ngozi"],
}

CATEGORIES = {
    "Information Technology": ["software", "developer", "it ", "ict", "network", "data", "programmer", "devops", "system administrator"],
    "Health": ["nurse", "doctor", "clinical", "medical", "health", "pharmac", "laboratory"],
    "Education": ["teacher", "lecturer", "tutor", "education", "school"],
    "Finance & Accounting": ["accountant", "finance", "audit", "accounting", "bank", "credit"],
    "Engineering": ["engineer", "civil", "mechanical", "electrical"],
    "Sales & Marketing": ["sales", "marketing", "business development", "brand"],
    "NGO & Development": ["programme", "program officer", "ngo", "humanitarian", "monitoring and evaluation", "m&e"],
    "Administration": ["administrat", "secretary", "receptionist", "office assistant", "clerk"],
    "Human Resources": ["human resource", "hr ", "recruit", "talent"],
    "Logistics & Transport": ["driver", "logistics", "procurement", "supply chain", "warehouse"],
    "Hospitality": ["hotel", "chef", "cook", "waiter", "hospitality", "tourism"],
    "Agriculture": ["agricultur", "farm", "agronom", "livestock"],
    "Legal": ["lawyer", "legal", "advocate", "compliance"],
}

DEADLINE_RE = re.compile(r"(?:deadline|closing date|apply before|applications? close[sd]?(?: on)?|last date)[^\w]{0,5}(?:is|:|-|on)?\s*([^\n.;<]{4,40})", re.I)

def clean_text(html: str | None) -> str | None:
    if not html:
        return None
    text = BeautifulSoup(html, "html.parser").get_text("\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return text or None

def norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()

def fingerprint(title: str, employer: str | None, country: str | None) -> str:
    return hashlib.sha256(f"{norm(title)}|{norm(employer)}|{norm(country)}".encode()).hexdigest()

def detect_country(*texts: str | None, default: str | None = None) -> str | None:
    blob = " " + " ".join(t or "" for t in texts).lower() + " "
    scores = {c: sum(blob.count(k) for k in kws) for c, kws in COUNTRIES.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else default

def detect_category(title: str, description: str | None) -> str | None:
    t = f" {(title or '').lower()} "
    d = f" {(description or '').lower()[:2000]} "
    scores = {c: sum(3 * t.count(k) + d.count(k) for k in kws) for c, kws in CATEGORIES.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None

def parse_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return dparser.parse(str(value), fuzzy=True, dayfirst=True).date()
    except (ValueError, OverflowError):
        return None

def extract_deadline(text: str | None) -> date | None:
    if not text:
        return None
    m = DEADLINE_RE.search(text)
    return parse_date(m.group(1)) if m else None

def extract_section(text: str | None, headings: list[str]) -> str | None:
    """Pull a section like 'Qualifications:' out of the original text, if present."""
    if not text:
        return None
    pat = re.compile(r"(?:^|\n)\s*(?:%s)\s*:?\s*\n?(.+?)(?=\n\s*[A-Z][A-Za-z /&]{2,40}:?\s*\n|\Z)" % "|".join(headings), re.I | re.S)
    m = pat.search(text)
    return m.group(1).strip()[:4000] if m else None

def enrich(raw: dict, source_country: str | None) -> dict:
    """raw keys: title, employer, location, description, qualifications, how_to_apply, apply_url,
    published_at, deadline, source_url, image_url, category, country (all optional except source_url)."""
    desc = clean_text(raw.get("description"))
    job = {
        "title": (clean_text(raw.get("title")) or "").strip()[:500],
        "employer": (clean_text(raw.get("employer")) or None),
        "location": clean_text(raw.get("location")),
        "description": desc,
        "qualifications": clean_text(raw.get("qualifications")) or extract_section(desc, ["qualifications", "requirements", "minimum requirements"]),
        "how_to_apply": clean_text(raw.get("how_to_apply")) or extract_section(desc, ["how to apply", "application instructions", "mode of application"]),
        "apply_url": raw.get("apply_url") or None,
        "image_url": raw.get("image_url") or None,
        "source_url": raw["source_url"],
        "published_at": raw.get("published_at"),
        "deadline": parse_date(raw.get("deadline")) or extract_deadline(desc),
    }
    job["country"] = raw.get("country") or detect_country(job["location"], job["title"], desc, default=source_country)
    job["category"] = raw.get("category") or detect_category(job["title"], desc)
    job["fingerprint"] = fingerprint(job["title"], job["employer"], job["country"])
    return job

def validate(job: dict, cfg: dict, source_reliability: int, today: date | None = None) -> tuple[str, list[str]]:
    """Returns (status, reasons). status in validated | rejected | expired."""
    today = today or datetime.now(timezone.utc).date()
    reasons = []
    for f in cfg["required_fields"]:
        if not job.get(f):
            reasons.append(f"missing:{f}")
    if cfg.get("require_apply_method") and not (job.get("apply_url") or job.get("how_to_apply")):
        reasons.append("missing:application_method")
    if job.get("country") not in cfg["allowed_countries"]:
        reasons.append(f"country_not_allowed:{job.get('country') or 'unknown'}")
    if source_reliability < cfg["min_source_reliability"]:
        reasons.append(f"low_source_reliability:{source_reliability}")
    for f in ("apply_url", "source_url"):
        v = job.get(f)
        if v and not re.match(r"^https?://", v):
            reasons.append(f"invalid_url:{f}")
    if job.get("deadline") and job["deadline"] < today:
        return "expired", reasons + ["deadline_passed"]
    pub = job.get("published_at")
    if not job.get("deadline") and pub and pub.date() < today - timedelta(days=cfg["max_job_age_days"]):
        return "expired", reasons + ["too_old_no_deadline"]
    return ("rejected", reasons) if reasons else ("validated", [])
