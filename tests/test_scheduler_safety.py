"""Scheduler safety: a failing job body logs and returns, never raises.

Needs no database: the repository call inside the job is monkeypatched to
raise directly, so this never touches CR_TEST_DATABASE_URL.
"""

from __future__ import annotations

import logging

from crop_rescue import scheduler, service, settings


def test_scheduled_check_logs_and_returns_when_run_check_raises(monkeypatch, caplog):
    """Verify that a scheduled-check failure is logged with exception information."""
    def boom(engine, *, now):
        """Simulate a database failure while running a freshness check."""
        raise RuntimeError("the database fell over")

    monkeypatch.setattr(service, "run_check", boom)

    with caplog.at_level(logging.ERROR, logger="crop_rescue.scheduler"):
        scheduler._run_scheduled_check()  # must not raise

    assert any("scheduled check failed" in record.message for record in caplog.records)
    assert any(record.exc_info is not None for record in caplog.records)


def test_scheduled_check_logs_and_returns_when_get_engine_raises(monkeypatch, caplog):
    """Verify that engine lookup failures are logged without escaping the job."""
    def boom():
        """Simulate failure to obtain a configured database engine."""
        raise RuntimeError("no database configured")

    monkeypatch.setattr("crop_rescue.scheduler.db.get_engine", boom)

    with caplog.at_level(logging.ERROR, logger="crop_rescue.scheduler"):
        scheduler._run_scheduled_check()  # must not raise

    assert any("scheduled check failed" in record.message for record in caplog.records)


def test_start_scheduler_is_a_noop_when_disabled(monkeypatch):
    """Verify that disabling scheduling prevents scheduler creation."""
    monkeypatch.setattr(settings, "enable_scheduler", False)
    scheduler.start_scheduler()
    try:
        assert scheduler._scheduler is None
    finally:
        scheduler.stop_scheduler()  # safe even though nothing started


def test_stop_scheduler_is_safe_when_never_started():
    """Verify that stopping an absent scheduler is harmless."""
    scheduler.stop_scheduler()  # must not raise
    assert scheduler._scheduler is None


def test_one_failing_lot_does_not_stop_the_rest(monkeypatch):
    """A lot that raises is logged and skipped; later lots are still checked."""
    from datetime import datetime, timezone
    from types import SimpleNamespace

    from crop_rescue import service

    now = datetime.now(timezone.utc)
    lots = [SimpleNamespace(id=n, harvested_at=now, last_checked_at=now) for n in ("bad", "good")]
    monkeypatch.setattr(service.repo, "list_active_lots", lambda engine: lots)

    def fake_apply(engine, lot, **kwargs):
        if lot.id == "bad":
            raise RuntimeError("boom")
        return SimpleNamespace(status="AT_RISK")

    monkeypatch.setattr(service, "_apply_check", fake_apply)
    assert service.run_check(None, now=now) == {"checked": 1, "at_risk": 1, "spoiled": 0}
