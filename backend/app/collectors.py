"""Collectors for permitted sources only. Respects robots.txt; never bypasses logins/CAPTCHAs."""
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib import robotparser
import feedparser, requests
from bs4 import BeautifulSoup
from .config import settings

TIMEOUT = 30
BLOCK_MARKERS = ("captcha", "cf-challenge", "g-recaptcha", "hcaptcha", "verify you are human")

class CollectError(Exception):
    def __init__(self, msg, temporary=False):
        super().__init__(msg)
        self.temporary = temporary

def _session():
    s = requests.Session()
    s.headers["User-Agent"] = settings.user_agent
    return s

def robots_allowed(url: str) -> bool:
    p = urlparse(url)
    if p.hostname in ("backend", "localhost", "127.0.0.1"):
        return True
    rp = robotparser.RobotFileParser()
    try:
        r = _session().get(f"{p.scheme}://{p.netloc}/robots.txt", timeout=TIMEOUT)
        if r.status_code >= 400:
            return True
        rp.parse(r.text.splitlines())
    except requests.RequestException:
        return True
    return rp.can_fetch(settings.user_agent, url)

def _fetch(url: str, headers: dict | None = None) -> requests.Response:
    if not robots_allowed(url):
        raise CollectError("robots.txt disallows automated access to this URL")
    try:
        r = _session().get(url, headers=headers or {}, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise CollectError(f"network error: {e}", temporary=True)
    if r.status_code in (401, 403):
        raise CollectError(f"access denied (HTTP {r.status_code}); source requires login or blocks bots - not bypassing")
    if r.status_code == 429 or r.status_code >= 500:
        raise CollectError(f"HTTP {r.status_code}", temporary=True)
    if r.status_code >= 400:
        raise CollectError(f"HTTP {r.status_code}")
    low = r.text[:20000].lower()
    if any(m in low for m in BLOCK_MARKERS):
        raise CollectError("anti-bot / CAPTCHA page detected - not bypassing")
    return r

def _dt(struct):
    return datetime.fromtimestamp(time.mktime(struct), tz=timezone.utc) if struct else None

def collect_rss(source) -> list[dict]:
    r = _fetch(source.url)
    feed = feedparser.parse(r.content)
    if feed.bozo and not feed.entries:
        raise CollectError(f"invalid feed: {feed.bozo_exception}")
    cfg = source.config or {}
    out = []
    for e in feed.entries:
        link = e.get("link")
        if not link:
            continue
        content = (e.get("content") or [{}])[0].get("value") or e.get("summary")
        image = None
        if cfg.get("allow_featured_image"):
            media = e.get("media_content") or e.get("media_thumbnail") or []
            image = media[0].get("url") if media else None
        out.append({
            "title": e.get("title"),
            "employer": e.get(cfg.get("employer_field", "job_employer")) or e.get("author") or e.get("job_company"),
            "location": e.get(cfg.get("location_field", "job_location")),
            "description": content,
            "apply_url": e.get(cfg.get("apply_field", "job_apply_url")) or link,
            "deadline": e.get(cfg.get("deadline_field", "job_deadline")),
            "category": None,
            "published_at": _dt(e.get("published_parsed") or e.get("updated_parsed")),
            "source_url": link,
            "image_url": image,
        })
    return out

def _get_path(obj, path: str | None):
    if not path:
        return None
    for part in path.split("."):
        if isinstance(obj, dict):
            obj = obj.get(part)
        elif isinstance(obj, list) and part.isdigit():
            obj = obj[int(part)] if int(part) < len(obj) else None
        else:
            return None
    return obj

def collect_api(source) -> list[dict]:
    """config: {"items_path": "data.jobs", "headers": {...}, "fields": {"title": "title", "source_url": "url", ...}}
    API keys can reference env vars: header value "env:MY_API_KEY"."""
    import os
    cfg = source.config or {}
    headers = {k: (os.environ.get(v[4:], "") if isinstance(v, str) and v.startswith("env:") else v)
               for k, v in (cfg.get("headers") or {}).items()}
    r = _fetch(source.url, headers)
    try:
        data = r.json()
    except ValueError:
        raise CollectError("API did not return JSON")
    items = _get_path(data, cfg.get("items_path")) if cfg.get("items_path") else data
    if not isinstance(items, list):
        raise CollectError("items_path did not resolve to a list")
    fields = cfg.get("fields") or {}
    out = []
    for it in items:
        rec = {k: _get_path(it, fields.get(k, k)) for k in
               ("title", "employer", "location", "description", "qualifications", "how_to_apply",
                "apply_url", "deadline", "source_url", "country", "category")}
        pub = _get_path(it, fields.get("published_at", "published_at"))
        from .processing import parse_date
        d = parse_date(pub)
        rec["published_at"] = datetime(d.year, d.month, d.day, tzinfo=timezone.utc) if d else None
        if rec.get("source_url"):
            out.append(rec)
    return out

def collect_html(source) -> list[dict]:
    """config: {"item_selector": ".job", "link_selector": "a", "title_selector": "h2",
    "employer_selector": ".company", "location_selector": ".loc", "deadline_selector": ".deadline",
    "fetch_detail": true, "detail_selector": ".job-description", "max_items": 30}"""
    cfg = source.config or {}
    if not cfg.get("item_selector"):
        raise CollectError("html source needs config.item_selector")
    soup = BeautifulSoup(_fetch(source.url).text, "html.parser")
    def txt(node, sel):
        if not sel:
            return None
        n = node.select_one(sel)
        return n.get_text(" ", strip=True) if n else None
    out = []
    for node in soup.select(cfg["item_selector"])[: int(cfg.get("max_items", 30))]:
        a = node.select_one(cfg.get("link_selector", "a"))
        if not a or not a.get("href"):
            continue
        link = urljoin(source.url, a["href"])
        rec = {"title": txt(node, cfg.get("title_selector")) or a.get_text(" ", strip=True),
               "employer": txt(node, cfg.get("employer_selector")),
               "location": txt(node, cfg.get("location_selector")),
               "deadline": txt(node, cfg.get("deadline_selector")),
               "description": txt(node, cfg.get("summary_selector")),
               "source_url": link, "apply_url": None, "published_at": None}
        if cfg.get("fetch_detail") and cfg.get("detail_selector"):
            try:
                time.sleep(float(cfg.get("delay_seconds", 2)))
                d = BeautifulSoup(_fetch(link).text, "html.parser").select_one(cfg["detail_selector"])
                if d:
                    rec["description"] = str(d)
            except CollectError:
                pass
        out.append(rec)
    return out

COLLECTORS = {"rss": collect_rss, "api": collect_api, "html": collect_html}

def collect(source) -> list[dict]:
    fn = COLLECTORS.get(source.type)
    if not fn:
        raise CollectError(f"unknown source type {source.type}")
    return fn(source)
