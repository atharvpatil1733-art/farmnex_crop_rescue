"""Mounting test: the host's own auth dependency wraps the router.

Needs no database: /rescue/crops is pure crops.json data, so this proves
mounting and auth wrapping work in isolation from the DB layer.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from crop_rescue import router


def _fake_auth_that_fails():
    """Simulate a host authentication dependency that rejects the request."""
    raise HTTPException(401, "not logged in")


def _fake_auth_that_succeeds():
    """Simulate a host authentication dependency returning a farmer identity."""
    return "farmer-mounted"


def test_host_auth_dependency_rejects_when_it_fails():
    """Verify that the host's authentication failure blocks crop catalog access."""
    app = FastAPI()
    app.include_router(router, dependencies=[Depends(_fake_auth_that_fails)])
    client = TestClient(app)

    response = client.get("/rescue/crops")

    assert response.status_code == 401


def test_host_auth_dependency_allows_through_when_it_succeeds():
    """Verify that successful host authentication permits access to the crop catalog."""
    app = FastAPI()
    app.include_router(router, dependencies=[Depends(_fake_auth_that_succeeds)])
    client = TestClient(app)

    response = client.get("/rescue/crops")

    assert response.status_code == 200
    assert response.json()["q10"] == 2.0


def test_router_never_defines_its_own_health_or_docs_route():
    """Verify that the router does not claim the host's root, health, or docs paths."""
    paths = {r.path for r in router.routes}
    assert "/" not in paths
    assert "/health" not in paths
    assert "/docs" not in paths
