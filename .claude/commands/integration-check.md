---
description: Verify crop_rescue/ is still a clean drop-in router for the main FarmNex FastAPI backend
---

Check each item and report ✅ or ❌ with the file:line for any failure.

1. `grep -rn "^from \|^import " crop_rescue/`: nothing imports `app`, `dev_app`, `tests` or anything outside `crop_rescue` and requirements.txt.
2. `python -c "import crop_rescue"` succeeds with **no** env vars set.
3. `crop_rescue/` contains no `FastAPI()` instance, no API-key code, and no routes outside `/rescue`.
4. **Simulated host:** copy `crop_rescue/` into a temp dir next to a fresh `main.py` that has its own `/` route and a fake `get_current_user` dependency, then does `app.include_router(router, dependencies=[Depends(get_current_user)])`. Check:
   - `/rescue/health` → 200 against the test DB when auth passes
   - `/rescue/health` → 401 when the fake auth raises
   - the host's own `/` route still works, and `/docs` shows a **crop-rescue** section
5. Every table, view and index in `migrations/*.sql` starts with `cr_`. Running `001` twice doesn't error.
6. Every Pydantic response model in `schemas.py` has a matching Dart class in `integration/flutter/crop_rescue_api.dart` with the same JSON keys, and the Dart client takes an existing `Dio`.
7. Every env var read in `config.py` starts with `CR_` (the `DATABASE_URL` fallback is allowed).
8. INTEGRATION.md has exactly 5 numbered steps plus curl smoke tests.

Fix any ❌, then re-run.
