# Build plan: FarmNex Crop Rescue (router module)

Build one phase per `/build-phase <n>` and stop after each one. Rough times assume Claude Code is doing the typing.

## Phase 1: Core engine (≈1.5 h) · skills: shelf-life-engine
- [ ] `crop_rescue/core/shelf_life.py`: load crops.json, `life_hours`, `advance_freshness`, `remaining_hours`
- [ ] `crop_rescue/core/status.py`: status rules plus `should_alert(prev_status, new_status)`
- [ ] `crop_rescue/config.py`: pydantic-settings with every `CR_` var and its default
- [ ] tests: sanity-number table, cold cap, accumulation, status thresholds, the ≥48 h notice property

## Phase 2: Matching (≈1 h) · skills: shelf-life-engine
- [ ] `crop_rescue/core/matching.py`: haversine, feasibility, net price, floor, scoring, reasons
- [ ] tests: radius, too-slow, below-floor, ordering, top-N, empty candidates

## Phase 3: Database (≈1 h) · skills: drop-in-contract
- [ ] `migrations/001_crop_rescue.sql` (idempotent) and `migrations/002_demo_seed.sql` (10 DEMO buyers around Pune, Chakan and Nashik)
- [ ] `crop_rescue/db.py` (lazy engine, `configure()`), `crop_rescue/repository.py`
- [ ] tests against real Postgres (docker compose `db` service)

## Phase 4: Router, service and scheduler (≈2 h) · skills: drop-in-contract, shelf-life-engine
- [ ] `schemas.py` (with examples), `service.py` (with the `on_alert` hook and check-on-read), `api.py` (all endpoints, with summaries), `scheduler.py`
- [ ] `crop_rescue/__init__.py` public surface
- [ ] `dev_app.py` (local testing only)
- [ ] API test: create → simulate → alert → matches → sold → no more alerts
- [ ] mounting test: host auth dependency wraps the router (401 when it fails)

## Phase 5: Flutter client and integration docs (≈1 h) · skills: drop-in-contract
- [ ] `integration/flutter/crop_rescue_api.dart` (takes the app's existing Dio)
- [ ] `INTEGRATION.md` (5 steps plus curl smoke tests)
- [ ] `/integration-check` all ✅

## Phase 6: Judge polish (≈1 h)
- [ ] README.md: the problem in 2 lines, the algorithm in under a page, the source citation, an assumptions table, the demo script
- [ ] `/demo` all PASS; transcript saved to `docs/demo_transcript.md`
- [ ] judge-reviewer: no MUST-FIX left

**Total ≈ 7–8 h.** Then mount it in the main backend (≈30 min) and wire up the Flutter screens (≈1–2 h).
