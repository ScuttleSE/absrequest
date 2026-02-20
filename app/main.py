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
from flask_login import current_user, login_required
from sqlalchemy import or_

from app import cache, db
from app.models import AudiobookRequest
from app.services.book_search import BookSearchService

main = Blueprint('main', __name__)

# Statuses that count as "already requested" when checking search results
_ACTIVE_STATUSES = ('pending', 'in_progress', 'completed', 'fulfilled')

# Statuses that block a new duplicate submission
_OPEN_STATUSES = ('pending', 'in_progress')

# Shared cache constants (same key/timeout used in library.py)
_ITEMS_CACHE_KEY = 'abs_all_items'
_ITEMS_CACHE_TIMEOUT = 600

STATUS_CONFIG: dict[str, dict] = {
    'pending':        {'label': 'Pending',            'badge': 'secondary', 'icon': 'bi-clock'},
    'in_progress':    {'label': 'In Progress',         'badge': 'warning',   'icon': 'bi-gear'},
    'completed':      {'label': 'Completed',           'badge': 'success',   'icon': 'bi-check-circle'},
    'fulfilled':      {'label': 'Found Automatically', 'badge': 'primary',   'icon': 'bi-arrow-repeat'},
    'possible_match': {'label': 'Possible Match',      'badge': 'info',      'icon': 'bi-question-circle'},
    'rejected':       {'label': 'Rejected',            'badge': 'danger',    'icon': 'bi-x-circle'},
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _build_or_filter(
    isbn: str | None,
    google_books_id: str | None,
    asin: str | None = None,
) -> list:
    """Return SQLAlchemy OR conditions for a book identified by any known ID."""
    conditions = []
    if isbn:
        conditions.append(AudiobookRequest.isbn == isbn)
    if google_books_id:
        conditions.append(AudiobookRequest.google_books_id == google_books_id)
    if asin:
        conditions.append(AudiobookRequest.asin == asin)
    return conditions


def _get_abs_items() -> list[dict]:
    """Return cached ABS library items, fetching from ABS on a cache miss."""
    items = cache.get(_ITEMS_CACHE_KEY)
    if items is None:
        if current_app.config.get('AUDIOBOOKSHELF_URL'):
            # Import lazily to avoid circular-import issues at module load time
            from app.services.audiobookshelf import AudiobookshelfClient
            items = AudiobookshelfClient().get_all_items_all_libraries()
            cache.set(_ITEMS_CACHE_KEY, items, timeout=_ITEMS_CACHE_TIMEOUT)
        else:
            items = []
    return items


# ── Routes ─────────────────────────────────────────────────────────────────────


@main.route('/')
@login_required
def index():
    import random
    abs_configured = bool(current_app.config.get('AUDIOBOOKSHELF_URL'))
    cover_urls = []
    if abs_configured:
        items = _get_abs_items()
        candidates = [item['cover_url'] for item in items if item.get('cover_url')]
        if candidates:
            cover_urls = random.sample(candidates, min(6, len(candidates)))
    return render_template('main/index.html', abs_configured=abs_configured, cover_urls=cover_urls)


@main.route('/search')
@login_required
def search():
    q = request.args.get('q', '').strip()
    if not q:
        return redirect(url_for('main.index'))

    try:
        page = max(1, int(request.args.get('page', 1) or 1))
    except (ValueError, TypeError):
        page = 1

    results, total_results = BookSearchService().search(q, page=page)
    page_size = 25
    total_pages = max(1, (total_results + page_size - 1) // page_size) if total_results else None

    # ── ABS matching ──────────────────────────────────────────────────────────
    abs_items = _get_abs_items()
    matcher = None
    if abs_items:
        from app.services.library_matcher import LibraryMatcher
        threshold = float(current_app.config.get('ABS_MATCH_THRESHOLD', 0.85))
        matcher = LibraryMatcher(threshold=threshold)

    # ── Annotate each result ──────────────────────────────────────────────────
    for result in results:
        isbn = result.get('isbn')
        google_books_id = result.get('google_books_id')
        asin = result.get('asin')

        # already_requested check
        already_requested = False
        conditions = _build_or_filter(isbn, google_books_id, asin)
        if conditions:
            existing = AudiobookRequest.query.filter(
                AudiobookRequest.user_id == current_user.id,
                AudiobookRequest.status.in_(_ACTIVE_STATUSES),
                or_(*conditions),
            ).first()
            already_requested = existing is not None
        result['already_requested'] = already_requested

        # ABS match
        if matcher:
            check = matcher.check_single(
                result.get('title', ''),
                result.get('author', ''),
                abs_items,
            )
            result['abs_match'] = check['found']
            result['abs_match_certain'] = check['is_certain']
            match = check.get('match') or {}
            result['abs_match_title'] = match.get('title', '')
            result['abs_match_author'] = match.get('author', '')
        else:
            result['abs_match'] = False
            result['abs_match_certain'] = False
            result['abs_match_title'] = ''
            result['abs_match_author'] = ''

    any_certain = any(r.get('abs_match_certain') for r in results)

    return render_template(
        'main/search.html',
        results=results,
        query=q,
        page=page,
        total_pages=total_pages,
        any_certain_match=any_certain,
    )


@main.route('/request/new', methods=['GET', 'POST'])
@login_required
def request_new():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Title is required.', 'danger')
            return redirect(url_for('main.index'))

        req = AudiobookRequest(
            user_id=current_user.id,
            title=title,
            author=request.form.get('author', '').strip() or None,
            narrator=request.form.get('narrator', '').strip() or None,
            cover_url=request.form.get('cover_url', '').strip() or None,
            isbn=request.form.get('isbn', '').strip() or None,
            asin=request.form.get('asin', '').strip() or None,
            google_books_id=request.form.get('google_books_id', '').strip() or None,
            duration=request.form.get('duration', '').strip() or None,
            description=request.form.get('description', '').strip() or None,
            source=request.form.get('source', '').strip() or None,
            user_note=request.form.get('user_note', '').strip() or None,
            status='pending',
        )
        db.session.add(req)
        db.session.commit()
        flash('Request submitted successfully!', 'success')
        return redirect(url_for('main.dashboard'))

    # GET — show the pre-filled request form
    title = request.args.get('title', '').strip()
    if not title:
        return redirect(url_for('main.index'))

    isbn = request.args.get('isbn', '').strip() or None
    google_books_id = request.args.get('google_books_id', '').strip() or None
    asin = request.args.get('asin', '').strip() or None

    # Block duplicate open requests
    conditions = _build_or_filter(isbn, google_books_id, asin)
    if conditions:
        existing = AudiobookRequest.query.filter(
            AudiobookRequest.user_id == current_user.id,
            AudiobookRequest.status.in_(_OPEN_STATUSES),
            or_(*conditions),
        ).first()
        if existing:
            flash('You already have an active request for this book.', 'warning')
            return redirect(url_for('main.dashboard'))

    book = {
        'title': title,
        'author': request.args.get('author', ''),
        'narrator': request.args.get('narrator', ''),
        'cover_url': request.args.get('cover_url', ''),
        'isbn': isbn or '',
        'asin': request.args.get('asin', ''),
        'google_books_id': google_books_id or '',
        'duration': request.args.get('duration', ''),
        'description': request.args.get('description', ''),
        'source': request.args.get('source', ''),
    }
    return render_template('main/request_form.html', book=book)


@main.route('/request/<int:request_id>')
@login_required
def request_detail(request_id: int):
    req = db.get_or_404(AudiobookRequest, request_id)
    if req.user_id != current_user.id and not current_user.is_manager:
        abort(403)
    return render_template('main/request_detail.html', req=req)


@main.route('/dashboard')
@login_required
def dashboard():
    user_requests = (
        AudiobookRequest.query
        .filter_by(user_id=current_user.id)
        .order_by(AudiobookRequest.created_at.desc())
        .all()
    )

    grouped: dict[str, list] = {}
    for req in user_requests:
        grouped.setdefault(req.status, []).append(req)

    pending_count = len(grouped.get('pending', []))
    in_progress_count = len(grouped.get('in_progress', []))
    completed_count = (
        len(grouped.get('completed', []))
        + len(grouped.get('fulfilled', []))
    )

    return render_template(
        'main/dashboard.html',
        requests=user_requests,
        grouped=grouped,
        pending_count=pending_count,
        in_progress_count=in_progress_count,
        completed_count=completed_count,
    )
