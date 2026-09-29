# CLAUDE.md — FarmNex Crop Rescue

A FastAPI **router module** for the FarmNex SIH 2026 prototype:
1. A freshness clock per harvested lot (the crop's shelf life, adjusted for temperature).
2. An alert to the farmer **at least 48 h before spoilage** (`FRESH` → `AT_RISK`).
3. The top 3 nearby buyers for an at-risk lot.

It's a prototype for SIH judges: **simple, readable, explainable.** Every number comes from `crop_rescue/data/crops.json` or from a config value labelled as an assumption.

**Integration:** the `crop_rescue/` module goes into the existing FarmNex FastAPI backend (e.g. `app/modules/crop_rescue/`) and is registered with `app.include_router(...)`. It runs in the same process and uses the same Supabase PostgreSQL database, with its own `cr_` tables. It reuses FarmNex login and needs no separate service and no API keys. Flutter calls the main backend as usual.

## Where things are

- **`docs/SPEC.md`**: the full detail (algorithm, DB schema, ownership, API, config, scheduler, tests, demo, INTEGRATION.md content). **Read only the sections your phase needs.**
- **`docs/BUILD_PLAN.md`**: build **one phase at a time**, then stop for review.
- **`docs/FARMNEX_HOST.md`**: facts about the real FarmNex backend (user id, async DB, `/api/v2` prefix, Flutter Dio). Read it before Phase 5 or anything in `integration/` / `INTEGRATION.md`; it wins over SPEC.md about the host.
- **Skills:** `shelf-life-engine` (before touching `core/`) and `drop-in-contract` (before touching anything else in `crop_rescue/`, `migrations/`, `integration/` or `INTEGRATION.md`).
- **Commands:** `/build-phase <n>`, `/run-tests`, `/demo`, `/integration-check`. **Agent:** `judge-reviewer`, run it before calling a phase done.

## ⚠️ Database safety rules (non-negotiable)

The `cr_` tables go into the **team's main Supabase database**, which the live app uses. It must never be harmed.

1. **Add only.** The only objects this repo may create are new tables, indexes and views named `cr_*`.
2. **Forbidden, always:** `DROP` (anything, `cr_` included), `TRUNCATE`, `ALTER` on non-`cr_` objects, `INSERT`/`UPDATE`/`DELETE` on non-`cr_` tables, `GRANT`/`REVOKE`, `CREATE EXTENSION`, changes to roles, policies, schemas or auth, and resetting or restoring the database. New column on a `cr_` table: `ALTER TABLE cr_... ADD COLUMN IF NOT EXISTS` only.
3. **Never read or join a non-`cr_` table.** Buyers come only through the `cr_buyer_pool` view.
4. **Never run SQL on the main Supabase database yourself.** The user runs the migrations in the Supabase SQL editor.
5. **Tests and `/demo` use only `CR_TEST_DATABASE_URL`** (a separate throwaway Postgres). If it isn't set, skip DB tests. Never fall back to `CR_DATABASE_URL`, `DATABASE_URL` or any `supabase.com` URL.
6. **Connection strings are secrets.** Keep them only in `.env` or env vars. Never print, log or commit them.
7. `tests/test_migrations_safe.py` must always pass and must never be weakened.

If a task seems to need breaking one of these rules, **stop and ask the user**.

## Hard rules

- **Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0 **Core** (no ORM, so it can't clash with the host's models), psycopg 3, APScheduler 3. Plain `.sql` migrations, no Alembic.
- **Self-contained:** `crop_rescue/` imports nothing outside itself and uses **relative imports only** (`from .service import ...`), so it works at any path in the host.
- **No coupling:** tables are prefixed `cr_`; `farmer_id`/`buyer_id` are `TEXT` with no foreign keys to host tables.
- **Auth and ownership:** no login code and no API keys in the router. The host wraps it with its login check, and the farmer comes only from `Depends(current_farmer_id)` (the host overrides it). Another farmer's lot or alert → 404. See SPEC "Who is the farmer".
- **Layering:** `api.py` (HTTP only) → `service.py` (logic) → `repository.py` (SQL). `core/` is **pure functions** (no DB, no FastAPI, no clock; `now` is passed in).
- **Never crash the host:** the scheduler job is wrapped in `try/except` + `logger.exception`; the only external call is Open-Meteo, with a 3 s timeout; no heavy work in a request.
- **Light dependencies** with version ranges; no numpy, pandas or ML libraries. **Rule-based by design**; don't import from `farmnex_ai_forecaster`.
- **Data:** exactly 8 crops. Never edit the numbers in `crops.json` and never invent data. If something is missing, stop and ask.

## Folder layout

```
crop_rescue/            ← the module that goes into the main backend
  __init__.py           exports: router, start_scheduler, stop_scheduler, settings, configure, current_farmer_id
  config.py             CR_* settings        data/crops.json   the 8 sourced crops (read-only)
  core/                 shelf_life.py, status.py, matching.py   (pure)
  db.py  repository.py  service.py  scheduler.py  schemas.py  deps.py  api.py
migrations/             001_crop_rescue.sql, 002_demo_seed.sql
integration/flutter/    crop_rescue_api.dart
tests/                  dev_app.py (local only, never deployed)   README.md   INTEGRATION.md
docs/                   SPEC.md, BUILD_PLAN.md
```

## Out of scope — do not build

Any change to existing Supabase tables, tests against the main database, API keys, a separate service, a Dockerfile for deployment, Celery or job queues, ML models, price prediction, weather forecasting beyond the current temperature, photo-based spoilage detection, partial multi-buyer allocation, payments, logistics booking, FCM code, admin UI, more than 8 crops, Alembic.

## Definition of done

`pytest` is green (including the migration-safety, ownership, nested-placement and scheduler-safety tests) and no test touched the main database. `uvicorn dev_app:app` serves `/docs` with working examples. `/demo` passes. README explains the algorithm in under a page, cites the source and flags the assumptions. INTEGRATION.md has the 5 steps. `crop_rescue/` mounts cleanly in a fresh FastAPI app.
