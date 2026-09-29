from datetime import datetime, timedelta, timezone

import pytest

from crop_rescue.core.shelf_life import (
    advance_freshness,
    crop_life_hours,
    effective_temp_c,
    elapsed_hours_since_last_check,
    life_hours,
    load_crops,
    remaining_hours,
)

Q10 = 2.0


# Sanity table from the shelf-life-engine skill. Must match to 0.1 h.
@pytest.mark.parametrize(
    ("code", "temp_c", "expected_hours"),
    [
        ("tomato", 25.0, 96.5),
        ("tomato", 30.0, 68.2),
        ("spinach", 25.0, 42.4),
        ("spinach", 30.0, 30.0),
        ("cauliflower", 25.0, 89.1),
        ("cauliflower", 30.0, 63.0),
    ],
)
def test_sanity_table(code, temp_c, expected_hours):
    """Verify that Q10 = 2 reproduces the reference examples within 0.1 hours."""
    crop = load_crops()[code]
    assert abs(crop_life_hours(crop, temp_c, Q10) - expected_hours) < 0.1


def test_crops_json_matches_spec_table():
    """Verify the exact eight crops and their sourced reference temperatures and lives."""
    expected = {
        "tomato": (17.0, 168),
        "spinach": (0.0, 240),
        "okra": (8.6, 168),
        "brinjal": (10.0, 168),
        "cauliflower": (0.0, 504),
        "grapes": (-0.3, 336),
        "capsicum": (10.0, 336),
        "cucumber": (11.4, 240),
    }
    crops = load_crops()
    assert len(crops) == 8
    for code, (ref_temp_c, ref_life_hours) in expected.items():
        assert crops[code].ref_temp_c == ref_temp_c
        assert crops[code].ref_life_hours == ref_life_hours


def test_every_crop_cites_the_source():
    """Require every crop record to cite USDA Agriculture Handbook 66."""
    for crop in load_crops().values():
        assert "USDA AH-66" in crop.source


@pytest.mark.parametrize("code", sorted(load_crops()))
def test_cold_is_capped_at_handbook_value(code):
    """Verify that cooling never extends life beyond the crop's handbook value."""
    crop = load_crops()[code]
    assert crop_life_hours(crop, crop.ref_temp_c, Q10) == crop.ref_life_hours
    assert crop_life_hours(crop, crop.ref_temp_c - 15, Q10) == crop.ref_life_hours


def test_ten_degrees_hotter_halves_life():
    """Verify that each 10-degree rise halves life when Q10 is assumed to be 2."""
    assert life_hours(168, 17.0, 27.0, Q10) == pytest.approx(84.0)
    assert life_hours(168, 17.0, 37.0, Q10) == pytest.approx(42.0)


def test_life_hours_rejects_bad_inputs():
    """Verify that zero reference life and Q10 of 1 raise ValueError."""
    with pytest.raises(ValueError):
        life_hours(0, 17.0, 30.0, Q10)
    with pytest.raises(ValueError):
        life_hours(168, 17.0, 30.0, 1.0)


def test_cold_storage_uses_reference_temperature():
    """Verify cold and ambient temperature selection and reject unknown storage modes."""
    tomato = load_crops()["tomato"]
    assert effective_temp_c(tomato, "cold", 38.0) == 17.0
    assert effective_temp_c(tomato, "ambient", 38.0) == 38.0
    with pytest.raises(ValueError):
        effective_temp_c(tomato, "fridge", 38.0)


def test_hot_interval_uses_more_freshness_than_cool_one():
    """Verify that a hot interval consumes more freshness than continued cool storage."""
    tomato = load_crops()["tomato"]
    life_20 = crop_life_hours(tomato, 20.0, Q10)
    life_35 = crop_life_hours(tomato, 35.0, Q10)

    cool_then_hot = advance_freshness(advance_freshness(0.0, 12, life_20), 12, life_35)
    cool_all_day = advance_freshness(0.0, 24, life_20)

    assert cool_then_hot > cool_all_day


def test_accumulation_at_constant_temp_equals_simple_subtraction():
    """Verify that successive checks consume the same life as total elapsed hours."""
    life = crop_life_hours(load_crops()["tomato"], 30.0, Q10)
    used = 0.0
    for _ in range(3):
        used = advance_freshness(used, 12, life)
    assert remaining_hours(used, life) == pytest.approx(life - 36)


def test_freshness_is_capped_and_remaining_never_negative():
    """Verify that ageing beyond spoilage caps freshness used and leaves zero hours."""
    assert advance_freshness(0.95, 100, 50.0) == 1.0
    assert remaining_hours(1.0, 50.0) == 0.0


def test_negative_elapsed_is_rejected():
    """Verify that ageing by a negative interval raises ValueError."""
    with pytest.raises(ValueError):
        advance_freshness(0.1, -1, 50.0)


NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)


def test_first_check_counts_from_harvest_not_registration():
    """A tomato picked 36 h ago and registered now has already lost 36 h."""
    harvested_at = NOW - timedelta(hours=36)
    life = crop_life_hours(load_crops()["tomato"], 30.0, Q10)

    elapsed = elapsed_hours_since_last_check(harvested_at, None, NOW)
    used = advance_freshness(0.0, elapsed, life)

    assert elapsed == pytest.approx(36.0)
    assert remaining_hours(used, life) == pytest.approx(life - 36)  # ~32.2 h, not ~68.2 h


def test_later_checks_count_from_last_check():
    """Verify that subsequent checks measure elapsed time from the previous check."""
    harvested_at = NOW - timedelta(hours=36)
    last_checked_at = NOW - timedelta(hours=12)
    assert elapsed_hours_since_last_check(harvested_at, last_checked_at, NOW) == pytest.approx(12.0)


def test_harvested_now_charges_nothing():
    """Verify that a lot harvested at the check instant has zero elapsed hours."""
    assert elapsed_hours_since_last_check(NOW, None, NOW) == 0.0


def test_harvest_in_the_future_is_rejected():
    """Verify that a harvest time after the check instant raises ValueError."""
    with pytest.raises(ValueError):
        elapsed_hours_since_last_check(NOW + timedelta(hours=1), None, NOW)


def test_last_checked_in_the_future_is_rejected():
    """Verify that a previous-check timestamp in the future raises ValueError."""
    harvested_at = NOW - timedelta(hours=36)
    with pytest.raises(ValueError):
        elapsed_hours_since_last_check(harvested_at, NOW + timedelta(hours=1), NOW)


def test_naive_datetimes_are_rejected():
    """Verify that harvest timestamps without timezone information raise ValueError."""
    with pytest.raises(ValueError):
        elapsed_hours_since_last_check(datetime(2026, 9, 28), None, NOW)
