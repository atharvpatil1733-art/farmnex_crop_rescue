---
description: Verify crop_rescue/ is still a clean, safe drop-in router for the main FarmNex FastAPI backend
---

Check each item and report ✅ or ❌ with the file:line for any failure.

**Module hygiene**
1. `grep -rn "^from \|^import " crop_rescue/`: nothing imports `app`, `dev_app`, `tests` or anything outside `crop_rescue` and requirements.txt. Imports of the package itself are **relative** (no `from crop_rescue.` inside `crop_rescue/`).
2. `python -c "import crop_rescue"` succeeds with **no** env vars set.
3. `crop_rescue/` contains no `FastAPI()` instance, no API-key code, and no routes outside `/rescue`.
4. `api.py` contains no SQL and no business logic; it only calls `service.py`.

**Database safety**
5. `tests/test_migrations_safe.py` passes. Also check by hand: no `DROP`, `TRUNCATE`, `GRANT`, `REVOKE` or `CREATE EXTENSION` in `migrations/*.sql`; every table, view and index starts with `cr_`; each file is wrapped in `BEGIN; ... COMMIT;`.
6. No code or test reads a non-`cr_` table, and no test reads `CR_DATABASE_URL` or `DATABASE_URL` (tests use only `CR_TEST_DATABASE_URL`).

**Simulated host**
7. Copy `crop_rescue/` into a temp dir at `app/modules/crop_rescue/`, next to a fresh `main.py` that has its own `/` route and a fake `get_current_user`. It should do `include_router(router, dependencies=[Depends(get_current_user)])` and override `current_farmer_id`. Check:
   - `/rescue/health` → 200 against the test DB when auth passes
   - `/rescue/health` → 401 when the fake auth raises
   - farmer A can't see farmer B's lot (404)
   - the host's own `/` route still works, and `/docs` shows a **crop-rescue** section

**Clients and docs**
8. Every Pydantic response model in `schemas.py` has a matching Dart class in `integration/flutter/crop_rescue_api.dart` with the same JSON keys. The Dart client takes an existing `Dio` and has no `farmerId` parameters.
9. Every env var read in `config.py` starts with `CR_` (the `DATABASE_URL` fallback is allowed at runtime only).
10. INTEGRATION.md has exactly 5 numbered steps (including the `dependency_overrides` line) plus curl smoke tests.

Fix any ❌, then re-run.
