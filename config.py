import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me-in-production')

    DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:////app/data/audiobook_requests.db')
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    ALLOW_REGISTRATION = os.environ.get('ALLOW_REGISTRATION', 'true').lower() in ('true', '1', 'yes')

    # ── OAuth2 — single generic OIDC provider ──────────────────────────────────
    OAUTH2_ENABLED = os.environ.get('OAUTH2_ENABLED', 'false').lower() in ('true', '1', 'yes')
    OAUTH2_PROVIDER_NAME = os.environ.get('OAUTH2_PROVIDER_NAME', 'SSO')
    OAUTH2_CLIENT_ID = os.environ.get('OAUTH2_CLIENT_ID', '')
    OAUTH2_CLIENT_SECRET = os.environ.get('OAUTH2_CLIENT_SECRET', '')
    OAUTH2_AUTHORIZATION_URL = os.environ.get('OAUTH2_AUTHORIZATION_URL', '')
    OAUTH2_TOKEN_URL = os.environ.get('OAUTH2_TOKEN_URL', '')
    OAUTH2_USERINFO_URL = os.environ.get('OAUTH2_USERINFO_URL', '')
    OAUTH2_SCOPE = os.environ.get('OAUTH2_SCOPE', 'openid email profile')
    OAUTH2_ICON = os.environ.get('OAUTH2_ICON', 'bi-box-arrow-in-right')

    # Computed: True only if OAUTH2_ENABLED is set and OAUTH2_CLIENT_ID is provided
    OAUTH2_CONFIGURED = OAUTH2_ENABLED and bool(OAUTH2_CLIENT_ID)

    OAUTH2_BUTTON = {
        'name': OAUTH2_PROVIDER_NAME,
        'icon': OAUTH2_ICON,
    }

    # ── Audiobookshelf ─────────────────────────────────────────────────────────
    AUDIOBOOKSHELF_URL = os.environ.get('AUDIOBOOKSHELF_URL', '')
    AUDIOBOOKSHELF_API_TOKEN = os.environ.get('AUDIOBOOKSHELF_API_TOKEN', '')
    ABS_MATCH_THRESHOLD = float(os.environ.get('ABS_MATCH_THRESHOLD', '0.85'))
    ABS_SYNC_INTERVAL_HOURS = int(os.environ.get('ABS_SYNC_INTERVAL_HOURS', '6'))

    # ── PostgreSQL ─────────────────────────────────────────────────────────────
    POSTGRES_USER = os.environ.get('POSTGRES_USER', '')
    POSTGRES_PASSWORD = os.environ.get('POSTGRES_PASSWORD', '')
    POSTGRES_DB = os.environ.get('POSTGRES_DB', '')

    # ── APScheduler ───────────────────────────────────────────────────────────
    SCHEDULER_API_ENABLED = False
    SCHEDULER_TIMEZONE = 'UTC'

    # ── Flask-Caching ─────────────────────────────────────────────────────────
    CACHE_TYPE = 'SimpleCache'
    CACHE_DEFAULT_TIMEOUT = 600
