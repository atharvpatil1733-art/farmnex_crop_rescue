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
    from types import SimpleNamespace
    from fastapi import Depends, FastAPI, Header, HTTPException
    from fastapi.testclient import TestClient

    from app.modules import crop_rescue
    from app.modules.crop_rescue import router

    WITH_DB = sys.argv[1] == "db"
    P = "/api/v2/rescue"   # FarmNex mounts everything under /api/v2

    # FarmNex: the host does NOT call crop_rescue.configure(engine=...) (its engine is async).
    # In db mode the module builds its own sync engine from CR_DATABASE_URL.

    def get_current_user(authorization: str | None = Header(None), x_user: str | None = Header(None), x_role: str = Header("FARMER")):
        if authorization != "Bearer good" or not x_user:
            raise HTTPException(401, "not logged in")
        # id is the internal integer the app never shows; public_id is the UUID that identifies the farmer
        return SimpleNamespace(id=424242, public_id=x_user, role=SimpleNamespace(name=x_role))

    async def rescue_farmer_id(user=Depends(get_current_user)) -> str:
        if user.role is None or user.role.name != "FARMER":
            raise HTTPException(403, "Only farmers can use Crop Rescue.")
        return str(user.public_id)

    app = FastAPI()

    @app.get("/")
    def host_root():
        return {"host": "still works"}

    app.include_router(router, prefix="/api/v2", dependencies=[Depends(get_current_user)])
    app.dependency_overrides[crop_rescue.current_farmer_id] = rescue_farmer_id

    client = TestClient(app)
    def as_user(name, role="FARMER"):
        return {"Authorization": "Bearer good", "X-User": name, "X-Role": role}

    # host route untouched, docs has the crop-rescue section, and the unprefixed path is not mounted
    assert client.get("/").json() == {"host": "still works"}
    assert client.get("/docs").status_code == 200
    spec = client.get("/openapi.json").json()
    tags = {t for p in spec["paths"].values() for op in p.values() for t in op.get("tags", [])}
    assert "crop-rescue" in tags, tags
    assert all(path.startswith("/api/v2/rescue") for path in spec["paths"] if "rescue" in path), list(spec["paths"])
    assert client.get("/rescue/crops", headers=as_user("A")).status_code == 404

    # host auth wraps the router; only farmers get through
    assert client.get(P + "/health").status_code == 401
    assert client.get(P + "/crops", headers={"Authorization": "Bearer bad", "X-User": "A"}).status_code == 401
    assert client.get(P + "/lots", headers=as_user("A", "ADMIN")).status_code == 403
    assert client.get(P + "/crops", headers=as_user("A")).status_code == 200

    if WITH_DB:
        assert client.get(P + "/health", headers=as_user("A")).json() == {"ok": True, "crops": 8, "db": True}
        body = {
            "crop_code": "tomato", "quantity_kg": 500, "lat": 18.5204, "lng": 73.8567,
            "harvested_at": datetime.now(timezone.utc).isoformat(), "temperature_c": 30,
        }
        made = client.post(P + "/lots", json=body, headers=as_user("uuid-farmer-A"))
        assert made.status_code == 201, made.text
        lot_id = made.json()["id"]
        assert client.get(f"{P}/lots/{lot_id}", headers=as_user("uuid-farmer-A")).status_code == 200
        assert client.get(f"{P}/lots/{lot_id}", headers=as_user("uuid-farmer-B")).status_code == 404
        assert client.get(f"{P}/lots/{lot_id}?farmer_id=uuid-farmer-A", headers=as_user("uuid-farmer-B")).status_code == 404
        assert client.get(P + "/lots", headers=as_user("uuid-farmer-B")).json() == []
        assert client.get(P + "/lots", headers=as_user("424242")).json() == []  # the internal integer id is not a farmer id

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
    if mode == "db":
        # Like FarmNex: the module gets its own CR_DATABASE_URL, and the host's async DATABASE_URL must be ignored.
        env["CR_DATABASE_URL"] = os.environ["CR_TEST_DATABASE_URL"]
        env["DATABASE_URL"] = "postgresql+asyncpg://host:host@invalid.example/host"
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
