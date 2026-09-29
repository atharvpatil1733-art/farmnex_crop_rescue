"""A simulated host backend: crop_rescue/ copied to app/modules/crop_rescue,
mounted exactly as INTEGRATION.md step 3 says, next to the host's own route,
a fake login and the `dependency_overrides` line.

Runs in a subprocess whose sys.path has only the temp dir, so only relative
imports can work. The database half runs only if CR_TEST_DATABASE_URL is set.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

HOST_SCRIPT = textwrap.dedent(
    """
    import os, sys
    from datetime import datetime, timezone
    import sqlalchemy as sa
    from fastapi import Depends, FastAPI, Header, HTTPException
    from fastapi.testclient import TestClient

    from app.modules import crop_rescue
    from app.modules.crop_rescue import router

    WITH_DB = sys.argv[1] == "db"
    if WITH_DB:
        crop_rescue.configure(engine=sa.create_engine(os.environ["CR_TEST_DATABASE_URL"]))

    def get_current_user(authorization: str | None = Header(None), x_user: str | None = Header(None)):
        if authorization != "Bearer good" or not x_user:
            raise HTTPException(401, "not logged in")
        return type("User", (), {"id": x_user})()

    app = FastAPI()

    @app.get("/")
    def host_root():
        return {"host": "still works"}

    app.include_router(router, dependencies=[Depends(get_current_user)])
    app.dependency_overrides[crop_rescue.current_farmer_id] = lambda user=Depends(get_current_user): str(user.id)

    client = TestClient(app)
    def as_user(name):
        return {"Authorization": "Bearer good", "X-User": name}

    # host route untouched, docs has the crop-rescue section
    assert client.get("/").json() == {"host": "still works"}
    assert client.get("/docs").status_code == 200
    spec = client.get("/openapi.json").json()
    tags = {t for p in spec["paths"].values() for op in p.values() for t in op.get("tags", [])}
    assert "crop-rescue" in tags, tags

    # host auth wraps the router
    assert client.get("/rescue/health").status_code == 401
    assert client.get("/rescue/crops", headers={"Authorization": "Bearer bad", "X-User": "A"}).status_code == 401
    assert client.get("/rescue/crops", headers=as_user("A")).status_code == 200

    if WITH_DB:
        assert client.get("/rescue/health", headers=as_user("A")).json() == {"ok": True, "crops": 8, "db": True}
        body = {
            "crop_code": "tomato", "quantity_kg": 500, "lat": 18.5204, "lng": 73.8567,
            "harvested_at": datetime.now(timezone.utc).isoformat(), "temperature_c": 30,
        }
        made = client.post("/rescue/lots", json=body, headers=as_user("host-farmer-A"))
        assert made.status_code == 201, made.text
        lot_id = made.json()["id"]
        assert client.get(f"/rescue/lots/{lot_id}", headers=as_user("host-farmer-A")).status_code == 200
        assert client.get(f"/rescue/lots/{lot_id}", headers=as_user("host-farmer-B")).status_code == 404
        assert client.get(f"/rescue/lots/{lot_id}?farmer_id=host-farmer-A", headers=as_user("host-farmer-B")).status_code == 404
        assert client.get("/rescue/lots", headers=as_user("host-farmer-B")).json() == []

    print("SIMULATED_HOST_OK")
    """
)


def _run_host(tmp_path: Path, mode: str) -> subprocess.CompletedProcess:
    shutil.copytree(
        REPO_ROOT / "crop_rescue",
        tmp_path / "app" / "modules" / "crop_rescue",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "app" / "modules" / "__init__.py").write_text("")
    script = tmp_path / "host_main.py"
    script.write_text(HOST_SCRIPT)

    env = {k: v for k, v in os.environ.items() if k not in ("CR_DATABASE_URL", "DATABASE_URL")}
    env["CR_ENABLE_SCHEDULER"] = "false"
    return subprocess.run(
        [sys.executable, str(script), mode],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_simulated_host_auth_docs_and_host_routes_without_a_database(tmp_path):
    result = _run_host(tmp_path, "nodb")
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "SIMULATED_HOST_OK" in result.stdout


def test_simulated_host_health_and_farmer_isolation_with_a_database(db, tmp_path):
    result = _run_host(tmp_path, "db")
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "SIMULATED_HOST_OK" in result.stdout
