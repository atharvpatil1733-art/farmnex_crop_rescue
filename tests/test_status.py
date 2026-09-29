import random

import pytest

from crop_rescue.core.shelf_life import (
    advance_freshness,
    crop_life_hours,
    effective_temp_c,
    load_crops,
    remaining_hours,
)
from crop_rescue.core.status import Status, should_alert, status_for

ALERT_H = 48.0
INTERVAL_H = 12.0
Q10 = 2.0


def test_status_thresholds():
    """Verify FRESH, AT_RISK, and SPOILED boundaries for the default alert window."""
    assert status_for(61, ALERT_H, INTERVAL_H) == Status.FRESH
    assert status_for(60, ALERT_H, INTERVAL_H) == Status.AT_RISK
    assert status_for(0.1, ALERT_H, INTERVAL_H) == Status.AT_RISK
    assert status_for(0, ALERT_H, INTERVAL_H) == Status.SPOILED


def test_alert_fires_once():
    """Verify alerts on entry to AT_RISK while suppressing repeats and SOLD transitions."""
    assert should_alert(Status.FRESH, Status.AT_RISK) is True
    assert should_alert(None, Status.AT_RISK) is True  # registered already at risk
    assert should_alert(Status.AT_RISK, Status.AT_RISK) is False  # no duplicate
    assert should_alert(Status.FRESH, Status.FRESH) is False
    assert should_alert(Status.AT_RISK, Status.SPOILED) is False
    assert should_alert(Status.SOLD, Status.AT_RISK) is False


def _first_alert_remaining(code, temp_c, storage_mode, check_gaps):
    """Run a lot through checks; return remaining hours when the alert first fires."""
    crop = load_crops()[code]
    life = crop_life_hours(crop, effective_temp_c(crop, storage_mode, temp_c), Q10)

    used = 0.0
    prev = None
    remaining = remaining_hours(used, life)
    status = status_for(remaining, ALERT_H, INTERVAL_H)
    if should_alert(prev, status):
        return remaining, life
    for gap in check_gaps:
        prev = status
        used = advance_freshness(used, gap, life)
        remaining = remaining_hours(used, life)
        status = status_for(remaining, ALERT_H, INTERVAL_H)
        if should_alert(prev, status):
            return remaining, life
        if status == Status.SPOILED:
            break
    raise AssertionError(f"{code} at {temp_c} °C spoiled without an alert")


TEMPS = [t / 2 for t in range(-10, 91)]  # -5 °C to 45 °C in 0.5 °C steps


@pytest.mark.parametrize("storage_mode", ["ambient", "cold"])
@pytest.mark.parametrize("code", sorted(load_crops()))
def test_first_alert_gives_at_least_48h_notice(code, storage_mode):
    """Checks every 12 h at a constant temperature.

    If the lot starts with more than 60 h of life, the first AT_RISK alert
    always has >= 48 h left. If it starts with 60 h or less (e.g. spinach on
    a hot day) the alert fires at registration, the earliest possible moment.
    """
    every_12h = [INTERVAL_H] * 200
    for temp_c in TEMPS:
        remaining, life = _first_alert_remaining(code, temp_c, storage_mode, every_12h)
        if life > ALERT_H + INTERVAL_H:
            assert remaining >= ALERT_H, (code, temp_c, remaining)
        else:
            assert remaining == pytest.approx(life), (code, temp_c)


@pytest.mark.parametrize("code", sorted(load_crops()))
def test_extra_checks_between_scheduler_runs_keep_the_48h_notice(code):
    """Check-on-read adds checks between scheduler runs; gaps are never > 12 h."""
    rng = random.Random(2026)
    for temp_c in TEMPS:
        gaps = [rng.uniform(0.5, INTERVAL_H) for _ in range(2000)]
        remaining, life = _first_alert_remaining(code, temp_c, "ambient", gaps)
        if life > ALERT_H + INTERVAL_H:
            assert remaining >= ALERT_H, (code, temp_c, remaining)


def test_heatwave_between_checks_shrinks_notice_but_still_alerts():
    """Known limit: the 48 h guarantee assumes the temperature holds between checks."""
    tomato = load_crops()["tomato"]
    life_20 = crop_life_hours(tomato, 20.0, Q10)
    life_40 = crop_life_hours(tomato, 40.0, Q10)

    used = 1 - 62 / life_20  # 62 h left at 20 °C
    prev = status_for(remaining_hours(used, life_20), ALERT_H, INTERVAL_H)
    assert prev == Status.FRESH

    used = advance_freshness(used, INTERVAL_H, life_40)  # 12 h heatwave at 40 °C
    remaining = remaining_hours(used, life_40)
    status = status_for(remaining, ALERT_H, INTERVAL_H)

    assert should_alert(prev, status)
    assert 0 < remaining < ALERT_H
