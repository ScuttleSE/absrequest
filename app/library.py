"""
Library blueprint.

Routes defined here (no blueprint prefix — full paths are declared on each
route so the API endpoints can live at /api/... without a separate blueprint):

  GET /library               — ABS library browser
  GET /api/library/check     — JSON: fuzzy-match a title+author against ABS
  GET /api/abs/status        — JSON: ABS connection status for the navbar pill
"""

from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import current_user, login_required

from app import cache
from app.services.audiobookshelf import AudiobookshelfClient
from app.services.library_matcher import LibraryMatcher

library = Blueprint('library', __name__)

_ITEMS_CACHE_KEY = 'abs_all_items'
_LIBS_CACHE_KEY = 'abs_libraries'
_ITEMS_CACHE_TIMEOUT = 600   # 10 minutes
_STATUS_CACHE_TIMEOUT = 60   # 1 minute
_PAGE_SIZE = 50


# ── Shared cache helpers ──────────────────────────────────────────────────────

def _cached_libraries() -> list[dict]:
    libs = cache.get(_LIBS_CACHE_KEY)
    if libs is None:
        libs = AudiobookshelfClient().get_libraries()
        cache.set(_LIBS_CACHE_KEY, libs, timeout=_ITEMS_CACHE_TIMEOUT)
    return libs


def _cached_items() -> list[dict]:
    """Return all ABS items from cache, fetching from ABS on a miss."""
    items = cache.get(_ITEMS_CACHE_KEY)
    if items is None:
        items = AudiobookshelfClient().get_all_items_all_libraries()
        cache.set(_ITEMS_CACHE_KEY, items, timeout=_ITEMS_CACHE_TIMEOUT)
    return items


# ── HTML routes ───────────────────────────────────────────────────────────────

@library.route('/library')
@login_required
def index():
    abs_configured = bool(current_app.config.get('AUDIOBOOKSHELF_URL'))

    if not abs_configured:
        return render_template('library/index.html', abs_configured=False)

    libraries = _cached_libraries()

    # Determine selected library
    selected_id = request.args.get('library_id', '').strip()
    if not selected_id and libraries:
        selected_id = libraries[0].get('id', '')

    q = request.args.get('q', '').strip().lower()

    try:
        page = max(1, int(request.args.get('page', 1) or 1))
    except (ValueError, TypeError):
        page = 1

    # Pull everything from cache (or fetch once)
    all_items = _cached_items()

    # Filter by library
    filtered = (
        [item for item in all_items if item.get('library_id') == selected_id]
        if selected_id
        else all_items
    )

    # Filter by search query (substring match in title or author)
    if q:
        filtered = [
            item for item in filtered
            if q in (item.get('title') or '').lower()
            or q in (item.get('author') or '').lower()
        ]

    # Paginate
    total = len(filtered)
    pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page = min(page, pages)
    start = (page - 1) * _PAGE_SIZE
    items = filtered[start: start + _PAGE_SIZE]

    return render_template(
        'library/index.html',
        abs_configured=True,
        items=items,
        total=total,
        page=page,
        pages=pages,
        libraries=libraries,
        selected_library_id=selected_id,
        query=q,
    )


# ── JSON API endpoints ────────────────────────────────────────────────────────

@library.route('/api/library/check')
def api_library_check():
    """Fuzzy-match a title+author against the cached ABS library."""
    if not current_user.is_authenticated:
        return jsonify({'error': 'Unauthorized'}), 401

    abs_configured = bool(current_app.config.get('AUDIOBOOKSHELF_URL'))
    if not abs_configured:
        return jsonify({'configured': False})

    title = request.args.get('title', '').strip()
    author = request.args.get('author', '').strip()

    items = _cached_items()
    threshold = float(current_app.config.get('ABS_MATCH_THRESHOLD', 0.85))
    matcher = LibraryMatcher(threshold=threshold)
    result = matcher.check_single(title, author, items)

    match_data = None
    if result.get('match'):
        match_data = {
            'title': result['match'].get('title'),
            'author': result['match'].get('author'),
        }

    return jsonify({
        'configured': True,
        'found': result.get('found', False),
        'is_certain': result.get('is_certain', False),
        'match': match_data,
    })


@library.route('/api/abs/status')
def api_abs_status():
    """Return ABS connection status (used by the navbar pill)."""
    if not current_user.is_authenticated:
        return jsonify({'error': 'Unauthorized'}), 401
    status = cache.get('abs_status')
    if status is None:
        status = AudiobookshelfClient().get_status()
        cache.set('abs_status', status, timeout=_STATUS_CACHE_TIMEOUT)
    return jsonify(status)
