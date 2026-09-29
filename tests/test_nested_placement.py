"""Nested placement: crop_rescue/ works when copied to app/modules/crop_rescue.

This proves the "relative imports only" rule (CLAUDE.md), not just that the
package happens to still be importable under its usual top-level name. The
check runs in a *subprocess* whose sys.path does not include this repo's
root, so the only way `import app.modules.crop_rescue` can succeed is if
every import inside the package is relative (`from .xyz import ...`).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

RUN_NESTED_SCRIPT = textwrap.dedent(
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.modules.crop_rescue import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.get("/rescue/crops")
    assert response.status_code == 200, response.text
    assert response.json()["q10"] == 2.0
    assert len(response.json()["crops"]) == 8
    print("NESTED_PLACEMENT_OK")
    """
)


def test_nested_placement_with_relative_imports_only(tmp_path):
    dest_pkg = tmp_path / "app" / "modules" / "crop_rescue"
    shutil.copytree(REPO_ROOT / "crop_rescue", dest_pkg)
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "app" / "modules" / "__init__.py").write_text("")

    script_path = tmp_path / "run_nested.py"
    script_path.write_text(RUN_NESTED_SCRIPT)

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "NESTED_PLACEMENT_OK" in result.stdout
