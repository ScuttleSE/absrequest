from datetime import datetime

from flask_login import UserMixin

from app import bcrypt, db


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    avatar_url = db.Column(db.String(500), nullable=True)
    # Null for SSO-only accounts
    password_hash = db.Column(db.String(255), nullable=True)
    # Stored as 'oidc' when linked via SSO
    oauth_provider = db.Column(db.String(50), nullable=True)
    oauth_provider_id = db.Column(db.String(255), nullable=True)
    # Values: 'user', 'manager'
    role = db.Column(db.String(50), nullable=False, default='user')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    requests = db.relationship('AudiobookRequest', backref='user', lazy=True)

    # ── Password helpers ───────────────────────────────────────────────────────

    def set_password(self, password: str) -> None:
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        return bcrypt.check_password_hash(self.password_hash, password)

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def is_manager(self) -> bool:
        return self.role == 'manager'

    # Flask-Login requires: is_authenticated, is_active, is_anonymous, get_id
    # All provided by UserMixin.


class AudiobookRequest(db.Model):
    __tablename__ = 'audiobook_requests'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    title = db.Column(db.String(500), nullable=False)
    author = db.Column(db.String(500))
    narrator = db.Column(db.String(500), nullable=True)
    cover_url = db.Column(db.String(500), nullable=True)
    isbn = db.Column(db.String(50), nullable=True)
    asin = db.Column(db.String(50), nullable=True)
    google_books_id = db.Column(db.String(100), nullable=True)
    duration = db.Column(db.String(50), nullable=True)
    description = db.Column(db.Text, nullable=True)
    # e.g. 'google_books', 'open_library'
    source = db.Column(db.String(100), nullable=True)

    # Values: 'pending', 'in_progress', 'completed', 'fulfilled',
    #         'possible_match', 'rejected'
    status = db.Column(db.String(50), nullable=False, default='pending')

    user_note = db.Column(db.Text, nullable=True)
    manager_note = db.Column(db.Text, nullable=True)
    fulfilled_by_sync = db.Column(db.Boolean, default=False)

    # ABS match info populated by the sync service
    abs_match_title = db.Column(db.String(500), nullable=True)
    abs_match_author = db.Column(db.String(500), nullable=True)
    last_sync_checked_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class AppSettings(db.Model):
    """Singleton settings row (always id=1). Use AppSettings.get() to access."""

    __tablename__ = 'app_settings'

    id = db.Column(db.Integer, primary_key=True)

    # Search providers
    audible_enabled = db.Column(db.Boolean, nullable=False, default=True)
    # Comma-separated region codes, e.g. "us,uk,de"
    audible_region = db.Column(db.String(100), nullable=False, default='us')
    # Language filter passed to the Audible API, e.g. "english". Empty = no filter.
    audible_language = db.Column(db.String(50), nullable=False, default='english')
    open_library_enabled = db.Column(db.Boolean, nullable=False, default=False)
    storytel_enabled = db.Column(db.Boolean, nullable=False, default=False)
    # Locale for Storytel API, e.g. "en", "sv", "de"
    storytel_locale = db.Column(db.String(10), nullable=False, default='en')

    @property
    def audible_regions(self) -> list[str]:
        """Return the selected Audible regions as a list."""
        return [r.strip() for r in (self.audible_region or 'us').split(',') if r.strip()]

    @classmethod
    def get(cls) -> 'AppSettings':
        """Return the singleton settings row, creating it with defaults if absent."""
        settings = db.session.get(cls, 1)
        if settings is None:
            settings = cls(id=1)
            db.session.add(settings)
            db.session.commit()
        return settings


class SyncLog(db.Model):
    __tablename__ = 'sync_logs'

    id = db.Column(db.Integer, primary_key=True)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)
    # Values: 'running', 'completed', 'failed'
    status = db.Column(db.String(50), nullable=False)
    total_requests_checked = db.Column(db.Integer, default=0)
    total_matches_found = db.Column(db.Integer, default=0)
    matched_request_ids = db.Column(db.JSON, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    # Values: 'scheduler', 'manual'
    triggered_by = db.Column(db.String(50), nullable=False)
    triggered_by_user_id = db.Column(
        db.Integer, db.ForeignKey('users.id'), nullable=True
    )
