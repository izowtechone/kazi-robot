"""WordPress REST API client. Credentials only come from server env vars."""
import html
import requests
from .config import settings

class WPError(Exception):
    def __init__(self, msg, temporary=False):
        super().__init__(msg)
        self.temporary = temporary

class WordPress:
    def __init__(self):
        if not (settings.wp_url and settings.wp_username and settings.wp_app_password):
            raise WPError("WordPress is not configured (WP_URL, WP_USERNAME, WP_APP_PASSWORD)")
        self.base = settings.wp_url.rstrip("/") + "/wp-json/wp/v2"
        self.s = requests.Session()
        self.s.auth = (settings.wp_username, settings.wp_app_password.replace(" ", ""))
        self.s.headers["User-Agent"] = settings.user_agent

    def _req(self, method, path, **kw):
        try:
            r = self.s.request(method, self.base + path, timeout=45, **kw)
        except requests.RequestException as e:
            raise WPError(f"network error: {e}", temporary=True)
        if r.status_code == 429 or r.status_code >= 500:
            raise WPError(f"WordPress HTTP {r.status_code}: {r.text[:300]}", temporary=True)
        if r.status_code >= 400:
            raise WPError(f"WordPress HTTP {r.status_code}: {r.text[:500]}")
        return r.json()

    def test(self) -> dict:
        me = self._req("GET", "/users/me", params={"context": "edit"})
        return {"ok": True, "user": me.get("name"), "roles": me.get("roles", []), "site": settings.wp_url}

    def _term(self, kind: str, name: str) -> int:
        found = self._req("GET", f"/{kind}", params={"search": name, "per_page": 100})
        for t in found:
            if html.unescape(t["name"]).lower() == name.lower():
                return t["id"]
        try:
            return self._req("POST", f"/{kind}", json={"name": name})["id"]
        except WPError as e:
            if "term_exists" in str(e):
                import json, re
                m = re.search(r'"term_id":(\d+)', str(e))
                if m:
                    return int(m.group(1))
            raise

    def find_existing(self, source_url: str) -> dict | None:
        """Duplicate guard on the WP side: we embed a marker comment with the source URL."""
        res = self._req("GET", "/posts", params={"search": source_url, "status": "any", "per_page": 5, "context": "edit"})
        for p in res:
            if f"kazi-source:{source_url}" in (p.get("content", {}).get("raw") or ""):
                return p
        return None

    def upload_image(self, url: str) -> int | None:
        try:
            r = requests.get(url, timeout=30, headers={"User-Agent": settings.user_agent})
            r.raise_for_status()
        except requests.RequestException:
            return None
        name = url.rstrip("/").split("/")[-1].split("?")[0] or "image.jpg"
        media = self._req("POST", "/media", data=r.content, headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Content-Type": r.headers.get("Content-Type", "image/jpeg")})
        return media.get("id")

    def publish(self, job, opts: dict, allow_image: bool) -> dict:
        existing = self.find_existing(job.source_url)
        if existing:
            return {"id": existing["id"], "link": existing.get("link"), "duplicate": True}
        cats = list(opts.get("wp_default_categories") or [])
        if opts.get("use_job_category_as_wp_category") and job.category:
            cats.append(job.category)
        tags = list(opts.get("wp_extra_tags") or [])
        if opts.get("use_country_as_tag") and job.country:
            tags.append(job.country)
        if job.location:
            tags.append(job.location[:60])
        body = {
            "title": job.title,
            "content": render_content(job),
            "status": opts.get("wp_post_status", "publish"),
            "categories": [self._term("categories", c) for c in dict.fromkeys(cats)],
            "tags": [self._term("tags", t) for t in dict.fromkeys(tags)],
            "excerpt": f"{job.employer or ''} – {job.location or job.country or ''}".strip(" –"),
        }
        if allow_image and job.image_url:
            mid = self.upload_image(job.image_url)
            if mid:
                body["featured_media"] = mid
        post = self._req("POST", "/posts", json=body)
        return {"id": post["id"], "link": post.get("link"), "duplicate": False}

def _p(label, value, pre=False):
    if not value:
        return ""
    v = html.escape(str(value))
    if pre:
        v = v.replace("\n", "<br>")
    return f"<p><strong>{label}:</strong> {v}</p>" if not pre else f"<h3>{label}</h3><p>{v}</p>"

def render_content(job) -> str:
    parts = [
        _p("Employer", job.employer), _p("Country", job.country), _p("Location", job.location),
        _p("Category", job.category),
        _p("Date posted", job.published_at.date().isoformat() if job.published_at else None),
        _p("Application deadline", job.deadline.isoformat() if job.deadline else None),
        _p("Job description", job.description, True),
        _p("Qualifications", job.qualifications, True),
        _p("How to apply", job.how_to_apply, True),
    ]
    if job.apply_url:
        u = html.escape(job.apply_url, quote=True)
        parts.append(f'<p><a href="{u}" rel="nofollow noopener" target="_blank"><strong>Apply here</strong></a></p>')
    s = html.escape(job.source_url, quote=True)
    parts.append(f'<p><em>Source: <a href="{s}" rel="nofollow noopener" target="_blank">original advertisement</a></em></p>')
    parts.append(f"<!-- kazi-source:{job.source_url} -->")
    return "\n".join(p for p in parts if p)
