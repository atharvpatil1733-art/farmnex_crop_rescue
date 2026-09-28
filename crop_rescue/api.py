"""HTTP only. Every request is validated by `schemas.py` and handed to
`service.py`; nothing here talks to the database directly. No auth here
either: the host wraps this router with its own login check, and the
farmer always comes from `Depends(current_farmer_id)`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from . import db, service
from .config import settings
from .deps import current_farmer_id
from .schemas import (
    AlertOut,
    CheckRunOut,
    CropsOut,
    HealthOut,
    LotCreate,
    LotDetailOut,
    LotOut,
    MatchOut,
    SimulateOut,
    SimulateRequest,
)

router = APIRouter(prefix="/rescue", tags=["crop-rescue"])


@router.get(
    "/health",
    response_model=HealthOut,
    summary="Health check",
    description="Whether the router is mounted, how many crops are loaded, and whether the database is reachable.",
)
def health() -> HealthOut:
    try:
        engine = db.get_engine()
    except RuntimeError:
        engine = None
    return HealthOut(**service.health(engine))


@router.get(
    "/crops",
    response_model=CropsOut,
    summary="List the 8 sourced crops",
    description="Each crop's shelf life at 25/30/35 °C under the Q10 model, with its source and the Q10 assumption.",
)
def list_crops() -> CropsOut:
    return CropsOut(q10=settings.q10, crops=service.list_crops())


@router.post(
    "/lots",
    response_model=LotOut,
    status_code=201,
    summary="Register a harvested lot",
    description="Registers a lot for the current farmer and runs its first freshness check immediately.",
)
def create_lot(body: LotCreate, farmer_id: str = Depends(current_farmer_id)) -> LotOut:
    lot = service.create_lot(
        db.get_engine(),
        farmer_id,
        crop_code=body.crop_code,
        quantity_kg=body.quantity_kg,
        harvested_at=body.harvested_at,
        lat=body.lat,
        lng=body.lng,
        storage_mode=body.storage_mode,
        floor_price_per_kg=body.floor_price_per_kg,
        temperature_c=body.temperature_c,
        now=datetime.now(timezone.utc),
    )
    return LotOut.model_validate(lot)


@router.get(
    "/lots",
    response_model=list[LotOut],
    summary="List your lots",
    description="The current farmer's lots, with status, remaining_hours and spoil_eta kept fresh on read.",
)
def list_lots(farmer_id: str = Depends(current_farmer_id)) -> list[LotOut]:
    lots = service.list_lots(db.get_engine(), farmer_id)
    return [LotOut.model_validate(lot) for lot in lots]


@router.get(
    "/lots/{lot_id}",
    response_model=LotDetailOut,
    summary="Get one lot, with its check history",
    description="One of the current farmer's lots plus every check ever run on it. 404 if it isn't theirs.",
)
def get_lot(lot_id: str, farmer_id: str = Depends(current_farmer_id)) -> LotDetailOut:
    lot, checks = service.get_lot_detail(db.get_engine(), farmer_id, lot_id)
    lot_out = LotOut.model_validate(lot)
    return LotDetailOut(**lot_out.model_dump(), checks=checks)


@router.get(
    "/lots/{lot_id}/matches",
    response_model=list[MatchOut],
    summary="Top nearby buyers for an at-risk lot",
    description="The top CR_TOP_N buyers for this lot. 404 if it isn't yours, 409 if it isn't AT_RISK.",
)
def get_matches(lot_id: str, farmer_id: str = Depends(current_farmer_id)) -> list[MatchOut]:
    matches = service.get_matches(db.get_engine(), farmer_id, lot_id)
    return [MatchOut.model_validate(m) for m in matches]


@router.post(
    "/lots/{lot_id}/sold",
    response_model=LotOut,
    summary="Mark a lot sold",
    description="Marks the lot SOLD, so it stops being checked and alerted on. 404 if it isn't yours.",
)
def mark_sold(lot_id: str, farmer_id: str = Depends(current_farmer_id)) -> LotOut:
    lot = service.mark_sold(db.get_engine(), farmer_id, lot_id)
    return LotOut.model_validate(lot)


@router.post(
    "/check",
    response_model=CheckRunOut,
    summary="Run the freshness engine now",
    description="Runs the same job the scheduler runs, over every open lot for every farmer. Needs no farmer.",
)
def run_check() -> CheckRunOut:
    result = service.run_check(db.get_engine(), now=datetime.now(timezone.utc))
    return CheckRunOut(**result)


@router.post(
    "/simulate",
    response_model=SimulateOut,
    summary="Demo: fast-forward the clock",
    description=(
        "Advances the current farmer's lots (or one lot) by `hours` without waiting, then re-runs the "
        "status rules and alerts. 404 once CR_ENABLE_SIMULATE=false (turn it off after the demo)."
    ),
)
def simulate(body: SimulateRequest, farmer_id: str = Depends(current_farmer_id)) -> SimulateOut:
    if not settings.enable_simulate:
        raise HTTPException(404, "Simulate is disabled (CR_ENABLE_SIMULATE=false)")
    lots = service.simulate(
        db.get_engine(),
        farmer_id,
        hours=body.hours,
        temperature_c=body.temperature_c,
        lot_id=body.lot_id,
    )
    return SimulateOut(lots=[LotOut.model_validate(lot) for lot in lots])


@router.get(
    "/alerts",
    response_model=list[AlertOut],
    summary="List your alerts",
    description="The current farmer's alerts, newest first. Flutter polls this every 30 s on the home screen.",
)
def list_alerts(
    unread_only: bool = Query(False), farmer_id: str = Depends(current_farmer_id)
) -> list[AlertOut]:
    alerts = service.list_alerts(db.get_engine(), farmer_id, unread_only)
    return [AlertOut.model_validate(a) for a in alerts]


@router.post(
    "/alerts/{alert_id}/read",
    response_model=AlertOut,
    summary="Mark an alert read",
    description="Marks one of the current farmer's alerts read. 404 if it isn't theirs.",
)
def mark_alert_read(alert_id: str, farmer_id: str = Depends(current_farmer_id)) -> AlertOut:
    alert = service.mark_alert_read(db.get_engine(), farmer_id, alert_id)
    return AlertOut.model_validate(alert)
