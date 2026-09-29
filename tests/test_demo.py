"""The 5-step judge demo from the README, replayed end to end.

Runs against the throwaway test database only (skipped without
CR_TEST_DATABASE_URL). Each step prints a PASS/FAIL line and its key fields.
Run `pytest tests/test_demo.py -s` to see the transcript; set
CR_DEMO_TRANSCRIPT=<path> to also write it to a file.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import crop_rescue
from crop_rescue import router

SEED = Path(__file__).resolve().parent.parent / "migrations" / "002_demo_seed.sql"
PUNE = {"lat": 18.5204, "lng": 73.8567}


def _lot_body(crop: str, mode: str = "ambient") -> dict:
    return {
        "crop_code": crop,
        "quantity_kg": 500,
        "harvested_at": datetime.now(timezone.utc).isoformat(),
        "storage_mode": mode,
        "temperature_c": 30,
        **PUNE,
    }


def test_judge_demo(db, monkeypatch):
    with db.begin() as conn:
        conn.exec_driver_sql(SEED.read_text(encoding="utf-8"))
    monkeypatch.setattr(crop_rescue.db, "_injected_engine", None, raising=False)
    monkeypatch.setattr(crop_rescue.db, "_lazy_engine", None, raising=False)
    crop_rescue.configure(engine=db)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    who = {"farmer_id": "demo-farmer-1"}

    lines: list[str] = ["# Crop Rescue demo transcript", "", "Farmer `demo-farmer-1`, test database, temperature 30 C.", ""]
    failures: list[str] = []

    def step(name: str, checks: list[tuple[str, bool]], details: list[str]) -> None:
        ok = all(passed for _, passed in checks)
        lines.append(f"## {name}: {'PASS' if ok else 'FAIL'}")
        lines.extend(f"- {d}" for d in details)
        lines.extend(f"- check `{label}`: {'ok' if passed else 'FAILED'}" for label, passed in checks)
        lines.append("")
        if not ok:
            failures.append(name)

    # Step 1: tomato, ambient
    r = client.post("/rescue/lots", params=who, json=_lot_body("tomato"))
    assert r.status_code == 201, r.text
    tomato = r.json()
    step(
        "1. Tomato 500 kg, ambient, 30 C",
        [("status FRESH", tomato["status"] == "FRESH"), ("about 68 h left", abs(tomato["remaining_hours"] - 68.2) < 0.5)],
        [f"status={tomato['status']} remaining_hours={tomato['remaining_hours']} spoil_eta={tomato['spoil_eta']}"],
    )

    # Step 2: tomato, cold
    r = client.post("/rescue/lots", params=who, json=_lot_body("tomato", "cold"))
    assert r.status_code == 201, r.text
    cold = r.json()
    step(
        "2. Same tomato, cold storage",
        [("status FRESH", cold["status"] == "FRESH"), ("168 h left", abs(cold["remaining_hours"] - 168) < 0.5)],
        [f"status={cold['status']} remaining_hours={cold['remaining_hours']}"],
    )

    # Step 3: spinach
    r = client.post("/rescue/lots", params=who, json=_lot_body("spinach"))
    assert r.status_code == 201, r.text
    spinach = r.json()
    step(
        "3. Spinach at 30 C",
        [("status AT_RISK at once", spinach["status"] == "AT_RISK")],
        [f"status={spinach['status']} remaining_hours={spinach['remaining_hours']}"],
    )

    # Step 4: simulate +12 h on the ambient tomato
    r = client.post("/rescue/simulate", params=who, json={"hours": 12, "lot_id": tomato["id"]})
    assert r.status_code == 200, r.text
    aged = r.json()["lots"][0]
    alerts = client.get("/rescue/alerts", params=who).json()
    tomato_alerts = [a for a in alerts if a["lot_id"] == tomato["id"]]
    matches = client.get(f"/rescue/lots/{tomato['id']}/matches", params=who).json()
    step(
        "4. Simulate +12 h on the ambient tomato",
        [
            ("status AT_RISK", aged["status"] == "AT_RISK"),
            ("one alert for the lot", len(tomato_alerts) == 1),
            ("3 buyers", len(matches) == 3),
            ("each buyer has a reason", all(m["reason"] for m in matches)),
        ],
        [f"status={aged['status']} remaining_hours={aged['remaining_hours']}"]
        + [f"alert: {a['title']}" for a in tomato_alerts]
        + [f"buyer: {m['buyer_name']}: {m['reason']}" for m in matches],
    )

    # Step 5: sold, alerts stop
    r = client.post(f"/rescue/lots/{tomato['id']}/sold", params=who)
    before = len(client.get("/rescue/alerts", params=who).json())
    client.post("/rescue/simulate", params=who, json={"hours": 24})
    client.post("/rescue/check")
    after = client.get("/rescue/alerts", params=who).json()
    step(
        "5. Mark the tomato SOLD",
        [
            ("sold accepted", r.status_code == 200),
            ("no new alert for the sold lot", len([a for a in after if a["lot_id"] == tomato["id"]]) == len(tomato_alerts)),
        ],
        [f"alerts before={before}, after another +24 h and a check={len(after)}"],
    )

    # Ownership
    other = {"farmer_id": "demo-farmer-2"}
    seen = client.get(f"/rescue/lots/{cold['id']}", params=other)
    step(
        "Extra. Another farmer cannot see the lot",
        [("404", seen.status_code == 404), ("empty list", client.get("/rescue/lots", params=other).json() == [])],
        [f"demo-farmer-2 GET lot -> {seen.status_code}"],
    )

    transcript = "\n".join(lines)
    print("\n" + transcript)
    target = os.environ.get("CR_DEMO_TRANSCRIPT")
    if target:
        Path(target).write_text(transcript, encoding="utf-8")
    assert not failures, failures
