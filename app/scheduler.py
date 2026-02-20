import logging

logger = logging.getLogger(__name__)


def init_scheduler(app):
    """Configure and start Flask-APScheduler if ABS is configured.

    The scheduler instance is attached to ``app.scheduler`` so other code can
    inspect it (e.g. to read ``next_run_time``).  ``app.scheduler`` is set to
    ``None`` when scheduling is skipped or fails.
    """
    app.scheduler = None

    if not app.config.get('AUDIOBOOKSHELF_URL'):
        logger.info('APScheduler not started — AUDIOBOOKSHELF_URL is not set')
        return

    try:
        from flask_apscheduler import APScheduler

        interval_hours = int(app.config.get('ABS_SYNC_INTERVAL_HOURS', 6))

        scheduler = APScheduler()
        scheduler.init_app(app)

        # Pass the real app object (not the proxy) so the background thread
        # can push its own application context.
        scheduler.add_job(
            id='abs_sync',
            func=_run_scheduled_sync,
            args=[app._get_current_object()],
            trigger='interval',
            hours=interval_hours,
            replace_existing=True,
        )

        scheduler.start()
        app.scheduler = scheduler

        logger.info(
            'APScheduler started — ABS sync every %d hour(s)', interval_hours
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception('Failed to start APScheduler: %s', exc)


def _run_scheduled_sync(app):
    """Wrapper called by APScheduler — imported lazily to avoid circular imports."""
    from app.services.sync import run_abs_sync

    run_abs_sync(app, triggered_by='scheduler')
