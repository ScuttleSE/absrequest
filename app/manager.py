from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import func

from app import db
from app.models import AppSettings, AudiobookRequest, SyncLog, User

manager = Blueprint('manager', __name__, url_prefix='/manager')

_VALID_STATUSES = (
    'pending',
    'in_progress',
    'completed',
    'fulfilled',
    'possible_match',
    'rejected',
)


# ── Access guard ───────────────────────────────────────────────────────────────


def manager_required(f):
    """Decorator: authenticate and require role == 'manager'."""

    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_manager:
            abort(403)
        return f(*args, **kwargs)

    return decorated


# ── Dashboard ──────────────────────────────────────────────────────────────────


@manager.route('/')
@manager.route('/dashboard')
@manager_required
def dashboard():
    status_counts = dict(
        db.session.query(AudiobookRequest.status, func.count(AudiobookRequest.id))
        .group_by(AudiobookRequest.status)
        .all()
    )
    total_users = db.session.query(func.count(User.id)).scalar()

    recent_requests = (
        AudiobookRequest.query.order_by(AudiobookRequest.created_at.desc())
        .limit(10)
        .all()
    )

    last_sync = (
        SyncLog.query.filter(SyncLog.status.in_(['completed', 'failed']))
        .order_by(SyncLog.finished_at.desc())
        .first()
    )
    is_running = SyncLog.query.filter_by(status='running').first() is not None

    return render_template(
        'manager/dashboard.html',
        status_counts=status_counts,
        total_users=total_users,
        recent_requests=recent_requests,
        last_sync=last_sync,
        is_running=is_running,
    )


# ── Request management ─────────────────────────────────────────────────────────


@manager.route('/requests')
@manager_required
def requests_list():
    status_filter = request.args.get('status', '')
    q = AudiobookRequest.query
    if status_filter:
        q = q.filter_by(status=status_filter)
    all_requests = q.order_by(AudiobookRequest.created_at.desc()).all()
    return render_template(
        'manager/requests.html',
        requests=all_requests,
        status_filter=status_filter,
    )


@manager.route('/requests/<int:request_id>', methods=['GET', 'POST'])
@manager_required
def request_edit(request_id):
    req = db.get_or_404(AudiobookRequest, request_id)

    if request.method == 'POST':
        new_status = request.form.get('status', '').strip()
        manager_note = request.form.get('manager_note', '').strip() or None

        if new_status not in _VALID_STATUSES:
            flash('Invalid status.', 'danger')
        else:
            req.status = new_status
            req.manager_note = manager_note
            db.session.commit()
            flash('Request updated.', 'success')
            return redirect(url_for('manager.dashboard'))

    return render_template('manager/request_edit.html', req=req)


# ── User management ────────────────────────────────────────────────────────────


@manager.route('/users')
@manager_required
def users():
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template('manager/users.html', users=all_users)


@manager.route('/users/<int:user_id>/toggle-role', methods=['POST'])
@manager_required
def toggle_user_role(user_id):
    user = db.get_or_404(User, user_id)

    if user.id == current_user.id:
        flash('You cannot change your own role.', 'warning')
        return redirect(url_for('manager.users'))

    user.role = 'user' if user.is_manager else 'manager'
    db.session.commit()

    role_label = 'manager' if user.is_manager else 'regular user'
    flash(f'{user.name} is now a {role_label}.', 'success')
    return redirect(url_for('manager.users'))


# ── Stats ──────────────────────────────────────────────────────────────────────


@manager.route('/stats')
@manager_required
def stats():
    status_counts = dict(
        db.session.query(AudiobookRequest.status, func.count(AudiobookRequest.id))
        .group_by(AudiobookRequest.status)
        .all()
    )
    total = sum(status_counts.values())
    completed_total = (
        status_counts.get('completed', 0) + status_counts.get('fulfilled', 0)
    )
    completion_rate = round(completed_total / total * 100) if total else 0

    top_requesters = (
        db.session.query(User, func.count(AudiobookRequest.id).label('req_count'))
        .join(AudiobookRequest, User.id == AudiobookRequest.user_id)
        .group_by(User.id)
        .order_by(func.count(AudiobookRequest.id).desc())
        .limit(10)
        .all()
    )

    # Monthly counts — computed in Python for SQLite/PostgreSQL portability
    all_reqs = AudiobookRequest.query.order_by(AudiobookRequest.created_at).all()
    monthly: dict[str, int] = {}
    for req in all_reqs:
        key = req.created_at.strftime('%Y-%m')
        monthly[key] = monthly.get(key, 0) + 1

    sync_history = (
        SyncLog.query.filter(SyncLog.status.in_(['completed', 'failed']))
        .order_by(SyncLog.finished_at.desc())
        .limit(10)
        .all()
    )

    return render_template(
        'manager/stats.html',
        status_counts=status_counts,
        total=total,
        completion_rate=completion_rate,
        top_requesters=top_requesters,
        monthly=monthly,
        sync_history=sync_history,
    )


# ── Sync ───────────────────────────────────────────────────────────────────────


@manager.route('/sync', methods=['POST'])
@manager_required
def trigger_sync():
    if not current_app.config.get('AUDIOBOOKSHELF_URL'):
        flash('Audiobookshelf is not configured.', 'danger')
        return redirect(url_for('manager.dashboard'))

    cutoff = datetime.utcnow() - timedelta(minutes=5)
    already_running = SyncLog.query.filter(
        SyncLog.status == 'running',
        SyncLog.started_at > cutoff,
    ).first()
    if already_running:
        flash('A sync is already in progress.', 'warning')
        return redirect(url_for('manager.dashboard'))

    from app.services.sync import trigger_manual_sync

    trigger_manual_sync(
        current_app._get_current_object(),
        triggered_by_user_id=current_user.id,
    )
    flash('Sync started in the background.', 'success')
    return redirect(url_for('manager.dashboard'))


@manager.route('/sync/status')
@manager_required
def sync_status():
    configured = bool(current_app.config.get('AUDIOBOOKSHELF_URL'))

    last_sync = (
        SyncLog.query.filter(SyncLog.status.in_(['completed', 'failed']))
        .order_by(SyncLog.finished_at.desc())
        .first()
    )
    is_running = SyncLog.query.filter_by(status='running').first() is not None

    next_run = None
    if hasattr(current_app, 'scheduler') and current_app.scheduler:
        job = current_app.scheduler.get_job('abs_sync')
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat()

    return jsonify(
        {
            'configured': configured,
            'last_sync': (
                last_sync.finished_at.isoformat()
                if last_sync and last_sync.finished_at
                else None
            ),
            'last_sync_status': last_sync.status if last_sync else None,
            'is_running': is_running,
            'next_run': next_run,
        }
    )


# ── Sync logs ──────────────────────────────────────────────────────────────────


@manager.route('/sync-logs')
@manager_required
def sync_logs():
    page = request.args.get('page', 1, type=int)
    pagination = SyncLog.query.order_by(SyncLog.started_at.desc()).paginate(
        page=page, per_page=25, error_out=False
    )
    return render_template(
        'manager/sync_logs.html',
        pagination=pagination,
        logs=pagination.items,
    )


# ── Settings ───────────────────────────────────────────────────────────────────


_AUDIBLE_REGIONS = ['us', 'uk', 'au', 'ca', 'de', 'fr', 'it', 'es', 'jp', 'in']


@manager.route('/settings', methods=['GET', 'POST'])
@manager_required
def settings():
    s = AppSettings.get()

    if request.method == 'POST':
        s.audible_enabled = 'audible_enabled' in request.form
        region = request.form.get('audible_region', 'us').lower()
        s.audible_region = region if region in _AUDIBLE_REGIONS else 'us'
        s.open_library_enabled = 'open_library_enabled' in request.form
        db.session.commit()
        flash('Settings saved.', 'success')
        return redirect(url_for('manager.settings'))

    return render_template(
        'manager/settings.html',
        settings=s,
        audible_regions=_AUDIBLE_REGIONS,
    )


@manager.route('/sync-logs/<int:log_id>')
@manager_required
def sync_log_detail(log_id):
    log = db.get_or_404(SyncLog, log_id)

    matched_requests = []
    if log.matched_request_ids:
        matched_requests = AudiobookRequest.query.filter(
            AudiobookRequest.id.in_(log.matched_request_ids)
        ).all()

    triggered_by_user = None
    if log.triggered_by_user_id:
        triggered_by_user = db.session.get(User, log.triggered_by_user_id)

    return render_template(
        'manager/sync_log_detail.html',
        log=log,
        matched_requests=matched_requests,
        triggered_by_user=triggered_by_user,
    )
