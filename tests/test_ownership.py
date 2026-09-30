"""Ownership: another farmer's lot or alert -> 404, never 403 (so ids
aren't confirmed to exist), and `farmer_id` in a POST body is ignored.

DB-backed: skipped automatically (via the `db` fixture) if
CR_TEST_DATABASE_URL isn't set.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import crop_rescue
from crop_rescue import current_farmer_id, router


def _harvested_now() -> str:
    """Harvested this instant. A fixed date would age the lot in real time
    (the first check counts from harvested_at), making tests time-dependent."""
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def app(db):
    """Mount the router in a fresh FastAPI app using the isolated test database."""
    crop_rescue.configure(engine=db)
    fastapi_app = FastAPI()
    fastapi_app.include_router(router)
    return fastapi_app


def _client_as(app: FastAPI, farmer_id: str) -> TestClient:
    """Override the app's farmer dependency and return a client for that identity."""
    app.dependency_overrides[current_farmer_id] = lambda: farmer_id
    return TestClient(app)


def _create_lot(app: FastAPI, farmer_id: str) -> dict:
    """Create a freshly harvested tomato lot belonging to the requested farmer."""
    client = _client_as(app, farmer_id)
    response = client.post(
        "/rescue/lots",
        json={
            "crop_code": "tomato",
            "quantity_kg": 500,
            "harvested_at": _harvested_now(),
            "lat": 18.5204,
            "lng": 73.8567,
            "temperature_c": 30,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_get_lot_by_another_farmer_is_404(app):
    """Verify that a lot lookup conceals another farmer's lot with HTTP 404."""
    owner = f"farmer-{uuid.uuid4()}"
    other = f"farmer-{uuid.uuid4()}"
    lot = _create_lot(app, owner)

    response = _client_as(app, other).get(f"/rescue/lots/{lot['id']}")

    assert response.status_code == 404


def test_matches_for_another_farmers_lot_is_404(app):
    """Verify that buyer matching conceals another farmer's lot with HTTP 404."""
    owner = f"farmer-{uuid.uuid4()}"
    other = f"farmer-{uuid.uuid4()}"
    lot = _create_lot(app, owner)

    response = _client_as(app, other).get(f"/rescue/lots/{lot['id']}/matches")

    assert response.status_code == 404


def test_mark_sold_for_another_farmers_lot_is_404(app):
    """Verify that another farmer cannot mark an owned lot sold or alter its status."""
    owner = f"farmer-{uuid.uuid4()}"
    other = f"farmer-{uuid.uuid4()}"
    lot = _create_lot(app, owner)

    response = _client_as(app, other).post(f"/rescue/lots/{lot['id']}/sold")

    assert response.status_code == 404
    # and the owner's lot is unaffected
    owner_view = _client_as(app, owner).get(f"/rescue/lots/{lot['id']}")
    assert owner_view.json()["status"] != "SOLD"


def test_mark_alert_read_for_another_farmers_alert_is_404(app):
    """Verify that marking another farmer's alert read returns HTTP 404."""
    owner = f"farmer-{uuid.uuid4()}"
    other = f"farmer-{uuid.uuid4()}"
    lot = _create_lot(app, owner)
    _client_as(app, owner).post("/rescue/simulate", json={"hours": 36, "lot_id": lot["id"]})
    alert_id = _client_as(app, owner).get("/rescue/alerts").json()[0]["id"]

    response = _client_as(app, other).post(f"/rescue/alerts/{alert_id}/read")

    assert response.status_code == 404


def test_listing_shows_only_the_current_farmers_lots(app):
    """Verify that lot listings exclude lots belonging to another farmer."""
    farmer_a = f"farmer-{uuid.uuid4()}"
    farmer_b = f"farmer-{uuid.uuid4()}"
    _create_lot(app, farmer_a)
    _create_lot(app, farmer_a)
    _create_lot(app, farmer_b)

    lots_a = _client_as(app, farmer_a).get("/rescue/lots").json()

    assert len(lots_a) == 2


def test_farmer_id_in_the_post_body_is_ignored():
    """LotCreate has no farmer_id field at all, so extra input is simply dropped."""
    from crop_rescue.schemas import LotCreate

    lot = LotCreate.model_validate(
        {
            "crop_code": "tomato",
            "quantity_kg": 500,
            "harvested_at": _harvested_now(),
            "lat": 18.5204,
            "lng": 73.8567,
            "farmer_id": "someone-elses-id",
        }
    )
    assert not hasattr(lot, "farmer_id")


def test_unknown_lot_id_is_404_not_500(app):
    """Verify that a nonexistent lot UUID returns HTTP 404."""
    owner = f"farmer-{uuid.uuid4()}"
    response = _client_as(app, owner).get(f"/rescue/lots/{uuid.uuid4()}")
    assert response.status_code == 404


def test_non_uuid_ids_are_404_not_500(app):
    """Verify that a malformed lot or alert id returns HTTP 404, not a database error."""
    client = _client_as(app, f"farmer-{uuid.uuid4()}")
    assert client.get("/rescue/lots/not-a-uuid").status_code == 404
    assert client.post("/rescue/lots/not-a-uuid/sold").status_code == 404
    assert client.post("/rescue/alerts/not-a-uuid/read").status_code == 404
