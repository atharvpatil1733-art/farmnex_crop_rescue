"""Rescue matching: the top nearby buyers for an at-risk lot.

In one breath: filter buyers to who's close enough and fast enough and pays
above the farmer's floor, score the survivors, then return the best 3, each
with a one-line reason built from the real numbers.

Pure functions only: no DB, no FastAPI, no clock. `cr_buyer_pool` rows come
in as `BuyerOffer` objects; config values come in as arguments.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Score weights from SPEC §5: 0.5 net price + 0.2 time margin + 0.2 reliability + 0.1 qty fit
DEFAULT_WEIGHTS = (0.5, 0.2, 0.2, 0.1)


@dataclass(frozen=True)
class BuyerOffer:
    """One row from the `cr_buyer_pool` view."""

    buyer_id: str
    buyer_name: str
    crop_code: str
    price_per_kg: float
    max_qty_kg: float
    lat: float
    lng: float
    reliability: float  # 0..1


@dataclass(frozen=True)
class LotForMatching:
    """Just the fields matching needs from an at-risk lot."""

    crop_code: str
    quantity_kg: float
    lat: float
    lng: float
    floor_price_per_kg: float
    remaining_hours: float


@dataclass(frozen=True)
class Match:
    """One ranked buyer for a lot, with a judge- and farmer-readable reason."""

    buyer_id: str
    buyer_name: str
    net_price_per_kg: float
    distance_km: float
    travel_hours: float
    qty_kg: float
    score: float
    reason: str


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two lat/lng points, in kilometres.

    >>> round(haversine_km(18.5204, 73.8567, 18.5204, 73.8567), 2)  # same point
    0.0
    >>> round(haversine_km(18.5204, 73.8567, 18.6298, 73.7997), 1)  # Pune -> Pimpri, ~14 km
    13.6
    """
    earth_radius_km = 6371.0
    lat1_r, lng1_r, lat2_r, lng2_r = map(math.radians, (lat1, lng1, lat2, lng2))
    dlat = lat2_r - lat1_r
    dlng = lng2_r - lng1_r
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return earth_radius_km * c


def road_km(straight_km: float, road_factor: float) -> float:
    """Approximate road distance from straight-line distance. No maps API.

    >>> road_km(10.0, 1.3)
    13.0
    """
    return straight_km * road_factor


def travel_hours(road_distance_km: float, avg_speed_kmph: float, loading_hours: float) -> float:
    """Hours from "go" to the buyer having the produce in hand.

    >>> travel_hours(35.0, 35.0, 2.0)
    3.0
    """
    if avg_speed_kmph <= 0:
        raise ValueError("avg_speed_kmph must be positive")
    return road_distance_km / avg_speed_kmph + loading_hours


def qty_matched(lot_qty_kg: float, buyer_max_qty_kg: float) -> float:
    """How much of the lot this buyer can actually take.

    >>> qty_matched(500, 300)
    300
    >>> qty_matched(200, 300)
    200
    """
    return min(lot_qty_kg, buyer_max_qty_kg)


def net_price_per_kg(
    price_per_kg: float, road_distance_km: float, transport_rs_per_km: float, qty_kg: float
) -> float:
    """What the farmer nets per kg after paying for transport.

    >>> net_price_per_kg(20.0, 12.0, 25.0, 300.0)
    19.0
    """
    if qty_kg <= 0:
        raise ValueError("qty_kg must be positive")
    return price_per_kg - (road_distance_km * transport_rs_per_km) / qty_kg


def _normalize(values: list[float]) -> list[float]:
    """Min-max normalise to [0, 1]. All-equal values normalise to 1.0 each."""
    lo, hi = min(values), max(values)
    if hi == lo:
        return [1.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def _reason(net_price: float, distance_km: float, remaining_after_travel: float) -> str:
    """One readable line built from a match's own numbers.

    >>> _reason(18.4, 12.0, 30.0)
    '₹18.4/kg after transport · 12 km · 30 h to spare'
    """
    return f"₹{net_price:.1f}/kg after transport · {distance_km:.0f} km · {remaining_after_travel:.0f} h to spare"


def find_matches(
    lot: LotForMatching,
    candidates: list[BuyerOffer],
    *,
    radius_km: float,
    road_factor: float,
    avg_speed_kmph: float,
    loading_hours: float,
    transport_rs_per_km: float,
    top_n: int,
    weights: tuple[float, float, float, float] = DEFAULT_WEIGHTS,
) -> list[Match]:
    """Filter, score and rank buyers for an at-risk lot. Pipeline: filter, score, take top N.

    Filters (in order): same crop, within `radius_km` of road distance, fast
    enough to beat `lot.remaining_hours`, and paying at least
    `lot.floor_price_per_kg` net of transport. Zero survivors is a valid
    result: an empty list, never an error.

    >>> lot = LotForMatching("tomato", 500, 18.5204, 73.8567, 10.0, 40.0)
    >>> near = BuyerOffer("b1", "Demo Buyer 1", "tomato", 20.0, 300, 18.5304, 73.8467, 0.9)
    >>> far = BuyerOffer("b2", "Demo Buyer 2 (too far)", "tomato", 25.0, 300, 20.0, 76.0, 0.9)
    >>> matches = find_matches(lot, [near, far], radius_km=50, road_factor=1.3,
    ...     avg_speed_kmph=35, loading_hours=2, transport_rs_per_km=25, top_n=3)
    >>> [m.buyer_id for m in matches]
    ['b1']
    """
    survivors: list[dict] = []
    for buyer in candidates:
        if buyer.crop_code != lot.crop_code:
            continue

        distance_km = haversine_km(lot.lat, lot.lng, buyer.lat, buyer.lng)
        rkm = road_km(distance_km, road_factor)
        if rkm > radius_km:
            continue

        travel_h = travel_hours(rkm, avg_speed_kmph, loading_hours)
        if travel_h >= lot.remaining_hours:
            continue

        qty_kg = qty_matched(lot.quantity_kg, buyer.max_qty_kg)
        net_price = net_price_per_kg(buyer.price_per_kg, rkm, transport_rs_per_km, qty_kg)
        if net_price < lot.floor_price_per_kg:
            continue

        survivors.append(
            {
                "buyer": buyer,
                "distance_km": distance_km,
                "travel_hours": travel_h,
                "qty_kg": qty_kg,
                "net_price": net_price,
                "time_margin": (lot.remaining_hours - travel_h) / lot.remaining_hours,
                "qty_fit": qty_kg / lot.quantity_kg,
            }
        )

    if not survivors:
        return []

    w_price, w_time, w_reliability, w_qty = weights
    norm_price = _normalize([s["net_price"] for s in survivors])
    norm_time = _normalize([s["time_margin"] for s in survivors])
    norm_reliability = _normalize([s["buyer"].reliability for s in survivors])
    norm_qty = _normalize([s["qty_fit"] for s in survivors])

    matches = []
    for s, np_, nt, nr, nq in zip(survivors, norm_price, norm_time, norm_reliability, norm_qty):
        score = w_price * np_ + w_time * nt + w_reliability * nr + w_qty * nq
        remaining_after_travel = lot.remaining_hours - s["travel_hours"]
        matches.append(
            Match(
                buyer_id=s["buyer"].buyer_id,
                buyer_name=s["buyer"].buyer_name,
                net_price_per_kg=s["net_price"],
                distance_km=s["distance_km"],
                travel_hours=s["travel_hours"],
                qty_kg=s["qty_kg"],
                score=score,
                reason=_reason(s["net_price"], s["distance_km"], remaining_after_travel),
            )
        )

    matches.sort(key=lambda m: m.score, reverse=True)
    return matches[:top_n]
