---
name: drop-in-contract
description: Integration rules that keep crop_rescue/ a copy-paste router module for the existing FarmNex FastAPI backend + Supabase PostgreSQL + Flutter app. Load before creating or editing api.py, db.py, repository.py, schemas.py, scheduler.py, config.py, __init__.py, dev_app.py, migrations/, integration/, INTEGRATION.md, or requirements.txt.
---

# Drop-in router contract

The team will **copy the `crop_rescue/` folder into their existing FastAPI backend** and mount it with `app.include_router(router)`. It then runs inside that backend: the same server, URL and Supabase database. Anything that makes this harder is a bug.

There is **no separate service and there are no API keys** for this internal integration. Do not add either. The endpoints are still protected: the host's login wraps the router, and every farmer sees only their own data.

## Main database safety (read CLAUDE.md "Database safety rules")

- Migrations may **only add** `cr_` tables, indexes and views, plus `ENABLE ROW LEVEL SECURITY` on `cr_` tables. No `DROP`, `TRUNCATE`, non-`cr_` `ALTER`, `GRANT`/`REVOKE` or `CREATE EXTENSION`. Wrap each file in `BEGIN; ... COMMIT;`.
- Code never reads a non-`cr_` table. Buyers come only through `cr_buyer_pool`.
- Tests use `CR_TEST_DATABASE_URL` only, never the main Supabase URL. Skip DB tests if it isn't set.
- `tests/test_migrations_safe.py` must pass and must never be weakened.

## The contract (do not break)

| Rule | Why |
|---|---|
| `crop_rescue/` imports nothing outside itself (no `from app...`, no `dev_app`, no `tests`) | So it can be copied as-is |
| Inside the package, **relative imports only** (`from .service import ...`) | Works at the backend root or at `app/modules/crop_rescue/` |
| Public surface = `router, start_scheduler, stop_scheduler, settings, configure, current_farmer_id` | The host touches only these |
| The farmer comes only from `Depends(current_farmer_id)` (in `deps.py`), never from a request body | The host overrides it with the logged-in user via `app.dependency_overrides` |
| Another farmer's lot or alert → **404** (checked in `service.py`) | Farmers only see their own data |
| Layering: `api.py` (HTTP) → `service.py` (logic) → `repository.py` (SQL) | Thin router, testable logic |
| Scheduler job wrapped in `try/except` + `logger.exception`, with `max_instances=1, coalesce=True` | A failing run can never crash the host backend |
| `/rescue/simulate` returns 404 when `CR_ENABLE_SIMULATE=false` | The demo tool can be switched off after the demo |
| Light deps with version ranges, no ML libraries | No clashes with the host's requirements |
| `configure(engine=None, on_alert=None)` lets the host inject its SQLAlchemy engine and an optional FCM callback | Share the host's DB pool; optional push |
| If no engine is injected, create one from `CR_DATABASE_URL` or `DATABASE_URL` lazily (on first use, not at import) | Importing must never crash when the env isn't set |
| All tables/views prefixed `cr_`; ids are `TEXT`/`UUID` with **no FKs to host tables** | Zero coupling to the host schema |
| SQLAlchemy **Core** only, no `DeclarativeBase` | No metadata clash with the host's ORM models |
| Migrations are plain idempotent `.sql` (`CREATE TABLE IF NOT EXISTS`, `CREATE OR REPLACE VIEW`) | Pasteable in the Supabase SQL editor, re-runnable |
| No auth in the router | The host wraps it: `include_router(router, dependencies=[Depends(get_current_user)])` |
| Router prefix is exactly `/rescue`, tag `crop-rescue` | Predictable URLs; its own section in the host's `/docs` |
| No route at `/`, `/health` or `/docs`, and no `FastAPI()` instance inside `crop_rescue/` | Never collide with the host's routes or app |
| Every response model is in `schemas.py` and in the Dart file with **identical JSON keys (snake_case)** | Flutter models never drift |
| Env vars all start with `CR_` (except the `DATABASE_URL` fallback) | No config collisions |
| Endpoints are sync `def` (FastAPI runs them in a threadpool) | Works whether the host is sync or async |
| Scheduler start/stop are plain functions the host calls from its own lifespan | The component never owns the app lifecycle |

## Judge-friendly `/docs`

The router shows up inside the main backend's `/docs`. Give every endpoint a `summary` and a one-line `description`, and give every request model `json_schema_extra` examples so "Try it out" works in one click.

## Supabase specifics

- Use `gen_random_uuid()`. It's built into PostgreSQL 13+, so no extension is needed.
- Timestamps are `TIMESTAMPTZ`, stored in UTC.
- The connection string needs `postgresql+psycopg://...` and `?sslmode=require`.
- Don't enable RLS policies here. The backend connects with the service role or DB user. Mention this in INTEGRATION.md.

## Flutter file (integration/flutter/crop_rescue_api.dart)

- One file. Uses `dio` only (no codegen, no freezed, no json_serializable).
- `class CropRescueApi { CropRescueApi(this._dio); ... }`. It takes the app's **existing** Dio, so the main backend's base URL and login token carry over automatically.
- Plain model classes with `fromJson`, one per response schema.
- Methods mirror the endpoints: `fetchCrops, createLot, listLots, getLot, getMatches, markSold, simulate, fetchAlerts, markAlertRead`.
- No `farmerId` parameters. The backend knows the farmer from the login token the Dio already sends.

## dev_app.py

Local testing only: `FastAPI()` + lifespan (scheduler) + `include_router(router)`. About 15 lines. Never referenced from inside `crop_rescue/`.

## Before finishing any change here

Run `/integration-check`. It must pass.
