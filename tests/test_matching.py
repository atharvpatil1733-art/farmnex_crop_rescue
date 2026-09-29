import pytest

from crop_rescue.core.matching import (
    BuyerOffer,
    LotForMatching,
    find_matches,
    haversine_km,
    net_price_per_kg,
    qty_matched,
    road_km,
    travel_hours,
)

RADIUS_KM = 50.0
ROAD_FACTOR = 1.3
AVG_SPEED_KMPH = 35.0
LOADING_HOURS = 2.0
TRANSPORT_RS_PER_KM = 25.0
TOP_N = 3

# A tomato lot near Pune, 40 h left, floor price Rs 10/kg.
LOT = LotForMatching(
    crop_code="tomato",
    quantity_kg=500,
    lat=18.5204,
    lng=73.8567,
    floor_price_per_kg=10.0,
    remaining_hours=40.0,
)


def buyer(buyer_id, lat, lng, price=20.0, max_qty=300, reliability=0.9, crop="tomato"):
    return BuyerOffer(
        buyer_id=buyer_id,
        buyer_name=f"Demo Buyer {buyer_id}",
        crop_code=crop,
        price_per_kg=price,
        max_qty_kg=max_qty,
        lat=lat,
        lng=lng,
        reliability=reliability,
    )


def match(**kwargs):
    kwargs.setdefault("radius_km", RADIUS_KM)
    kwargs.setdefault("road_factor", ROAD_FACTOR)
    kwargs.setdefault("avg_speed_kmph", AVG_SPEED_KMPH)
    kwargs.setdefault("loading_hours", LOADING_HOURS)
    kwargs.setdefault("transport_rs_per_km", TRANSPORT_RS_PER_KM)
    kwargs.setdefault("top_n", TOP_N)
    return find_matches(LOT, kwargs.pop("candidates"), **kwargs)


# --- component functions -----------------------------------------------


def test_haversine_same_point_is_zero():
    assert haversine_km(18.5, 73.8, 18.5, 73.8) == pytest.approx(0.0)


def test_haversine_known_distance():
    # Pune (18.5204, 73.8567) to Pimpri-Chinchwad (18.6298, 73.7997): ~13.6 km
    assert haversine_km(18.5204, 73.8567, 18.6298, 73.7997) == pytest.approx(13.6, abs=0.2)


def test_road_km_applies_factor():
    assert road_km(10.0, 1.3) == pytest.approx(13.0)


def test_travel_hours_adds_loading():
    assert travel_hours(35.0, 35.0, 2.0) == pytest.approx(3.0)


def test_travel_hours_rejects_zero_speed():
    with pytest.raises(ValueError):
        travel_hours(10.0, 0.0, 2.0)


def test_qty_matched_is_the_smaller_of_lot_and_buyer():
    assert qty_matched(500, 300) == 300
    assert qty_matched(200, 300) == 200


def test_net_price_subtracts_transport_per_kg():
    assert net_price_per_kg(20.0, 12.0, 25.0, 300.0) == pytest.approx(19.0)


def test_net_price_rejects_non_positive_qty():
    with pytest.raises(ValueError):
        net_price_per_kg(20.0, 12.0, 25.0, 0.0)


# --- find_matches: filters ----------------------------------------------


def test_buyer_beyond_radius_is_excluded():
    # ~0.11 deg lat ~= 12 km; push far enough that road distance > 50 km.
    far = buyer("far", 19.0, 73.8567)  # ~53 km straight-line * 1.3 road factor
    results = match(candidates=[far])
    assert results == []


def test_buyer_within_radius_is_included():
    near = buyer("near", 18.55, 73.86)
    results = match(candidates=[near])
    assert len(results) == 1
    assert results[0].buyer_id == "near"


def test_too_slow_buyer_is_excluded():
    # Close by, but the lot has almost no time left.
    tight_lot = LotForMatching("tomato", 500, 18.5204, 73.8567, 10.0, remaining_hours=2.0)
    nearby = buyer("slow", 18.55, 73.86)
    results = find_matches(
        tight_lot,
        [nearby],
        radius_km=RADIUS_KM,
        road_factor=ROAD_FACTOR,
        avg_speed_kmph=AVG_SPEED_KMPH,
        loading_hours=LOADING_HOURS,
        transport_rs_per_km=TRANSPORT_RS_PER_KM,
        top_n=TOP_N,
    )
    assert results == []


def test_below_floor_buyer_is_excluded():
    cheap = buyer("cheap", 18.55, 73.86, price=5.0)  # net price will be < floor (10.0)
    results = match(candidates=[cheap])
    assert results == []


def test_different_crop_is_excluded():
    wrong_crop = buyer("wrong", 18.55, 73.86, crop="spinach")
    results = match(candidates=[wrong_crop])
    assert results == []


# --- find_matches: scoring and ordering ----------------------------------


def test_ordering_follows_score():
    great = buyer("great", 18.53, 73.86, price=25.0, reliability=1.0)
    okay = buyer("okay", 18.60, 73.90, price=18.0, reliability=0.7)
    poor = buyer("poor", 18.65, 73.95, price=15.0, reliability=0.5)
    results = match(candidates=[poor, great, okay])  # shuffled input order
    assert [m.buyer_id for m in results] == ["great", "okay", "poor"]
    assert results[0].score >= results[1].score >= results[2].score


def test_top_n_limits_result_count():
    buyers = [buyer(f"b{i}", 18.52 + i * 0.01, 73.86, price=20.0 - i) for i in range(5)]
    results = match(candidates=buyers, top_n=3)
    assert len(results) == 3


def test_top_n_keeps_the_best_ones():
    buyers = [buyer(f"b{i}", 18.52 + i * 0.01, 73.86, price=10.0 + i) for i in range(5)]
    results = match(candidates=buyers, top_n=2)
    # Higher price -> higher net price -> higher score (other components similar); best two win.
    assert {m.buyer_id for m in results} == {"b3", "b4"}


# --- find_matches: empty and edge cases ----------------------------------


def test_no_candidates_returns_empty_list():
    assert match(candidates=[]) == []


def test_all_candidates_filtered_out_returns_empty_list():
    all_too_far = [buyer("far1", 19.5, 74.5), buyer("far2", 20.0, 75.0)]
    assert match(candidates=all_too_far) == []


def test_equal_candidates_do_not_raise_and_score_equally():
    identical = [buyer("x", 18.55, 73.86), buyer("y", 18.55, 73.86)]
    results = match(candidates=identical)
    assert len(results) == 2
    assert results[0].score == pytest.approx(results[1].score)


# --- reason string --------------------------------------------------------


def test_reason_is_built_from_real_numbers():
    near = buyer("near", 18.55, 73.86, price=20.0)
    results = match(candidates=[near])
    m = results[0]
    assert f"{m.net_price_per_kg:.1f}" in m.reason
    assert f"{m.distance_km:.0f}" in m.reason
    remaining_after_travel = LOT.remaining_hours - m.travel_hours
    assert f"{remaining_after_travel:.0f}" in m.reason
    assert "₹" in m.reason and "km" in m.reason and "h to spare" in m.reason


def test_reason_differs_for_different_buyers():
    near = buyer("near", 18.53, 73.86, price=25.0)
    farther = buyer("farther", 18.65, 73.95, price=15.0)
    results = match(candidates=[near, farther])
    reasons = {m.buyer_id: m.reason for m in results}
    assert reasons["near"] != reasons["farther"]
