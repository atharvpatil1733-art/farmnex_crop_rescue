"""Lot status rules and the one-time rescue alert.

    remaining <= 0                              -> SPOILED
    remaining <= alert_hours + interval_hours   -> AT_RISK   (48 + 12 = 60 by default)
    otherwise                                   -> FRESH

Why 48 + 12: checks run every 12 hours, so a lot at 61 h now is at 49 h at the
next check. Alerting at 60 h or less guarantees at least 48 hours of notice,
as long as the temperature holds between checks. A sudden heatwave can eat
freshness faster; the next check still alerts, just with less notice.
SOLD is set only by the API, never here.
"""

from __future__ import annotations

from enum import Enum


class Status(str, Enum):
    FRESH = "FRESH"
    AT_RISK = "AT_RISK"
    SPOILED = "SPOILED"
    SOLD = "SOLD"


def status_for(remaining_hours: float, alert_hours: float, interval_hours: float) -> Status:
    """Status of a lot with `remaining_hours` left.

    >>> status_for(61, 48, 12).value
    'FRESH'
    >>> status_for(60, 48, 12).value
    'AT_RISK'
    >>> status_for(0, 48, 12).value
    'SPOILED'
    """
    if remaining_hours <= 0:
        return Status.SPOILED
    if remaining_hours <= alert_hours + interval_hours:
        return Status.AT_RISK
    return Status.FRESH


def should_alert(prev_status: Status | None, new_status: Status) -> bool:
    """True only when a lot enters AT_RISK, so the alert fires once.

    `prev_status` is None for a lot being registered right now.

    >>> should_alert(Status.FRESH, Status.AT_RISK)
    True
    >>> should_alert(Status.AT_RISK, Status.AT_RISK)   # second check: no duplicate
    False
    """
    return new_status == Status.AT_RISK and prev_status in (None, Status.FRESH)
