# Kazi Robot – Self-hosted Job Automation

Collects job adverts from Tanzania, Kenya, Uganda, Rwanda and Burundi (RSS feeds, official APIs,
permitted websites), validates them, and publishes qualifying jobs to your WordPress site.
Everything runs on your own server with Docker Compose. No Lovable or Supabase services are needed.

| Service  | Role |
|----------|------|
| `nginx`    | Reverse proxy on port 80 (rate limiting, security headers) |
| `frontend` | React + TypeScript admin dashboard |
| `backend`  | FastAPI REST API (`/api`, docs at `/api/docs`) – runs migrations on start |
| `worker`   | Celery worker: collecting, processing, publishing |
| `beat`     | Celery scheduler: runs a "tick" every minute |
| `db`       | PostgreSQL 16 (persistent volume `pgdata`) |
| `redis`    | Queue broker (persistent AOF volume `redisdata`) |

---

## 1. Install on a clean Debian 13 VPS

```bash
# As root (or with sudo)
apt update && apt upgrade -y
apt install -y ca-certificates curl git unzip

# Install Docker Engine + Compose plugin (official repo)
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
docker --version && docker compose version
```

> If Docker's repo does not yet publish packages for Debian 13 ("trixie"), replace
> `$(. /etc/os-release && echo "$VERSION_CODENAME")` with `bookworm`, or run `apt install -y docker.io docker-compose`.

Firewall (optional but recommended):
```bash
apt install -y ufw && ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw enable
```

## 2. Get the code

```bash
mkdir -p /opt && cd /opt
git clone https://github.com/<you>/kazi-robot.git      # or: unzip kazi-robot.zip
cd kazi-robot
```

## 3. Configure environment variables

```bash
cp .env.example .env
openssl rand -hex 32          # paste into SECRET_KEY
openssl rand -hex 16          # use as POSTGRES_PASSWORD (also update it inside DATABASE_URL)
nano .env
chmod 600 .env
```

Set at minimum: `POSTGRES_PASSWORD`, `DATABASE_URL`, `SECRET_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`,
`CORS_ORIGINS` (e.g. `https://robot.yourdomain.com`), and the WordPress values:

* `WP_URL` – e.g. `https://jobs.yoursite.co.tz`
* `WP_USERNAME` – a WordPress user with *Author* or *Editor* role
* `WP_APP_PASSWORD` – WordPress Admin → Users → Profile → **Application Passwords** → Add New

WordPress credentials live only in `.env` on the server; the dashboard only shows the site URL and a masked username.

## 4. Start everything

```bash
docker compose up -d --build
docker compose ps                     # all services should become "healthy"/"running"
curl http://localhost/api/health      # {"api":"ok","database":"ok","redis":"ok"}
```

Open `http://YOUR_SERVER_IP/` and sign in with `ADMIN_EMAIL` / `ADMIN_PASSWORD`.
Change the admin password afterwards in **Admin Users**.

### HTTPS (recommended)
Put Caddy or Certbot in front, or quickly:
```bash
apt install -y certbot
docker compose stop nginx
certbot certonly --standalone -d robot.yourdomain.com
```
then add a `listen 443 ssl` server block to `nginx/nginx.conf` pointing to
`/etc/letsencrypt/live/robot.yourdomain.com/` and mount `/etc/letsencrypt` into the nginx container.

## 5. Acceptance test walkthrough

1. **Sample RSS feed** – *Job Sources* → "Sample Test Feed" → **Test** (preview, nothing saved) → **Collect now**.
   You should get 4 fetched: 1 validated, 1 duplicate, 1 expired (Nairobi nurse), 1 rejected (missing employer).
2. **Duplicate detection** – click **Collect now** again: `new: 0, duplicates: 4`.
3. **WordPress connection** – *WordPress Settings* → **Test connection** → shows your WP user name and roles.
4. **Publish a test job** – tip: set *Post status* to `draft` first. *All Jobs* → open "[TEST] Software Developer" → **Publish now**.
   The job turns `published` and shows the WordPress link. Clicking again does nothing (duplicate publishing is blocked).
5. **Automation** – enable the sample source (or your real ones). Every minute the scheduler checks which sources are due.
6. **Restart survival** – `sudo reboot`. All containers have `restart: unless-stopped`; scheduling state lives in PostgreSQL,
   so collection and publishing continue where they left off.
7. Disable or delete the Sample Test Feed and remove `[TEST]` posts from WordPress when finished.

Run the automated test suite:
```bash
docker compose exec -e DATABASE_URL=sqlite:////tmp/test.db backend pytest -q
```

## 6. Adding sources

Only add sources you are allowed to collect from (public RSS, official/partner APIs, sites whose terms and
`robots.txt` allow it). The robot checks `robots.txt`, stops on HTTP 401/403, and stops on CAPTCHA/anti-bot pages.
It never logs in or bypasses protections.

**RSS** – just the feed URL. Optional `config`:
```json
{"employer_field": "job_employer", "location_field": "job_location", "deadline_field": "job_deadline",
 "apply_field": "job_apply_url", "allow_featured_image": false}
```
(Namespaced RSS tags like `<job:employer>` become `job_employer`.)

**JSON API**
```json
{"items_path": "data.jobs",
 "headers": {"Authorization": "env:MY_PARTNER_API_KEY"},
 "fields": {"title": "title", "employer": "company.name", "location": "city", "description": "body",
            "apply_url": "apply_link", "deadline": "closing_date", "published_at": "created", "source_url": "url"}}
```
`env:NAME` reads the key from `.env` so API keys are never stored in the database.

**Website (permitted)**
```json
{"item_selector": ".job-listing", "link_selector": "a", "title_selector": "h3", "employer_selector": ".company",
 "location_selector": ".location", "deadline_selector": ".deadline", "fetch_detail": true,
 "detail_selector": ".job-description", "delay_seconds": 3, "max_items": 30}
```

`allow_featured_image: true` – only set when the source licence allows reuse of its images.

## 7. How processing works

* **Extraction** – title, employer, country, location, category, description, qualifications, how to apply, apply URL,
  publication date, deadline, source URL. Missing values stay empty – nothing is invented.
* **Country detection** – from location/title/text (city lists), falling back to the source's default country.
* **Categorisation** – keyword rules (IT, Health, Education, Finance, NGO, …).
* **Duplicate detection** – same source URL, or same normalised title + employer + country.
* **Validation** – required fields, application method, allowed countries, URL format, minimum source reliability
  (all configurable in *Automation Settings*). Failures are stored as `rejected` with reasons and logged.
* **Expiry** – deadline passed, or no deadline and older than *max job age*. Re-checked every minute.
* **Source reliability** – after 3 consecutive failures the source's reliability drops by 5 each failure.
* **Publishing** – atomic claim in the DB + `wp_post_id` + hidden marker searched in WordPress → never double-posts.
  Temporary errors (network, 429, 5xx) are retried; attempts are capped.

## 8. Daily operations

```bash
cd /opt/kazi-robot
docker compose logs -f                     # all logs
docker compose logs -f worker beat         # automation logs
docker compose restart worker beat         # restart automation
docker compose restart                     # restart everything
docker compose down && docker compose up -d
```

### Update the application
```bash
cd /opt/kazi-robot
./scripts/backup.sh
git pull                                    # or unzip the new version over the folder (keep .env)
docker compose up -d --build                # migrations run automatically
docker image prune -f
```

### Backup & restore
```bash
./scripts/backup.sh                                     # -> backups/kazirobot_YYYYmmdd_HHMMSS.sql.gz
./scripts/restore.sh backups/kazirobot_20261030_020000.sql.gz
```
Nightly backup via cron (`crontab -e`):
```
0 2 * * * cd /opt/kazi-robot && ./scripts/backup.sh >> /var/log/kazi-backup.log 2>&1
```
Copy the `backups/` folder off-server regularly (e.g. `rsync` to another machine).

## 9. Security notes

* Passwords hashed with bcrypt; JWT access tokens (HS256, `SECRET_KEY`).
* Roles: `viewer` (read), `editor` (sources, test, publish), `admin` (settings, users, deletes).
* Rate limits: login 10/min per IP, API 300/min per IP, plus nginx 20 req/s.
* All input validated with Pydantic; all DB access via SQLAlchemy parameterised queries.
* WordPress and API credentials only in `.env`; never sent to the browser.
* Containers run the app as a non-root user; Postgres and Redis are not exposed publicly.

## 10. Local development

```bash
docker compose up -d db redis
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg://kazirobot:PASS@localhost:5432/kazirobot   # expose db port 5432 first
alembic upgrade head && python -m app.bootstrap && uvicorn app.main:app --reload
cd ../frontend && npm install && npm run dev        # proxies /api to :8000
```
