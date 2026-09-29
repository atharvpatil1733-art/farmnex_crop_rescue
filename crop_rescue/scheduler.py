"""The background job. `start_scheduler()` / `stop_scheduler()` are plain
functions the host calls from its own lifespan; this module never owns the
app's lifecycle.

Crash-proof by design: the job body is wrapped in `try/except Exception`
and logs with `logger.exception`, so a failing run can never stop the
scheduler or the host backend. `max_instances=1` and `coalesce=True` mean
runs never pile up if one takes longer than the interval.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from . import db, service
from .config import settings

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _run_scheduled_check() -> None:
    """The job body. Never raises, whatever goes wrong inside it."""
    try:
        engine = db.get_engine()
        service.run_check(engine, now=datetime.now(timezone.utc))
    except Exception:
        logger.exception("crop_rescue: scheduled check failed")


def start_scheduler() -> None:
    """Start the background job, unless CR_ENABLE_SCHEDULER=false or it's already running."""
    global _scheduler
    if not settings.enable_scheduler or _scheduler is not None:
        return
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _run_scheduled_check,
        "interval",
        hours=settings.check_interval_hours,
        id="crop_rescue_check",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()


def stop_scheduler() -> None:
    """Stop the background job. Safe to call even if it was never started."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
