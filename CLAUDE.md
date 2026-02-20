# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**absrequest** is a request app for [Audiobookshelf](https://www.audiobookshelf.org/).

**Stack:** Python 3.12, Flask 3, SQLAlchemy/Flask-Migrate (SQLite dev / PostgreSQL prod),
Flask-Login, Flask-WTF, Flask-Bcrypt, Authlib (OIDC), Gunicorn, Bootstrap 5.

## Structure

```
app/
  __init__.py          # create_app() factory; extension init; blueprint registration
  models.py            # User, AudiobookRequest, SyncLog
  auth.py              # /auth blueprint — local login/register + OIDC OAuth2
  main.py              # / and /dashboard routes
  manager.py           # /manager blueprint (stub)
  library.py           # /library blueprint (stub)
  scheduler.py         # APScheduler jobs (stub)
  services/
    oauth_provider.py  # register_oauth_provider() for Authlib
    audiobookshelf.py  # ABS API client (stub)
    book_search.py     # book search stub
    library_matcher.py # fuzzy-match stub
    sync.py            # sync logic stub
  templates/           # Jinja2 + Bootstrap 5
  static/css/custom.css
  static/js/library_check.js
config.py              # Config class — all settings from env vars via python-dotenv
run.py                 # WSGI entry point: app = create_app()
entrypoint.sh          # Docker: flask db upgrade && gunicorn
Dockerfile             # python:3.12-slim, non-root appuser, port 8000
docker-compose.yml     # default=SQLite; --profile postgres=PostgreSQL
.env.example           # all env vars with comments
requirements.txt
README.md
```

## Key conventions

- **App factory pattern** — `create_app()` in `app/__init__.py`. All blueprints and
  extensions are imported *inside* `create_app()` to avoid circular imports.
- **Extensions** (`db`, `bcrypt`, `oauth`, etc.) are module-level singletons in
  `app/__init__.py` so blueprints/models can import them with `from app import db`.
- **Config** is a single `Config` class in `config.py`; all values read from env vars.
  `OAUTH2_CONFIGURED` is a computed bool (True only if enabled AND client_id set).
- **Jinja2 globals** — `OAUTH2_CONFIGURED`, `OAUTH2_BUTTON`, and `ALLOW_REGISTRATION`
  are injected into every template via `app.jinja_env.globals` (not passed per-view).
- **First registered user** (local or OAuth) automatically gets `role='manager'`.
- **Docker profiles** — `docker compose up` uses SQLite; `--profile postgres` adds the
  `db` service and the `app` service waits for it via `depends_on.required: false`.

## Development setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set SECRET_KEY and DATABASE_URL=sqlite:///dev.db
flask db init && flask db migrate -m "initial" && flask db upgrade
python run.py
```

## What is NOT yet implemented (future steps)

- Audiobook search (Google Books, Open Library)
- Audiobookshelf API integration
- Library sync / fuzzy matching
- Manager request-management UI
- Password reset via email
- APScheduler jobs

Update this file as the project takes shape.
