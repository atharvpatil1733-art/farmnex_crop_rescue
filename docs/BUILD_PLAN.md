# Build plan: FarmNex Crop Rescue (router module)

Build one phase per `/build-phase <n>` and stop after each one. Rough times assume Claude Code is doing the typing.

## Phase 1: Core engine (≈1.5 h) · skills: shelf-life-engine · SPEC: Crop data, Algorithm §1–4, Config, Tests
- [ ] `crop_rescue/core/shelf_life.py`: load crops.json, `life_hours`, `advance_freshness`, `remaining_hours`
- [ ] `crop_rescue/core/status.py`: status rules plus `should_alert(prev_status, new_status)`
- [ ] `crop_rescue/config.py`: pydantic-settings with every `CR_` var and its default
- [ ] tests: sanity-number table, cold cap, accumulation, status thresholds, the ≥48 h notice property

## Phase 2: Matching (≈1 h) · skills: shelf-life-engine · SPEC: Algorithm §5, Tests
- [ ] `crop_rescue/core/matching.py`: haversine, feasibility, net price, floor, scoring, reasons
- [ ] tests: radius, too-slow, below-floor, ordering, top-N, empty candidates

## Phase 3: Database (≈1 h) · skills: drop-in-contract · SPEC: Database, Database connection, Tests
- [ ] `migrations/001_crop_rescue.sql` (idempotent, `BEGIN/COMMIT`, only `cr_` objects, RLS enabled on `cr_` tables) and `migrations/002_demo_seed.sql` (10 DEMO buyers around Pune, Chakan and Nashik)
- [ ] `tests/test_migrations_safe.py` (no DB needed): fails on DROP/TRUNCATE/GRANT/REVOKE/CREATE EXTENSION or any non-`cr_` object
- [ ] `crop_rescue/db.py` (lazy engine, `configure()`), `crop_rescue/repository.py`
- [ ] tests against the **test** Postgres only (`CR_TEST_DATABASE_URL`, docker compose `db` service); skipped if not set

## Phase 4: Router, service and scheduler (≈2 h) · skills: drop-in-contract, shelf-life-engine · SPEC: Who is the farmer, API contract, Scheduler, Local development, Tests
- [ ] `deps.py` (`current_farmer_id`), `schemas.py` (with examples), `service.py` (with ownership checks, the `on_alert` hook and check-on-read), thin `api.py` (all endpoints, with summaries), crash-proof `scheduler.py`
- [ ] `crop_rescue/__init__.py` public surface
- [ ] `dev_app.py` (local testing only)
- [ ] API test: create → simulate → alert → matches → sold → no more alerts
- [ ] mounting test: host auth dependency wraps the router (401 when it fails)
- [ ] ownership test (other farmer → 404), nested-placement test (`app/modules/crop_rescue`), scheduler-safety test, simulate-switch test

## Phase 5: Flutter client and integration docs (≈1 h) · skills: drop-in-contract · SPEC: API contract, INTEGRATION.md
- [ ] `integration/flutter/crop_rescue_api.dart` (takes the app's existing Dio, no `farmerId` params)
- [ ] `INTEGRATION.md` (5 steps including the `dependency_overrides` line, plus curl smoke tests)
- [ ] `/integration-check` all ✅

## Phase 6: Judge polish (≈1 h) · SPEC: Crop data, Algorithm, Demo script
- [ ] README.md: the problem in 2 lines, the algorithm in under a page, the source citation, an assumptions table, the demo script
- [ ] `/demo` all PASS; transcript saved to `docs/demo_transcript.md`
- [ ] judge-reviewer: no MUST-FIX left

**Total ≈ 7–8 h.** Then mount it in the main backend (≈30 min) and wire up the Flutter screens (≈1–2 h).
