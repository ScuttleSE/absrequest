from authlib.integrations.flask_client import OAuth
from flask import Flask
from flask_bcrypt import Bcrypt
from flask_caching import Cache
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

from config import Config

# Extensions are instantiated at module level so blueprints and models can
# import them directly (e.g. `from app import db`).  They are bound to the
# Flask app inside create_app() via init_app().
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
cache = Cache()
bcrypt = Bcrypt()
oauth = OAuth()


def create_app(config_class: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    # ── Bind extensions to the app ─────────────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)

    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    csrf.init_app(app)
    cache.init_app(app)
    bcrypt.init_app(app)
    oauth.init_app(app)

    # ── OAuth provider registration ────────────────────────────────────────────
    from app.services.oauth_provider import register_oauth_provider

    register_oauth_provider(oauth, app)

    # ── Blueprints ─────────────────────────────────────────────────────────────
    # Imported here (not at module level) to avoid circular imports.
    from app.auth import auth as auth_blueprint
    from app.library import library as library_blueprint
    from app.main import STATUS_CONFIG, main as main_blueprint
    from app.manager import manager as manager_blueprint

    app.register_blueprint(auth_blueprint)
    app.register_blueprint(main_blueprint)
    app.register_blueprint(manager_blueprint)
    app.register_blueprint(library_blueprint)

    # ── Flask-Login user loader ────────────────────────────────────────────────
    # app.models is now in sys.modules (loaded transitively via auth blueprint).
    from app.models import User

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))

    # ── Jinja2 globals ─────────────────────────────────────────────────────────
    # Makes OAuth config available in every template without passing it
    # explicitly from every view function.
    app.jinja_env.globals.update(
        OAUTH2_CONFIGURED=app.config.get('OAUTH2_CONFIGURED', False),
        OAUTH2_BUTTON=app.config.get(
            'OAUTH2_BUTTON', {'name': 'SSO', 'icon': 'bi-box-arrow-in-right'}
        ),
        ALLOW_REGISTRATION=app.config.get('ALLOW_REGISTRATION', True),
        STATUS_CONFIG=STATUS_CONFIG,
    )

    # ── Background scheduler ───────────────────────────────────────────────────
    from app.scheduler import init_scheduler

    init_scheduler(app)

    return app
