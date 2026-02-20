# ABS Request Manager

A web application for managing audiobook requests for
[Audiobookshelf](https://www.audiobookshelf.org/).

Users search for audiobooks via Audible (and optionally Open Library), submit
requests, and track their status. Managers review requests, update statuses, and
can trigger an automatic sync that checks the ABS library and fulfils matching
requests.

---

## Quick Start

```bash
cp .env.example .env
# Edit .env — set SECRET_KEY at minimum
docker compose up
```

The app is available at <http://localhost:5001>.

**The first registered user automatically becomes a manager.**

---

## Configuration

All settings are read from environment variables (via `.env`). See `.env.example`
for the full annotated list.

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | *(required)* | Flask session signing key — generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | `sqlite:////app/data/audiobook_requests.db` | SQLAlchemy database URL |
| `ALLOW_REGISTRATION` | `true` | Allow self-registration at `/auth/register` |
| `AUDIBLE_REGION` | `us` | Default Audible region for searches |
| `AUDIOBOOKSHELF_URL` | — | Base URL of your ABS server, e.g. `http://abs:13378` |
| `AUDIOBOOKSHELF_API_TOKEN` | — | ABS API token (ABS → Settings → Users → your user → API Token) |
| `ABS_MATCH_THRESHOLD` | `0.85` | Fuzzy-match threshold (0.0–1.0) for title/author matching |
| `ABS_SYNC_INTERVAL_HOURS` | `6` | How often the background scheduler syncs with ABS |
| `OAUTH2_ENABLED` | `false` | Enable SSO/OIDC login |
| `OAUTH2_PROVIDER_NAME` | `SSO` | Label shown on the SSO login button |
| `OAUTH2_CLIENT_ID` | — | OIDC client ID |
| `OAUTH2_CLIENT_SECRET` | — | OIDC client secret |
| `OAUTH2_SERVER_METADATA_URL` | — | OIDC discovery document URL *(recommended — see below)* |
| `OAUTH2_AUTHORIZATION_URL` | — | OIDC authorization endpoint *(manual fallback)* |
| `OAUTH2_TOKEN_URL` | — | OIDC token endpoint *(manual fallback)* |
| `OAUTH2_USERINFO_URL` | — | OIDC userinfo endpoint *(manual fallback)* |
| `OAUTH2_JWKS_URI` | — | JWKS endpoint *(manual fallback)* |
| `OAUTH2_SCOPE` | `openid email profile` | OIDC scopes to request |
| `OAUTH2_ICON` | `bi-box-arrow-in-right` | Bootstrap Icons class for the SSO button |

---

## First-Time Setup

1. Copy and edit `.env`:
   ```bash
   cp .env.example .env
   # Required: set SECRET_KEY to a long random string
   # Optional: set AUDIOBOOKSHELF_URL and AUDIOBOOKSHELF_API_TOKEN
   ```

2. Start the app:
   ```bash
   docker compose up
   ```

3. Open <http://localhost:5001>. You will be taken to the login page.

4. Register the first account — it is automatically assigned the **manager** role.

5. Subsequent users who register receive the **user** role. Managers can promote
   users via **Manager → Users**.

---

## OAuth2 / OIDC Login

The app supports a single generic OIDC provider.

When SSO is configured, the default login page shows only the SSO button.
The local email/password form is available at `/auth/login?local=1` — useful
for emergency admin access.

### Setup

Set the following in `.env`:

```bash
OAUTH2_ENABLED=true
OAUTH2_PROVIDER_NAME=Authentik        # label on the login button
OAUTH2_ICON=bi-shield-lock            # optional Bootstrap Icons class
OAUTH2_CLIENT_ID=<your-client-id>
OAUTH2_CLIENT_SECRET=<your-client-secret>

# Recommended: discovery document URL — the app finds all endpoints automatically
OAUTH2_SERVER_METADATA_URL=https://your-provider/.well-known/openid-configuration
```

**Redirect URI** to register with your provider:

```
https://<your-domain>/auth/callback/oidc
```

### Provider examples

| Provider | `OAUTH2_SERVER_METADATA_URL` |
|---|---|
| Authentik | `https://auth.example.com/application/o/<slug>/.well-known/openid-configuration` |
| Keycloak | `https://auth.example.com/realms/<realm>/.well-known/openid-configuration` |
| Auth0 | `https://<tenant>.auth0.com/.well-known/openid-configuration` |

When a user logs in via SSO for the first time and their email matches an existing
local account, the accounts are linked automatically.

### Manual endpoint configuration (fallback)

If your provider does not expose a discovery document, set the individual URLs
instead of `OAUTH2_SERVER_METADATA_URL`:

```bash
OAUTH2_AUTHORIZATION_URL=https://your-provider/authorize
OAUTH2_TOKEN_URL=https://your-provider/token
OAUTH2_USERINFO_URL=https://your-provider/userinfo
OAUTH2_JWKS_URI=https://your-provider/jwks        # required for ID token validation
```

---

## Audiobookshelf Integration

1. In ABS, open **Settings → Users** and select your admin user.
2. Copy the **API Token** shown at the bottom of the page.
3. Set `AUDIOBOOKSHELF_URL` and `AUDIOBOOKSHELF_API_TOKEN` in `.env`.

When connected, the home page displays a wallpaper of random book covers from
your library. The **ABS** pill in the navbar shows green ✓ when reachable,
red ✗ when not.

### Sync

The sync engine checks all open requests (`pending`, `in_progress`,
`possible_match`) against the ABS library using fuzzy title and author matching:

- **Certain match** (title and author both ≥ threshold): request is marked
  **Fulfilled** automatically.
- **Possible match** (title ≥ threshold only): request is marked
  **Possible Match** for a manager to review.

Sync runs automatically every `ABS_SYNC_INTERVAL_HOURS` hours (default: 6).
Managers can also trigger it manually from **Manager → Dashboard**.

---

## Search Providers

Search uses **Audible** by default. Managers can configure providers and regions
from **Manager → Settings**:

- **Audible** — searches one or more regional Audible catalogues (US, UK, AU, CA,
  DE, FR, IT, ES, JP, IN). Multiple regions are searched in parallel and
  deduplicated by ASIN.
- **Open Library** — fallback for books not on Audible. Disabled by default.

---

## Manager Features

Managers have access to a dedicated section under the **Manager** navbar menu:

| Page | Description |
|---|---|
| Dashboard | Overview of all request statuses, recent activity, sync status |
| Requests | Full list of all user requests; edit status and add notes |
| Users | List all users; promote/demote manager role |
| Stats | Charts and counts: requests by status, top requesters, monthly volume |
| Sync Logs | History of every sync run with matched request details |
| Settings | Toggle search providers and Audible regions |

---

## Project Structure

```
absrequest/
├── app/
│   ├── __init__.py          # App factory, extension init, scheduler start
│   ├── models.py            # SQLAlchemy models (User, AudiobookRequest, SyncLog, AppSettings)
│   ├── auth.py              # Authentication blueprint (/auth/*)
│   ├── main.py              # User-facing routes (search, request, dashboard)
│   ├── manager.py           # Manager routes (/manager/*)
│   ├── library.py           # Library browser and API endpoints (/library, /api/*)
│   ├── scheduler.py         # Flask-APScheduler initialisation
│   ├── services/
│   │   ├── audiobookshelf.py    # ABS API client
│   │   ├── book_search.py       # Audible + Open Library search
│   │   ├── library_matcher.py   # Fuzzy title/author matching (rapidfuzz)
│   │   ├── oauth_provider.py    # Authlib OIDC provider registration
│   │   └── sync.py              # Sync engine (run_abs_sync, trigger_manual_sync)
│   ├── templates/
│   │   ├── base.html
│   │   ├── auth/            # login, register, forgot_password
│   │   ├── main/            # index, search, request_form, request_detail, dashboard
│   │   ├── manager/         # dashboard, requests, request_edit, users, stats,
│   │   │                    #   sync_logs, sync_log_detail, settings
│   │   └── library/         # index
│   └── static/
│       └── css/custom.css
├── config.py                # Config class (env-var driven)
├── run.py                   # WSGI entry point
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh            # Creates DB tables with db.create_all(), then starts Gunicorn
├── .env.example
└── requirements.txt
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, Flask 3.x |
| Database | SQLAlchemy (SQLite) |
| Auth | Flask-Login, Flask-WTF, Flask-Bcrypt, Authlib (OIDC) |
| Scheduler | Flask-APScheduler (interval jobs) |
| Caching | Flask-Caching (SimpleCache) |
| Fuzzy matching | rapidfuzz |
| Frontend | Bootstrap 5, Bootstrap Icons |
| Container | Docker, Gunicorn (1 worker, 4 threads) |

---

## Local Development

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Set DATABASE_URL=sqlite:///dev.db
# Set SECRET_KEY=any-dev-string

python run.py
```

Database tables are created automatically on first run. The development server
is available at <http://localhost:5000>.
