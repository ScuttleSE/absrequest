from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError

from app import db, oauth
from app.models import User

auth = Blueprint('auth', __name__, url_prefix='/auth')


# ── Forms ──────────────────────────────────────────────────────────────────────


class RegistrationForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField(
        'Confirm Password',
        validators=[
            DataRequired(),
            EqualTo('password', message='Passwords must match.'),
        ],
    )
    submit = SubmitField('Create Account')

    def validate_email(self, field: StringField) -> None:
        if User.query.filter_by(email=field.data.strip().lower()).first():
            raise ValidationError('An account with that email already exists.')


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Log In')


# ── Local auth routes ──────────────────────────────────────────────────────────


@auth.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    if not current_app.config.get('ALLOW_REGISTRATION'):
        flash(
            'Registration is currently disabled. Please contact an administrator.',
            'warning',
        )
        return redirect(url_for('auth.login'))

    form = RegistrationForm()
    if form.validate_on_submit():
        is_first_user = User.query.count() == 0
        user = User(
            name=form.name.data.strip(),
            email=form.email.data.strip().lower(),
            role='manager' if is_first_user else 'user',
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Account created successfully. Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html', form=form)


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.strip().lower()).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.dashboard'))
        flash('Invalid email or password.', 'danger')

    return render_template('auth/login.html', form=form)


@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


@auth.route('/forgot-password')
def forgot_password():
    return render_template('auth/forgot_password.html')


# ── OAuth2 / OIDC routes ───────────────────────────────────────────────────────


@auth.route('/login/oidc')
def login_oidc():
    if not current_app.config.get('OAUTH2_CONFIGURED'):
        abort(404)
    redirect_uri = url_for('auth.callback_oidc', _external=True)
    return oauth.oidc.authorize_redirect(redirect_uri)


@auth.route('/callback/oidc')
def callback_oidc():
    if not current_app.config.get('OAUTH2_CONFIGURED'):
        abort(404)

    try:
        token = oauth.oidc.authorize_access_token()
    except RuntimeError as exc:
        if 'jwks_uri' in str(exc):
            flash(
                'SSO login failed: the provider\'s JWKS endpoint could not be '
                'discovered. Set OAUTH2_SERVER_METADATA_URL in your .env file '
                'to the provider\'s OpenID Connect discovery URL '
                '(e.g. https://auth.example.com/.well-known/openid-configuration).',
                'danger',
            )
            return redirect(url_for('auth.login'))
        raise

    # For OIDC providers the userinfo may be embedded in the id_token claims,
    # or we need to fetch it from the userinfo endpoint.
    userinfo = token.get('userinfo') or oauth.oidc.userinfo()

    sub: str = userinfo.get('sub', '')
    email: str = userinfo.get('email', '').strip().lower()
    name: str = (
        userinfo.get('name')
        or userinfo.get('preferred_username')
        or email
    )
    picture: str | None = userinfo.get('picture')

    if not email:
        flash('Could not retrieve your email address from the SSO provider.', 'danger')
        return redirect(url_for('auth.login'))

    # 1. Existing user matched by OAuth provider + subject ID
    user = User.query.filter_by(oauth_provider='oidc', oauth_provider_id=sub).first()

    if user:
        login_user(user)
    else:
        # 2. Existing user matched by email — link the OAuth account
        user = User.query.filter_by(email=email).first()
        if user:
            user.oauth_provider = 'oidc'
            user.oauth_provider_id = sub
            if picture:
                user.avatar_url = picture
            db.session.commit()
            login_user(user)
        else:
            # 3. No matching user — create a new one
            is_first_user = User.query.count() == 0
            user = User(
                name=name,
                email=email,
                avatar_url=picture,
                oauth_provider='oidc',
                oauth_provider_id=sub,
                role='manager' if is_first_user else 'user',
            )
            db.session.add(user)
            db.session.commit()
            login_user(user)

    return redirect(url_for('main.dashboard'))
