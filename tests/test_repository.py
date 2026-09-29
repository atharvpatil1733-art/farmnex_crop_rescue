"""Repository tests against a real Postgres: CR_TEST_DATABASE_URL only.

Skipped automatically (via the `db` fixture) if CR_TEST_DATABASE_URL isn't
set. Never touches CR_DATABASE_URL, DATABASE_URL or Supabase.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from crop_rescue import repository as repo

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)


def _farmer_id() -> str:
    """Generate a unique synthetic farmer identity for an isolated test."""
    return f"farmer-{uuid.uuid4()}"


def _insert_lot(db, farmer_id: str, **overrides) -> repo.LotRecord:
    """Insert a tomato lot using fixed test values and any requested field overrides."""
    kwargs = dict(
        farmer_id=farmer_id,
        crop_code="tomato",
        quantity_kg=500.0,
        harvested_at=NOW - timedelta(hours=6),
        lat=18.5204,
        lng=73.8567,
        storage_mode="ambient",
        floor_price_per_kg=10.0,
        temperature_c=22.5,
        freshness_used=0.0,
        remaining_hours=68.2,
        spoil_eta=NOW + timedelta(hours=68.2),
        status="FRESH",
        last_checked_at=NOW,
    )
    kwargs.update(overrides)
    return repo.insert_lot(db, **kwargs)


def test_insert_and_get_lot_round_trip(db):
    """Verify that inserting and fetching an owned lot preserves its key fields."""
    farmer_id = _farmer_id()
    created = _insert_lot(db, farmer_id)

    fetched = repo.get_lot(db, created.id, farmer_id)

    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.crop_code == "tomato"
    assert fetched.quantity_kg == pytest.approx(500.0)
    assert fetched.temperature_c == pytest.approx(22.5)
    assert fetched.status == "FRESH"


def test_get_lot_returns_none_for_another_farmer(db):
    """Verify that fetching another farmer's lot returns None."""
    owner = _farmer_id()
    other = _farmer_id()
    created = _insert_lot(db, owner)

    assert repo.get_lot(db, created.id, other) is None


def test_get_lot_returns_none_for_unknown_id(db):
    """Verify that fetching a nonexistent lot UUID returns None."""
    assert repo.get_lot(db, str(uuid.uuid4()), _farmer_id()) is None


def test_list_lots_only_returns_that_farmers_lots(db):
    """Verify that repository lot listings are scoped to the requested farmer."""
    farmer_a = _farmer_id()
    farmer_b = _farmer_id()
    _insert_lot(db, farmer_a)
    _insert_lot(db, farmer_a)
    _insert_lot(db, farmer_b)

    lots = repo.list_lots(db, farmer_a)

    assert len(lots) == 2
    assert all(lot.farmer_id == farmer_a for lot in lots)


def test_list_lots_filters_by_status(db):
    """Verify that the optional status filter selects only matching lots."""
    farmer_id = _farmer_id()
    _insert_lot(db, farmer_id, status="FRESH")
    _insert_lot(db, farmer_id, status="AT_RISK")

    at_risk = repo.list_lots(db, farmer_id, status="AT_RISK")

    assert len(at_risk) == 1
    assert at_risk[0].status == "AT_RISK"


def test_list_active_lots_excludes_sold_and_spoiled(db):
    """Verify that only FRESH and AT_RISK fixtures remain eligible for checking."""
    farmer_id = _farmer_id()
    _insert_lot(db, farmer_id, status="FRESH")
    _insert_lot(db, farmer_id, status="AT_RISK")
    _insert_lot(db, farmer_id, status="SOLD")
    _insert_lot(db, farmer_id, status="SPOILED")

    active = repo.list_active_lots(db)
    active_for_farmer = [lot for lot in active if lot.farmer_id == farmer_id]

    assert {lot.status for lot in active_for_farmer} == {"FRESH", "AT_RISK"}


def test_update_lot_after_check_persists_new_values(db):
    """Verify that a freshness update returns the new status and freshness values."""
    farmer_id = _farmer_id()
    created = _insert_lot(db, farmer_id)

    updated = repo.update_lot_after_check(
        db,
        created.id,
        farmer_id,
        freshness_used=0.5,
        remaining_hours=34.1,
        spoil_eta=NOW + timedelta(hours=34.1),
        status="AT_RISK",
        last_checked_at=NOW + timedelta(hours=12),
    )

    assert updated is not None
    assert updated.status == "AT_RISK"
    assert updated.freshness_used == pytest.approx(0.5)
    assert updated.remaining_hours == pytest.approx(34.1)


def test_update_lot_after_check_returns_none_for_unknown_lot(db):
    """Verify that updating a nonexistent lot returns None."""
    result = repo.update_lot_after_check(
        db,
        str(uuid.uuid4()),
        _farmer_id(),
        freshness_used=0.5,
        remaining_hours=10.0,
        spoil_eta=None,
        status="AT_RISK",
        last_checked_at=NOW,
    )
    assert result is None


def test_mark_lot_sold(db):
    """Verify that marking an owned lot sold returns a record with SOLD status."""
    farmer_id = _farmer_id()
    created = _insert_lot(db, farmer_id)

    sold = repo.mark_lot_sold(db, created.id, farmer_id)

    assert sold is not None
    assert sold.status == "SOLD"


def test_mark_lot_sold_is_ownership_scoped(db):
    """Verify that another farmer cannot change a lot's status to SOLD."""
    owner = _farmer_id()
    other = _farmer_id()
    created = _insert_lot(db, owner)

    assert repo.mark_lot_sold(db, created.id, other) is None
    assert repo.get_lot(db, created.id, owner).status == "FRESH"


def test_insert_check_round_trip(db):
    """Verify that a new check record retains its lot, temperature source, and hours."""
    farmer_id = _farmer_id()
    lot = _insert_lot(db, farmer_id)

    check = repo.insert_check(
        db,
        lot_id=lot.id,
        temperature_c=30.0,
        temp_source="request",
        elapsed_hours=12.0,
        freshness_used=0.25,
        remaining_hours=51.1,
        status="FRESH",
    )

    assert check.lot_id == lot.id
    assert check.temp_source == "request"
    assert check.remaining_hours == pytest.approx(51.1)


def test_insert_alert_returns_none_on_duplicate_dedup_key(db):
    """Verify that repeated alert keys return None and leave a single stored alert."""
    farmer_id = _farmer_id()
    lot = _insert_lot(db, farmer_id, status="AT_RISK")
    dedup_key = f"{farmer_id}:{lot.id}:AT_RISK"

    first = repo.insert_alert(
        db,
        lot_id=lot.id,
        farmer_id=farmer_id,
        kind="AT_RISK",
        title="Lot at risk",
        body="Sell soon",
        payload={"remaining_hours": 51.1},
        dedup_key=dedup_key,
    )
    second = repo.insert_alert(
        db,
        lot_id=lot.id,
        farmer_id=farmer_id,
        kind="AT_RISK",
        title="Lot at risk (again)",
        body="Sell soon",
        payload=None,
        dedup_key=dedup_key,
    )

    assert first is not None
    assert second is None  # the outbox guarantees no duplicate alert
    assert len(repo.list_alerts(db, farmer_id)) == 1


def test_list_alerts_unread_only(db):
    """Verify that marking an alert read excludes it only from unread listings."""
    farmer_id = _farmer_id()
    lot = _insert_lot(db, farmer_id, status="AT_RISK")
    alert = repo.insert_alert(
        db,
        lot_id=lot.id,
        farmer_id=farmer_id,
        kind="AT_RISK",
        title="Lot at risk",
        body="Sell soon",
        payload=None,
        dedup_key=f"{farmer_id}:{lot.id}:AT_RISK",
    )

    assert len(repo.list_alerts(db, farmer_id, unread_only=True)) == 1
    repo.mark_alert_read(db, alert.id, farmer_id, read_at=NOW)
    assert repo.list_alerts(db, farmer_id, unread_only=True) == []
    assert len(repo.list_alerts(db, farmer_id, unread_only=False)) == 1


def test_mark_alert_read_is_ownership_scoped(db):
    """Verify that marking another farmer's alert read returns None."""
    owner = _farmer_id()
    other = _farmer_id()
    lot = _insert_lot(db, owner, status="AT_RISK")
    alert = repo.insert_alert(
        db,
        lot_id=lot.id,
        farmer_id=owner,
        kind="AT_RISK",
        title="Lot at risk",
        body="Sell soon",
        payload=None,
        dedup_key=f"{owner}:{lot.id}:AT_RISK",
    )

    assert repo.mark_alert_read(db, alert.id, other, read_at=NOW) is None


def test_list_buyers_for_crop_reads_only_matching_crop_from_the_view(db):
    """Verify that the buyer view returns only offers for the requested crop."""
    with db.begin() as conn:
        conn.exec_driver_sql(
            """
            INSERT INTO cr_demo_buyers
                (buyer_id, buyer_name, crop_code, price_per_kg, max_qty_kg, lat, lng, reliability)
            VALUES
                ('test-tomato-buyer', 'Test Tomato Buyer', 'tomato', 20.0, 300, 18.53, 73.86, 0.9),
                ('test-spinach-buyer', 'Test Spinach Buyer', 'spinach', 15.0, 200, 18.60, 73.90, 0.8)
            """
        )

    tomato_buyers = repo.list_buyers_for_crop(db, "tomato")

    assert [b.buyer_id for b in tomato_buyers] == ["test-tomato-buyer"]
    assert tomato_buyers[0].price_per_kg == pytest.approx(20.0)
