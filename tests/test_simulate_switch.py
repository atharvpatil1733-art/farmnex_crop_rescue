"""Simulate switch: with CR_ENABLE_SIMULATE=false, /rescue/simulate -> 404.

Needs no database: the switch is checked in api.py before any DB call.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from crop_rescue import current_farmer_id, router, settings


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[current_farmer_id] = lambda: "farmer-switch"
    return TestClient(app)


def test_simulate_returns_404_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "enable_simulate", False)
    client = _client()

    response = client.post("/rescue/simulate", json={"hours": 24})

    assert response.status_code == 404


def test_simulate_switch_does_not_affect_other_endpoints(monkeypatch):
    monkeypatch.setattr(settings, "enable_simulate", False)
    client = _client()

    response = client.get("/rescue/crops")

    assert response.status_code == 200
