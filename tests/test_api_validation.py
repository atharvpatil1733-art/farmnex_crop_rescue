"""Request validation that fails before any database call.

Needs no database: an unconnected engine is injected, and every request
here is rejected before it would be used.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from crop_rescue import current_farmer_id, router


@pytest.fixture
def client(monkeypatch):
    # create_engine never connects by itself; this URL is never reached.
    unconnected = sa.create_engine("postgresql+psycopg://nobody@127.0.0.1:1/never_used")
    monkeypatch.setattr("crop_rescue.db._injected_engine", unconnected)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[current_farmer_id] = lambda: "farmer-validation"
    return TestClient(app)


def _lot_body(harvested_at: str) -> dict:
    return {
        "crop_code": "tomato",
        "quantity_kg": 500,
        "harvested_at": harvested_at,
        "lat": 18.5204,
        "lng": 73.8567,
        "temperature_c": 30,
    }


def test_harvested_at_in_the_future_is_422_not_500(client):
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    response = client.post("/rescue/lots", json=_lot_body(tomorrow))

    assert response.status_code == 422
    assert "harvested_at" in response.json()["detail"]


def test_harvested_at_without_a_timezone_is_422_not_500(client):
    response = client.post("/rescue/lots", json=_lot_body("2026-09-28T06:00:00"))

    assert response.status_code == 422
    assert "harvested_at" in response.json()["detail"]
