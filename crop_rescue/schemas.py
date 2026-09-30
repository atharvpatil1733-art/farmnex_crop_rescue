"""Request and response models. Every request model carries a
`json_schema_extra` example so "Try it out" works in `/docs` in one click.

Times are ISO 8601 UTC. Money is Rs per kg. Hours are rounded to one
decimal place in responses.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


def _round1(value: float | None) -> float | None:
    """Round a value to one decimal place, preserving None for unknown values."""
    return None if value is None else round(value, 1)


class CropOut(BaseModel):
    """One crop from crops.json, plus its life at a few sample temperatures."""

    code: str
    name_en: str
    name_mr: str
    ref_temp_c: float
    ref_life_hours: float
    life_hours_at_25c: float
    life_hours_at_30c: float
    life_hours_at_35c: float
    source: str
    note: str | None = None


class CropsOut(BaseModel):
    """All 8 crops, labelled with the Q10 assumption used to compute them."""

    q10: float
    q10_note: str = (
        "Q10 = 2 (assumption). The rule of thumb for produce is 2-3; "
        "we use the lower end (a higher Q10 would alert earlier)."
    )
    crops: list[CropOut]


class LotCreate(BaseModel):
    """Register a lot for the current farmer. No farmer_id: it comes from login."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "crop_code": "tomato",
                "quantity_kg": 500,
                "harvested_at": "2026-09-28T06:00:00Z",
                "lat": 18.5204,
                "lng": 73.8567,
                "storage_mode": "ambient",
                "floor_price_per_kg": 10,
                "temperature_c": 30,
            }
        }
    )

    crop_code: str = Field(description="One of the 8 codes from GET /rescue/crops")
    quantity_kg: float = Field(gt=0)
    harvested_at: datetime = Field(description="When the crop left the field, not when you register it")
    lat: float
    lng: float
    storage_mode: Literal["ambient", "cold"] = "ambient"
    floor_price_per_kg: float = Field(default=0, ge=0, description="Buyers below this net price are excluded")
    temperature_c: float | None = Field(
        default=None, description="Omit to use CR_DEFAULT_TEMP_C (or Open-Meteo, if enabled)"
    )


class CheckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    checked_at: datetime
    temperature_c: float
    temp_source: str
    elapsed_hours: float
    freshness_used: float
    remaining_hours: float
    status: str

    @field_serializer("elapsed_hours", "remaining_hours")
    def _round_hours(self, value: float) -> float:
        """Serialize elapsed and remaining hours to one decimal place."""
        return round(value, 1)


class LotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    crop_code: str
    quantity_kg: float
    harvested_at: datetime
    lat: float
    lng: float
    storage_mode: str
    floor_price_per_kg: float
    temperature_c: float | None
    freshness_used: float
    remaining_hours: float | None
    spoil_eta: datetime | None
    status: str
    last_checked_at: datetime
    created_at: datetime

    @field_serializer("remaining_hours")
    def _round_remaining(self, value: float | None) -> float | None:
        """Serialize remaining hours to one decimal place, preserving None."""
        return _round1(value)


class LotDetailOut(LotOut):
    """A lot plus its full check history (newest first)."""

    checks: list[CheckOut]


class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    buyer_id: str
    buyer_name: str
    net_price_per_kg: float
    distance_km: float
    travel_hours: float
    qty_kg: float
    score: float
    reason: str

    @field_serializer("travel_hours")
    def _round_travel_hours(self, value: float) -> float:
        """Serialize estimated travel hours to one decimal place."""
        return round(value, 1)


class SimulateRequest(BaseModel):
    """Demo button: fast-forward the clock without waiting."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"hours": 24, "temperature_c": 34, "lot_id": None}}
    )

    hours: float = Field(gt=0, le=720, description="At most 720 (30 days)")
    temperature_c: float | None = Field(default=None, description="Omit to resolve temperature normally")
    lot_id: str | None = Field(default=None, description="Omit to advance every one of your open lots")


class SimulateOut(BaseModel):
    lots: list[LotOut]


class CheckRunOut(BaseModel):
    """Result of running the engine over all open lots once."""

    checked: int
    at_risk: int
    spoiled: int


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    lot_id: str
    kind: str
    title: str
    body: str
    payload: dict | None
    created_at: datetime
    read_at: datetime | None


class HealthOut(BaseModel):
    ok: bool
    crops: int
    db: bool
