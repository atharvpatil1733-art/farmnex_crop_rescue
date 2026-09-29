"""API test: create -> simulate -> alert -> matches -> sold -> no more alerts.

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
def client(db):
    """Mount the router in a test client using the isolated database engine."""
    crop_rescue.configure(engine=db)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _as_farmer(client: TestClient, farmer_id: str) -> TestClient:
    """Override the client's farmer dependency and return the same client."""
    client.app.dependency_overrides[current_farmer_id] = lambda: farmer_id
    return client


def _seed_tomato_buyer(db, buyer_id: str = "test-api-buyer") -> None:
    """Insert a nearby tomato buyer into the isolated database for matching tests."""
    with db.begin() as conn:
        conn.exec_driver_sql(
            f"""
            INSERT INTO cr_demo_buyers
                (buyer_id, buyer_name, crop_code, price_per_kg, max_qty_kg, lat, lng, reliability)
            VALUES
                ('{buyer_id}', 'Test API Buyer', 'tomato', 20.0, 600, 18.53, 73.86, 0.9)
            """
        )


def test_full_lifecycle_create_simulate_alert_matches_sold(db, client):
    """Verify creation, ageing, alerts, matching, and exclusion from checks after sale."""
    farmer_id = f"farmer-{uuid.uuid4()}"
    _as_farmer(client, farmer_id)
    _seed_tomato_buyer(db)

    # 1. create: a fresh tomato lot at 30 °C, harvested now.
    create_response = client.post(
        "/rescue/lots",
        json={
            "crop_code": "tomato",
            "quantity_kg": 500,
            "harvested_at": _harvested_now(),
            "lat": 18.5204,
            "lng": 73.8567,
            "storage_mode": "ambient",
            "floor_price_per_kg": 10,
            "temperature_c": 30,
        },
    )
    assert create_response.status_code == 201, create_response.text
    lot = create_response.json()
    assert lot["status"] == "FRESH"
    assert lot["remaining_hours"] == pytest.approx(68.2, abs=0.5)
    lot_id = lot["id"]

    # 2. simulate: fast-forward 36 h without waiting.
    simulate_response = client.post("/rescue/simulate", json={"hours": 36, "lot_id": lot_id})
    assert simulate_response.status_code == 200, simulate_response.text
    simulated_lot = simulate_response.json()["lots"][0]
    assert simulated_lot["status"] == "AT_RISK"
    assert simulated_lot["remaining_hours"] > 0

    # 3. alert: an AT_RISK alert now exists.
    alerts_response = client.get("/rescue/alerts")
    assert alerts_response.status_code == 200
    alerts = alerts_response.json()
    assert len(alerts) == 1
    assert alerts[0]["kind"] == "AT_RISK"
    assert alerts[0]["payload"]["lot_id"] == lot_id

    # 4. matches: the top buyers for this lot.
    matches_response = client.get(f"/rescue/lots/{lot_id}/matches")
    assert matches_response.status_code == 200
    matches = matches_response.json()
    assert len(matches) == 1
    assert matches[0]["buyer_id"] == "test-api-buyer"
    assert "₹" in matches[0]["reason"]

    # 5. sold: mark it sold.
    sold_response = client.post(f"/rescue/lots/{lot_id}/sold")
    assert sold_response.status_code == 200
    assert sold_response.json()["status"] == "SOLD"

    # 6. no more alerts: running the engine again creates nothing new.
    check_response = client.post("/rescue/check")
    assert check_response.status_code == 200
    assert check_response.json()["checked"] == 0  # SOLD lots are not active

    alerts_after = client.get("/rescue/alerts").json()
    assert len(alerts_after) == 1  # still just the one AT_RISK alert


def test_matches_returns_409_when_lot_is_not_at_risk(client):
    """Verify that requesting buyers for a FRESH lot returns HTTP 409."""
    farmer_id = f"farmer-{uuid.uuid4()}"
    _as_farmer(client, farmer_id)

    create_response = client.post(
        "/rescue/lots",
        json={
            "crop_code": "tomato",
            "quantity_kg": 500,
            "harvested_at": _harvested_now(),
            "lat": 18.5204,
            "lng": 73.8567,
            "temperature_c": 20,  # cool enough to stay FRESH
        },
    )
    lot_id = create_response.json()["id"]
    assert create_response.json()["status"] == "FRESH"

    response = client.get(f"/rescue/lots/{lot_id}/matches")

    assert response.status_code == 409


def test_create_lot_rejects_unknown_crop_code(client):
    """Verify that an unsupported crop code returns HTTP 422."""
    farmer_id = f"farmer-{uuid.uuid4()}"
    _as_farmer(client, farmer_id)

    response = client.post(
        "/rescue/lots",
        json={
            "crop_code": "durian",
            "quantity_kg": 500,
            "harvested_at": _harvested_now(),
            "lat": 18.5204,
            "lng": 73.8567,
        },
    )

    assert response.status_code == 422


def test_health_reports_db_true_when_configured(client):
    """Verify that health reports eight crops and a reachable test database."""
    response = client.get("/rescue/health")
    assert response.status_code == 200
    body = response.json()
    assert body == {"ok": True, "crops": 8, "db": True}


def _create_tomato_lot(client: TestClient, temperature_c: float = 30) -> dict:
    """Create a freshly harvested tomato lot and return the successful JSON response."""
    response = client.post(
        "/rescue/lots",
        json={
            "crop_code": "tomato",
            "quantity_kg": 500,
            "harvested_at": _harvested_now(),
            "lat": 18.5204,
            "lng": 73.8567,
            "temperature_c": temperature_c,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_real_check_after_simulate_does_not_fail(client):
    """Regression: simulate must never stamp a future last_checked_at, or the
    next real check would reject it and POST /rescue/check would 500."""
    _as_farmer(client, f"farmer-{uuid.uuid4()}")
    lot = _create_tomato_lot(client)

    client.post("/rescue/simulate", json={"hours": 36, "lot_id": lot["id"]})
    check_response = client.post("/rescue/check")

    assert check_response.status_code == 200, check_response.text
    detail = client.get(f"/rescue/lots/{lot['id']}").json()
    assert detail["status"] == "AT_RISK"
    assert detail["remaining_hours"] == pytest.approx(68.2 - 36, abs=0.5)


def test_simulate_never_touches_a_sold_lot(client):
    """Verify that simulating a sold lot preserves its SOLD status."""
    _as_farmer(client, f"farmer-{uuid.uuid4()}")
    lot = _create_tomato_lot(client)
    client.post(f"/rescue/lots/{lot['id']}/sold")

    response = client.post("/rescue/simulate", json={"hours": 100, "lot_id": lot["id"]})

    assert response.status_code == 200
    assert response.json()["lots"][0]["status"] == "SOLD"
    assert client.get(f"/rescue/lots/{lot['id']}").json()["status"] == "SOLD"


def test_failed_check_rolls_back_the_lot_update_and_alert(client, monkeypatch):
    """The lot update, check row and alert commit together: if writing the
    check row fails, the lot keeps its old status and no alert exists."""
    _as_farmer(client, f"farmer-{uuid.uuid4()}")
    lot = _create_tomato_lot(client)
    assert lot["status"] == "FRESH"

    def fail(*args, **kwargs):
        """Fail the check insert to exercise transaction rollback."""
        raise RuntimeError("insert_check failed")

    monkeypatch.setattr("crop_rescue.repository.insert_check", fail)
    with pytest.raises(RuntimeError):
        client.post("/rescue/simulate", json={"hours": 36, "lot_id": lot["id"]})
    monkeypatch.undo()

    detail = client.get(f"/rescue/lots/{lot['id']}").json()
    assert detail["status"] == "FRESH"
    assert detail["remaining_hours"] == lot["remaining_hours"]
    assert len(detail["checks"]) == 1
    assert client.get("/rescue/alerts").json() == []


def test_check_on_read_runs_when_any_lot_is_overdue(db, client):
    """Staleness follows the OLDEST open lot: a freshly registered lot must
    not hide another lot whose last check is overdue."""
    _as_farmer(client, f"farmer-{uuid.uuid4()}")
    overdue = _create_tomato_lot(client, temperature_c=20)
    with db.begin() as conn:
        conn.exec_driver_sql(
            "UPDATE cr_lots SET last_checked_at = now() - interval '13 hours' WHERE id = %s",
            (overdue["id"],),
        )
    _create_tomato_lot(client, temperature_c=20)  # the newest check is now "just now"

    client.get("/rescue/lots")  # check-on-read

    checks = client.get(f"/rescue/lots/{overdue['id']}").json()["checks"]
    assert len(checks) == 2
    assert checks[0]["elapsed_hours"] == pytest.approx(13, abs=0.1)
