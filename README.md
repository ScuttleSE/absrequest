# ABS Request Manager

A web application for managing audiobook library requests for
[Audiobookshelf](https://www.audiobookshelf.org/).

Users search for audiobooks (via Google Books and Open Library), submit requests,
and track their status.  Managers review requests, update statuses, and can run
an automatic sync that checks the ABS library and fulfils matching requests.

---

## Quick Start

### SQLite (default)

```bash
cp .env.example .env
# Edit .env — set SECRET_KEY at minimum
docker compose up
```

### PostgreSQL

```bash
cp .env.example .env
# Edit .env:
#   Set DATABASE_URL to the postgresql:// line
#   Fill in POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
docker compose --profile postgres up
```

The app is available at <http://localhost:8000>.

**The first registered user automatically becomes a manager.**

---

## Configuration

All settings are read from environment variables (loaded from `.env` via
`python-dotenv`).  See `.env.example` for the full annotated list.

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | *(required)* | Flask session signing key — generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | SQLite `/app/data/...` | SQLAlchemy database URL |
| `ALLOW_REGISTRATION` | `true` | Allow self-registration at `/auth/register` |
| `OAUTH2_ENABLED` | `false` | Enable SSO/OIDC login |
| `OAUTH2_PROVIDER_NAME` | `SSO` | Label shown on the SSO login button |
| `OAUTH2_CLIENT_ID` | — | OIDC client ID |
| `OAUTH2_CLIENT_SECRET` | — | OIDC client secret |
| `OAUTH2_AUTHORIZATION_URL` | — | OIDC authorization endpoint |
| `OAUTH2_TOKEN_URL` | — | OIDC token endpoint |
| `OAUTH2_USERINFO_URL` | — | OIDC userinfo endpoint |
| `OAUTH2_SCOPE` | `openid email profile` | OIDC scopes to request |
| `OAUTH2_ICON` | `bi-box-arrow-in-right` | Bootstrap Icons class for the SSO button |
| `AUDIOBOOKSHELF_URL` | — | Base URL of your ABS server, e.g. `http://abs:13378` |
| `AUDIOBOOKSHELF_API_TOKEN` | — | ABS API token (Settings → Users → your user → API Token) |
| `ABS_MATCH_THRESHOLD` | `0.85` | Fuzzy-match threshold (0.0 – 1.0) for title/author matching |
| `ABS_SYNC_INTERVAL_HOURS` | `6` | How often the scheduler syncs with ABS |
| `POSTGRES_USER` | — | PostgreSQL user (only with `--profile postgres`) |
| `POSTGRES_PASSWORD` | — | PostgreSQL password |
| `POSTGRES_DB` | — | PostgreSQL database name |

---

## First-Time Setup

1. Copy and edit `.env`:
   ```bash
   cp .env.example .env
   # Set SECRET_KEY to a long random string
   # Configure AUDIOBOOKSHELF_URL and AUDIOBOOKSHELF_API_TOKEN if available
   ```

2. Start the app:
   ```bash
   docker compose up
   ```

3. Open <http://localhost:8000> and register the first account — it will
   automatically be assigned the **manager** role.

4. Subsequent users who register get the **user** role.  Managers can promote
   users to manager via the **Manager → Users** page.

---

## OAuth2 / OIDC Setup

The app supports a single generic OIDC provider (tested with Authentik and
standard-compliant providers).

Set the following variables in `.env`:

```bash
OAUTH2_ENABLED=true
OAUTH2_PROVIDER_NAME=Authentik          # label on the login button
OAUTH2_ICON=bi-shield-lock              # optional Bootstrap Icons class
OAUTH2_CLIENT_ID=<your-client-id>
OAUTH2_CLIENT_SECRET=<your-client-secret>
OAUTH2_AUTHORIZATION_URL=https://your-provider/application/o/authorize/
OAUTH2_TOKEN_URL=https://your-provider/application/o/token/
OAUTH2_USERINFO_URL=https://your-provider/application/o/userinfo/
```

**Redirect URI** to register with your provider:

```
http://your-app-host/auth/callback/oidc
```

When SSO is enabled, users can log in via SSO or (if `ALLOW_REGISTRATION=true`)
register a local account.  Accounts are linked by email — if a user already has
a local account with the same email, SSO login will link to that existing account
on the first SSO login.

### Authentik example

1. Create a new **OAuth2/OpenID Connect Provider** in Authentik.
2. Set the redirect URI to `http://your-app/auth/callback/oidc`.
3. Note the Client ID and Client Secret.
4. Set the authorization/token/userinfo URLs from the provider's `.well-known`
   endpoint (Authentik shows these in the provider detail view).

---

## Audiobookshelf Setup

1. In ABS, go to **Settings → Users** and open your admin user.
2. Copy the **API Token** shown at the bottom of the user page.
3. Set `AUDIOBOOKSHELF_URL` to your ABS server base URL (no trailing slash).
4. Set `AUDIOBOOKSHELF_API_TOKEN` to the token copied above.

The **ABS status pill** in the top navbar shows a green ✓ when the app can
reach your ABS server, or a red ✗ when it cannot.

### Sync

The sync engine checks all open requests (status `pending`, `in_progress`,
`possible_match`) against the ABS library using fuzzy title and author matching:

- **Certain match** (both title and author ≥ threshold): request is marked
  **Fulfilled** automatically.
- **Possible match** (only title ≥ threshold): request is marked
  **Possible Match** for a manager to review.

Sync runs automatically every `ABS_SYNC_INTERVAL_HOURS` hours (default: 6).
Managers can also trigger a sync manually from **Manager → Dashboard**.

---

## Local Development

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Set DATABASE_URL=sqlite:///dev.db
# Set SECRET_KEY=any-dev-string

flask db init        # first time only — creates the migrations/ folder
flask db migrate -m "initial schema"
flask db upgrade

python run.py
```

The development server is available at <http://localhost:5000>.

### Useful commands

```bash
# Apply any new migrations after pulling changes
flask db upgrade

# Generate a migration after changing models.py
flask db migrate -m "describe your change"

# Open a Python shell with the app context
flask shell
```

---

## Project Structure

```
absrequest/
├── app/
│   ├── __init__.py          # App factory, extension init, scheduler start
│   ├── models.py            # SQLAlchemy models (User, AudiobookRequest, SyncLog)
│   ├── auth.py              # Authentication blueprint (/auth/*)
│   ├── main.py              # User-facing routes (search, request, dashboard)
│   ├── manager.py           # Manager routes (/manager/*)
│   ├── library.py           # Library browser and API endpoints (/library, /api/*)
│   ├── scheduler.py         # Flask-APScheduler initialisation
│   ├── services/
│   │   ├── audiobookshelf.py    # ABS API client
│   │   ├── book_search.py       # Google Books + Open Library search
│   │   ├── library_matcher.py   # Fuzzy title/author matching (rapidfuzz)
│   │   ├── oauth_provider.py    # Authlib OIDC provider registration
│   │   └── sync.py              # Sync engine (run_abs_sync, trigger_manual_sync)
│   ├── templates/
│   │   ├── base.html
│   │   ├── auth/            # login, register, forgot_password
│   │   ├── main/            # index, search, request_form, request_detail, dashboard
│   │   ├── manager/         # dashboard, requests, request_edit, users, stats,
│   │   │                    #   sync_logs, sync_log_detail
│   │   └── library/         # index
│   └── static/
│       ├── css/custom.css
│       └── js/library_check.js
├── config.py                # Config class (env-var driven)
├── run.py                   # WSGI entry point
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh            # Runs flask db upgrade then gunicorn
├── .env.example
└── requirements.txt
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, Flask 3.x |
| Database | SQLAlchemy + Flask-Migrate (SQLite / PostgreSQL) |
| Auth | Flask-Login, Flask-WTF, Flask-Bcrypt, Authlib (OIDC) |
| Scheduler | Flask-APScheduler (APScheduler 3.x, interval jobs) |
| Caching | Flask-Caching (SimpleCache) |
| Fuzzy matching | rapidfuzz |
| Frontend | Bootstrap 5, Bootstrap Icons |
| Container | Docker, Gunicorn (1 worker + 4 threads) |
