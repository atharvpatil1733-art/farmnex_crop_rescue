"""Shelf life at a temperature (Q10 rule) and freshness accumulation.

In one breath: each crop has a sourced shelf life at its ideal temperature
(USDA Agriculture Handbook 66). Every 10 °C hotter divides it by Q10
(2.0 by default, an assumption). We add up how much freshness each hour eats.

Everything here is a pure function: config values come in as arguments,
and nothing reads the clock, the database or the environment.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

CROPS_JSON = Path(__file__).resolve().parent.parent / "data" / "crops.json"
EXPECTED_CROP_COUNT = 8


@dataclass(frozen=True)
class Crop:
    """One row of crops.json. The numbers are never edited in code."""

    code: str
    name_en: str
    name_mr: str
    ref_temp_c: float
    ref_life_hours: float
    table_row: str
    storage_life_in_table: str
    source: str
    note: str | None = None


@lru_cache(maxsize=1)
def load_crops() -> dict[str, Crop]:
    """Read the 8 sourced crops from crops.json, keyed by code.

    >>> load_crops()["tomato"].ref_life_hours
    168.0
    """
    raw = json.loads(CROPS_JSON.read_text(encoding="utf-8"))
    crops: dict[str, Crop] = {}
    for row in raw["crops"]:
        crops[row["code"]] = Crop(
            code=row["code"],
            name_en=row["name_en"],
            name_mr=row["name_mr"],
            ref_temp_c=float(row["ref_temp_c"]),
            ref_life_hours=float(row["ref_life_hours"]),
            table_row=row["table_row"],
            storage_life_in_table=row["storage_life_in_table"],
            source=row["source"],
            note=row.get("note"),
        )
    if len(crops) != EXPECTED_CROP_COUNT:
        raise ValueError(f"crops.json must hold exactly {EXPECTED_CROP_COUNT} crops, got {len(crops)}")
    return crops


def life_hours(ref_life_hours: float, ref_temp_c: float, temp_c: float, q10: float) -> float:
    """Total shelf life (hours) of a fresh lot kept at `temp_c`.

    Q10 rule: every 10 °C above the reference temperature divides life by `q10`.
    At or below the reference temperature we return the handbook value;
    we never extend life beyond it.

    >>> life_hours(168, 17.0, 27.0, 2.0)   # tomato, 10 °C hotter -> half
    84.0
    >>> life_hours(168, 17.0, 5.0, 2.0)    # colder than reference -> capped
    168
    """
    if ref_life_hours <= 0:
        raise ValueError("ref_life_hours must be positive")
    if q10 <= 1:
        raise ValueError("q10 must be greater than 1")
    if temp_c <= ref_temp_c:
        return ref_life_hours
    return ref_life_hours / q10 ** ((temp_c - ref_temp_c) / 10)


def crop_life_hours(crop: Crop, temp_c: float, q10: float) -> float:
    """`life_hours` for a crop from crops.json.

    >>> round(crop_life_hours(load_crops()["spinach"], 30.0, 2.0), 1)
    30.0
    """
    return life_hours(crop.ref_life_hours, crop.ref_temp_c, temp_c, q10)


def effective_temp_c(crop: Crop, storage_mode: str, temp_c: float) -> float:
    """Temperature the lot actually experiences.

    In `cold` storage the lot sits at the crop's reference temperature;
    in `ambient` storage it feels the measured air temperature.

    >>> effective_temp_c(load_crops()["tomato"], "cold", 34.0)
    17.0
    >>> effective_temp_c(load_crops()["tomato"], "ambient", 34.0)
    34.0
    """
    if storage_mode == "cold":
        return crop.ref_temp_c
    if storage_mode == "ambient":
        return temp_c
    raise ValueError(f"storage_mode must be 'ambient' or 'cold', got {storage_mode!r}")


def elapsed_hours_since_last_check(
    harvested_at: datetime, last_checked_at: datetime | None, now: datetime
) -> float:
    """Hours of freshness to charge at this check.

    A new lot has never been checked, so its first check counts from
    `harvested_at` (entered by the farmer), not from registration time:
    produce starts ageing when it leaves the field.

    >>> from datetime import timezone
    >>> harvest = datetime(2026, 9, 28, 6, 0, tzinfo=timezone.utc)
    >>> now = datetime(2026, 9, 29, 18, 0, tzinfo=timezone.utc)
    >>> elapsed_hours_since_last_check(harvest, None, now)   # first check
    36.0
    >>> elapsed_hours_since_last_check(harvest, datetime(2026, 9, 29, 6, 0, tzinfo=timezone.utc), now)
    12.0
    """
    for value in (harvested_at, last_checked_at, now):
        if value is not None and value.tzinfo is None:
            raise ValueError("datetimes must be timezone-aware (UTC)")
    if harvested_at > now:
        raise ValueError("harvested_at is in the future")
    if last_checked_at is not None and last_checked_at > now:
        raise ValueError("last_checked_at is in the future")

    start = harvested_at if last_checked_at is None else last_checked_at
    seconds = (now - start).total_seconds()
    return max(0.0, seconds / 3600)


def advance_freshness(
    freshness_used: float, elapsed_hours: float, life_hours_during_interval: float
) -> float:
    """Add the freshness eaten during one interval. 0 = just harvested, 1 = spoiled.

    Accumulating (instead of subtracting hours) lets a hot afternoon eat
    freshness faster than a cool night.

    >>> advance_freshness(0.0, 12, 48.0)   # 12 h out of a 48 h life
    0.25
    >>> advance_freshness(0.9, 12, 48.0)   # capped at 1.0
    1.0
    """
    if elapsed_hours < 0:
        raise ValueError("elapsed_hours must not be negative")
    used = freshness_used + elapsed_hours / life_hours_during_interval
    return min(1.0, used)


def remaining_hours(freshness_used: float, life_hours_now: float) -> float:
    """Hours left before spoilage if the current temperature holds.

    >>> remaining_hours(0.25, 48.0)
    36.0
    >>> remaining_hours(1.0, 48.0)
    0.0
    """
    return max(0.0, (1.0 - freshness_used) * life_hours_now)
