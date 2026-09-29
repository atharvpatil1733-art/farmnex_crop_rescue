"""Business logic. Ownership checks (404 for another farmer's data), the
`on_alert` hook, and check-on-read all live here, between `api.py` (HTTP
only) and `repository.py` (SQL only).
"""

from __future__ import annotations

import dataclasses
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

from fastapi import HTTPException
from sqlalchemy import Engine

from . import repository as repo
from .config import settings
from .core import matching
from .core import shelf_life
from .core import status as status_module
from .core.status import Status

logger = logging.getLogger(__name__)

_on_alert: Callable[[repo.AlertRecord], None] | None = None


def configure_on_alert(callback: Callable[[repo.AlertRecord], None] | None) -> None:
    """Let the host receive a call (e.g. to send an FCM push) whenever a new
    alert is created. Optional; by default alerts are only written to
    `cr_alerts` and Flutter polls `GET /rescue/alerts`.
    """
    global _on_alert
    _on_alert = callback


def _notify(alert: repo.AlertRecord | None) -> None:
    """Call the host's on_alert hook. A duplicate alert (None) is not sent."""
    if alert is None or _on_alert is None:
        return
    try:
        _on_alert(alert)
    except Exception:
        logger.exception("crop_rescue: on_alert callback raised")


def list_crops() -> list[dict]:
    """The 8 crops with their life at 25/30/35 °C, for GET /rescue/crops."""
    out = []
    for crop in shelf_life.load_crops().values():
        out.append(
            {
                "code": crop.code,
                "name_en": crop.name_en,
                "name_mr": crop.name_mr,
                "ref_temp_c": crop.ref_temp_c,
                "ref_life_hours": crop.ref_life_hours,
                "life_hours_at_25c": round(shelf_life.crop_life_hours(crop, 25.0, settings.q10), 1),
                "life_hours_at_30c": round(shelf_life.crop_life_hours(crop, 30.0, settings.q10), 1),
                "life_hours_at_35c": round(shelf_life.crop_life_hours(crop, 35.0, settings.q10), 1),
                "source": crop.source,
                "note": crop.note,
            }
        )
    return out


def health(engine: Engine | None) -> dict:
    """GET /rescue/health. `db` is False if no engine is configured or it can't connect."""
    db_ok = False
    if engine is not None:
        try:
            import sqlalchemy as sa

            with engine.connect() as conn:
                conn.execute(sa.text("SELECT 1"))
            db_ok = True
        except Exception:
            db_ok = False
    return {"ok": True, "crops": len(shelf_life.load_crops()), "db": db_ok}


def _resolve_temperature(lat: float, lng: float, temperature_c: float | None) -> tuple[float, str]:
    """Temperature source, in priority order: request, Open-Meteo (if enabled), default.

    Open-Meteo gets a 3 s timeout and any error falls back to the default,
    so a flaky network call never breaks a check.
    """
    if temperature_c is not None:
        return temperature_c, "request"

    if settings.use_open_meteo:
        try:
            import httpx

            response = httpx.get(
                "https://api.open-meteo.com/v1/forecast",
                params={"latitude": lat, "longitude": lng, "current": "temperature_2m"},
                timeout=3.0,
            )
            response.raise_for_status()
            temp_c = float(response.json()["current"]["temperature_2m"])
            return temp_c, "open_meteo"
        except Exception:
            logger.exception("crop_rescue: Open-Meteo lookup failed, using CR_DEFAULT_TEMP_C")

    return settings.default_temp_c, "default"


def _compute_check(
    crop: shelf_life.Crop,
    storage_mode: str,
    lat: float,
    lng: float,
    temperature_c: float | None,
    freshness_before: float,
    elapsed_hours: float,
) -> tuple[float, str, float, float, Status]:
    """Run the Q10 model for one check. Returns (temp_c, temp_source,
    freshness_used, remaining_hours, status)."""
    temp_c, temp_source = _resolve_temperature(lat, lng, temperature_c)
    effective_temp = shelf_life.effective_temp_c(crop, storage_mode, temp_c)
    life = shelf_life.crop_life_hours(crop, effective_temp, settings.q10)
    freshness_used = shelf_life.advance_freshness(freshness_before, elapsed_hours, life)
    remaining = shelf_life.remaining_hours(freshness_used, life)
    new_status = status_module.status_for(remaining, settings.alert_hours, settings.check_interval_hours)
    return temp_c, temp_source, freshness_used, remaining, new_status


def _create_at_risk_alert(conn: repo.Bind, lot: repo.LotRecord) -> repo.AlertRecord | None:
    """Insert an AT_RISK alert with buyer matches, returning None for a duplicate."""
    buyers = repo.list_buyers_for_crop(conn, lot.crop_code)
    lot_for_matching = matching.LotForMatching(
        crop_code=lot.crop_code,
        quantity_kg=lot.quantity_kg,
        lat=lot.lat,
        lng=lot.lng,
        floor_price_per_kg=lot.floor_price_per_kg,
        remaining_hours=lot.remaining_hours or 0.0,
    )
    matches = matching.find_matches(
        lot_for_matching,
        buyers,
        radius_km=settings.radius_km,
        road_factor=settings.road_factor,
        avg_speed_kmph=settings.avg_speed_kmph,
        loading_hours=settings.loading_hours,
        transport_rs_per_km=settings.transport_rs_per_km,
        top_n=settings.top_n,
    )
    n = len(matches)
    remaining = round(lot.remaining_hours or 0.0)
    title = f"Your {lot.quantity_kg:.0f} kg {lot.crop_code} lot needs a buyer soon"
    body = (
        f"Your {lot.quantity_kg:.0f} kg {lot.crop_code} lot has about {remaining} hours left. "
        f"{n} buyer{'s' if n != 1 else ''} near you can take it. Tap to see offers."
    )
    payload = {
        "lot_id": lot.id,
        "remaining_hours": round(lot.remaining_hours or 0.0, 1),
        "matches": [dataclasses.asdict(m) for m in matches],
    }
    return repo.insert_alert(
        conn,
        lot_id=lot.id,
        farmer_id=lot.farmer_id,
        kind="AT_RISK",
        title=title,
        body=body,
        payload=payload,
        dedup_key=f"{lot.farmer_id}:{lot.id}:AT_RISK",
    )


def _create_spoiled_alert(conn: repo.Bind, lot: repo.LotRecord) -> repo.AlertRecord | None:
    """Insert a SPOILED alert with zero remaining hours, or None for a duplicate."""
    title = f"Your {lot.quantity_kg:.0f} kg {lot.crop_code} lot has spoiled"
    body = f"Your {lot.quantity_kg:.0f} kg {lot.crop_code} lot passed its shelf life and is now marked SPOILED."
    payload = {"lot_id": lot.id, "remaining_hours": 0.0}
    return repo.insert_alert(
        conn,
        lot_id=lot.id,
        farmer_id=lot.farmer_id,
        kind="SPOILED",
        title=title,
        body=body,
        payload=payload,
        dedup_key=f"{lot.farmer_id}:{lot.id}:SPOILED",
    )


def _maybe_alert(conn: repo.Bind, prev_status: Status | None, lot: repo.LotRecord) -> repo.AlertRecord | None:
    """Write the AT_RISK or SPOILED alert if this check is that transition.

    Returns the new alert (None if no transition, or a duplicate). The
    caller sends it with `_notify` only after its transaction commits.
    """
    new_status = Status(lot.status)
    if status_module.should_alert(prev_status, new_status):
        return _create_at_risk_alert(conn, lot)
    if new_status == Status.SPOILED and prev_status != Status.SPOILED:
        return _create_spoiled_alert(conn, lot)
    return None


def create_lot(
    engine: Engine,
    farmer_id: str,
    *,
    crop_code: str,
    quantity_kg: float,
    harvested_at: datetime,
    lat: float,
    lng: float,
    storage_mode: str,
    floor_price_per_kg: float,
    temperature_c: float | None,
    now: datetime,
) -> repo.LotRecord:
    """Register a lot and run its first check immediately."""
    crops = shelf_life.load_crops()
    crop = crops.get(crop_code)
    if crop is None:
        raise HTTPException(422, f"Unknown crop_code {crop_code!r}. Valid codes: {sorted(crops)}")

    try:
        elapsed = shelf_life.elapsed_hours_since_last_check(harvested_at, None, now)
    except ValueError as exc:  # harvested_at in the future, or without a timezone
        raise HTTPException(422, f"Invalid harvested_at: {exc}") from exc
    temp_c, temp_source, freshness_used, remaining, new_status = _compute_check(
        crop, storage_mode, lat, lng, temperature_c, 0.0, elapsed
    )
    spoil_eta = now + timedelta(hours=remaining)

    # The lot, its first check row and any alert commit together or not at all.
    with engine.begin() as conn:
        lot = repo.insert_lot(
            conn,
            farmer_id=farmer_id,
            crop_code=crop_code,
            quantity_kg=quantity_kg,
            harvested_at=harvested_at,
            lat=lat,
            lng=lng,
            storage_mode=storage_mode,
            floor_price_per_kg=floor_price_per_kg,
            freshness_used=freshness_used,
            remaining_hours=remaining,
            spoil_eta=spoil_eta,
            status=new_status.value,
            last_checked_at=now,
        )
        repo.insert_check(
            conn,
            lot_id=lot.id,
            temperature_c=temp_c,
            temp_source=temp_source,
            elapsed_hours=elapsed,
            freshness_used=freshness_used,
            remaining_hours=remaining,
            status=new_status.value,
        )
        alert = _maybe_alert(conn, None, lot)
    _notify(alert)  # only after the commit, so a push never announces a rolled-back alert
    return lot


def list_lots(engine: Engine, farmer_id: str) -> list[repo.LotRecord]:
    """Run overdue freshness checks, then return the requested farmer's lots."""
    _run_check_if_stale(engine, datetime.now(timezone.utc))
    return repo.list_lots(engine, farmer_id)


def get_lot_detail(engine: Engine, farmer_id: str, lot_id: str) -> tuple[repo.LotRecord, list[repo.CheckRecord]]:
    """Return an owned lot and its check history, raising HTTP 404 if unavailable."""
    lot = repo.get_lot(engine, lot_id, farmer_id)
    if lot is None:
        raise HTTPException(404, "Lot not found")
    checks = repo.list_checks_for_lot(engine, lot_id)
    return lot, checks


def get_matches(engine: Engine, farmer_id: str, lot_id: str) -> list[matching.Match]:
    """Rank buyers for an owned AT_RISK lot.

    Raise HTTP 404 for a missing or unowned lot, or 409 for any other status.
    Return an empty list when no buyer satisfies the matching constraints.
    """
    lot = repo.get_lot(engine, lot_id, farmer_id)
    if lot is None:
        raise HTTPException(404, "Lot not found")
    if lot.status != Status.AT_RISK.value:
        raise HTTPException(409, f"Lot is {lot.status}, not AT_RISK")

    buyers = repo.list_buyers_for_crop(engine, lot.crop_code)
    lot_for_matching = matching.LotForMatching(
        crop_code=lot.crop_code,
        quantity_kg=lot.quantity_kg,
        lat=lot.lat,
        lng=lot.lng,
        floor_price_per_kg=lot.floor_price_per_kg,
        remaining_hours=lot.remaining_hours or 0.0,
    )
    return matching.find_matches(
        lot_for_matching,
        buyers,
        radius_km=settings.radius_km,
        road_factor=settings.road_factor,
        avg_speed_kmph=settings.avg_speed_kmph,
        loading_hours=settings.loading_hours,
        transport_rs_per_km=settings.transport_rs_per_km,
        top_n=settings.top_n,
    )


def mark_sold(engine: Engine, farmer_id: str, lot_id: str) -> repo.LotRecord:
    """Mark an owned lot SOLD, raising HTTP 404 if it is missing or unowned."""
    lot = repo.mark_lot_sold(engine, lot_id, farmer_id)
    if lot is None:
        raise HTTPException(404, "Lot not found")
    return lot


def _apply_check(
    engine: Engine, lot: repo.LotRecord, *, elapsed_hours: float, temperature_c: float | None, checked_at: datetime
) -> repo.LotRecord:
    """Run one check on an existing lot: compute, persist, maybe alert."""
    crop = shelf_life.load_crops()[lot.crop_code]
    prev_status = Status(lot.status)

    temp_c, temp_source, freshness_used, remaining, new_status = _compute_check(
        crop, lot.storage_mode, lot.lat, lot.lng, temperature_c, lot.freshness_used, elapsed_hours
    )
    spoil_eta = checked_at + timedelta(hours=remaining)

    # The lot update, its check row and any alert commit together or not at
    # all, so a failure can never leave a new status with no history or no alert.
    with engine.begin() as conn:
        updated = repo.update_lot_after_check(
            conn,
            lot.id,
            lot.farmer_id,
            freshness_used=freshness_used,
            remaining_hours=remaining,
            spoil_eta=spoil_eta,
            status=new_status.value,
            last_checked_at=checked_at,
        )
        repo.insert_check(
            conn,
            lot_id=lot.id,
            temperature_c=temp_c,
            temp_source=temp_source,
            elapsed_hours=elapsed_hours,
            freshness_used=freshness_used,
            remaining_hours=remaining,
            status=new_status.value,
        )
        alert = _maybe_alert(conn, prev_status, updated)
    _notify(alert)  # only after the commit
    return updated


def run_check(engine: Engine, *, now: datetime) -> dict:
    """Run the engine over every open lot. Same job the scheduler calls.

    Logs one line: `checked=N at_risk=M spoiled=K`.
    """
    checked = at_risk = spoiled = 0
    for lot in repo.list_active_lots(engine):
        try:
            elapsed = shelf_life.elapsed_hours_since_last_check(lot.harvested_at, lot.last_checked_at, now)
            updated = _apply_check(engine, lot, elapsed_hours=elapsed, temperature_c=None, checked_at=now)
        except Exception:
            logger.exception("check failed for lot %s; continuing with the next lot", lot.id)
            continue
        checked += 1
        if updated.status == Status.AT_RISK.value:
            at_risk += 1
        elif updated.status == Status.SPOILED.value:
            spoiled += 1
    logger.info("checked=%d at_risk=%d spoiled=%d", checked, at_risk, spoiled)
    return {"checked": checked, "at_risk": at_risk, "spoiled": spoiled}


def simulate(
    engine: Engine,
    farmer_id: str,
    *,
    hours: float,
    temperature_c: float | None,
    lot_id: str | None,
    now: datetime,
) -> list[repo.LotRecord]:
    """Demo button: charge `hours` of ageing to the current farmer's open lots right now.

    The check is stamped with the real `now`, never a future time, so the
    next real check (scheduler, POST /check, check-on-read) carries on from
    here normally. SOLD and SPOILED lots are returned unchanged: the engine
    never touches them.

    With no `lot_id` and no open lots, this deliberately returns an empty
    list rather than an error: "nothing to simulate" isn't a failure.
    """
    if lot_id is not None:
        lot = repo.get_lot(engine, lot_id, farmer_id)
        if lot is None:
            raise HTTPException(404, "Lot not found")
        lots = [lot]
    else:
        lots = repo.list_lots(engine, farmer_id)

    updated_lots = []
    for lot in lots:
        if lot.status in (Status.SOLD.value, Status.SPOILED.value):
            if lot_id is not None:
                updated_lots.append(lot)
            continue
        updated_lots.append(
            _apply_check(engine, lot, elapsed_hours=hours, temperature_c=temperature_c, checked_at=now)
        )
    return updated_lots


def _run_check_if_stale(engine: Engine, now: datetime) -> None:
    """Check-on-read safety net: a sleeping host can skip scheduler runs, so
    GET /rescue/lots and GET /rescue/alerts run the check themselves if any
    open lot's last check is older than CR_CHECK_INTERVAL_HOURS. (The oldest,
    not the newest: one freshly registered lot must not hide an overdue one.)
    """
    lots = repo.list_active_lots(engine)
    if not lots:
        return
    oldest = min(lot.last_checked_at for lot in lots)
    if now - oldest > timedelta(hours=settings.check_interval_hours):
        run_check(engine, now=now)


def list_alerts(engine: Engine, farmer_id: str, unread_only: bool) -> list[repo.AlertRecord]:
    """Run overdue checks, then return the farmer's alerts with the unread filter."""
    _run_check_if_stale(engine, datetime.now(timezone.utc))
    return repo.list_alerts(engine, farmer_id, unread_only=unread_only)


def mark_alert_read(engine: Engine, farmer_id: str, alert_id: str) -> repo.AlertRecord:
    """Stamp an owned alert as read now, raising HTTP 404 if unavailable."""
    alert = repo.mark_alert_read(engine, alert_id, farmer_id, read_at=datetime.now(timezone.utc))
    if alert is None:
        raise HTTPException(404, "Alert not found")
    return alert
