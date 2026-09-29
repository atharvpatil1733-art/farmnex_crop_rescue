"""The temperature given at registration is kept and reused by later checks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from crop_rescue import service


class _Stop(Exception):
    pass


def _temperature_used(monkeypatch, stored, explicit):
    seen = {}

    def fake_compute(crop, storage_mode, lat, lng, temperature_c, freshness_before, elapsed):
        seen["temp"] = temperature_c
        raise _Stop

    monkeypatch.setattr(service, "_compute_check", fake_compute)
    lot = SimpleNamespace(
        crop_code="tomato", status="FRESH", storage_mode="ambient", lat=18.5, lng=73.8,
        temperature_c=stored, freshness_used=0.0,
    )
    with pytest.raises(_Stop):
        service._apply_check(None, lot, elapsed_hours=12, temperature_c=explicit, checked_at=datetime.now(timezone.utc))
    return seen["temp"]


def test_later_check_reuses_the_stored_temperature(monkeypatch):
    assert _temperature_used(monkeypatch, stored=20.0, explicit=None) == 20.0


def test_explicit_temperature_wins_for_that_call(monkeypatch):
    assert _temperature_used(monkeypatch, stored=20.0, explicit=35.0) == 35.0


def test_no_stored_temperature_falls_back_to_normal_resolution(monkeypatch):
    assert _temperature_used(monkeypatch, stored=None, explicit=None) is None


def test_lot_registered_at_20c_is_rechecked_at_20c(db):
    now = datetime.now(timezone.utc)
    lot = service.create_lot(
        db, "farmer-temp", crop_code="tomato", quantity_kg=100, harvested_at=now, lat=18.52, lng=73.85,
        storage_mode="ambient", floor_price_per_kg=0, temperature_c=20.0, now=now,
    )
    assert lot.temperature_c == 20.0

    later = now + timedelta(hours=12)
    service.run_check(db, now=later)
    _, checks = service.get_lot_detail(db, "farmer-temp", lot.id)
    assert checks[0].temperature_c == 20.0
    assert checks[0].temp_source == "request"
