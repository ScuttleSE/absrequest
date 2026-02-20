import logging
import threading
from datetime import datetime, timedelta

from app import cache, db
from app.models import AudiobookRequest, SyncLog

_ITEMS_CACHE_KEY = 'abs_all_items'
_ITEMS_CACHE_TIMEOUT = 600

logger = logging.getLogger(__name__)

# Statuses that are still "open" and worth checking against ABS
_CHECKABLE_STATUSES = ('pending', 'in_progress', 'possible_match')


def run_abs_sync(app, triggered_by='scheduler', triggered_by_user_id=None):
    """Run a full ABS library sync within the given app context.

    Fetches all items from ABS (bypassing cache), then compares every active
    audiobook request against the library.  Requests with a certain match are
    marked 'fulfilled'; those with only a possible match become 'possible_match'.
    Runs synchronously — call trigger_manual_sync() to run in a thread.
    """
    with app.app_context():
        # ── Concurrency guard ───────────────────────────────────────────────────
        # Refuse to start if another sync that started within the last 5 minutes
        # is still marked as running.
        cutoff = datetime.utcnow() - timedelta(minutes=5)
        already_running = SyncLog.query.filter(
            SyncLog.status == 'running',
            SyncLog.started_at > cutoff,
        ).first()
        if already_running:
            logger.info(
                'Sync skipped — another sync is already running (id=%d)',
                already_running.id,
            )
            return

        # ── Create sync log ─────────────────────────────────────────────────────
        sync_log = SyncLog(
            status='running',
            triggered_by=triggered_by,
            triggered_by_user_id=triggered_by_user_id,
        )
        db.session.add(sync_log)
        db.session.commit()
        log_id = sync_log.id
        logger.info(
            'ABS sync started (log id=%d, triggered_by=%s)', log_id, triggered_by
        )

        try:
            # ── Fetch ABS items (no cache — always fresh for sync) ──────────────
            abs_url = app.config.get('AUDIOBOOKSHELF_URL')
            if not abs_url:
                raise RuntimeError('AUDIOBOOKSHELF_URL is not configured')

            from app.services.audiobookshelf import AudiobookshelfClient

            client = AudiobookshelfClient()
            abs_items = client.get_all_items_all_libraries()

            # Refresh the shared cache so the library browser and search pages
            # reflect the newly fetched items immediately after sync.
            cache.set(_ITEMS_CACHE_KEY, abs_items, timeout=_ITEMS_CACHE_TIMEOUT)

            if not abs_items:
                logger.warning('ABS sync: no items returned from ABS library')

            # ── Set up matcher ──────────────────────────────────────────────────
            from app.services.library_matcher import LibraryMatcher

            threshold = float(app.config.get('ABS_MATCH_THRESHOLD', 0.85))
            matcher = LibraryMatcher(threshold=threshold)

            # ── Fetch checkable requests ────────────────────────────────────────
            active_requests = AudiobookRequest.query.filter(
                AudiobookRequest.status.in_(_CHECKABLE_STATUSES)
            ).all()

            total_checked = len(active_requests)
            matched_ids = []

            for req in active_requests:
                req.last_sync_checked_at = datetime.utcnow()

                if not abs_items:
                    continue

                check = matcher.check_single(
                    req.title, req.author or '', abs_items
                )

                if check['found'] and check['is_certain']:
                    match = check['match']
                    req.status = 'fulfilled'
                    req.fulfilled_by_sync = True
                    req.abs_match_title = match.get('title', '')
                    req.abs_match_author = match.get('author', '')
                    matched_ids.append(req.id)
                    logger.info(
                        'Sync matched request %d ("%s") → ABS "%s"',
                        req.id,
                        req.title,
                        match.get('title', ''),
                    )
                elif check['found'] and not check['is_certain']:
                    # Possible match — mark only if still in a mutable state
                    if req.status not in ('fulfilled', 'completed', 'rejected'):
                        match = check['match']
                        req.status = 'possible_match'
                        req.abs_match_title = match.get('title', '')
                        req.abs_match_author = match.get('author', '')
                else:
                    # No match — if it was flagged as possible_match, revert
                    if req.status == 'possible_match':
                        req.status = 'pending'
                        req.abs_match_title = None
                        req.abs_match_author = None

            db.session.commit()

            # ── Finalise sync log ───────────────────────────────────────────────
            sync_log = db.session.get(SyncLog, log_id)
            sync_log.status = 'completed'
            sync_log.finished_at = datetime.utcnow()
            sync_log.total_requests_checked = total_checked
            sync_log.total_matches_found = len(matched_ids)
            sync_log.matched_request_ids = matched_ids
            db.session.commit()

            logger.info(
                'ABS sync completed (log id=%d): checked=%d, matched=%d',
                log_id,
                total_checked,
                len(matched_ids),
            )

        except Exception as exc:  # noqa: BLE001
            logger.exception('ABS sync failed: %s', exc)
            try:
                sync_log = db.session.get(SyncLog, log_id)
                sync_log.status = 'failed'
                sync_log.finished_at = datetime.utcnow()
                sync_log.error_message = str(exc)
                db.session.commit()
            except Exception:  # noqa: BLE001
                logger.exception('Failed to update sync log after sync error')


def trigger_manual_sync(app, triggered_by_user_id=None):
    """Spawn a daemon thread to run an ABS sync immediately.

    Returns immediately; the sync runs in the background.
    """
    thread = threading.Thread(
        target=run_abs_sync,
        args=(app,),
        kwargs={
            'triggered_by': 'manual',
            'triggered_by_user_id': triggered_by_user_id,
        },
        daemon=True,
    )
    thread.start()
    return thread
