---
description: Start the TEST Postgres if needed and run the full test suite (never touches the main Supabase database)
---

1. Make sure a **test** database is available at `CR_TEST_DATABASE_URL`:
   - If docker works: `docker compose up -d db`, wait until it's healthy, and use `postgresql+psycopg://farmnex:farmnex@localhost:5433/crop_rescue_test`.
   - If docker is not available (e.g. a cloud session): install PostgreSQL locally (`apt-get install -y postgresql`), start it, create user `farmnex` with password `farmnex` and database `crop_rescue_test`, and use `postgresql+psycopg://farmnex:farmnex@localhost:5432/crop_rescue_test`.
   - **Never** use `CR_DATABASE_URL`, `DATABASE_URL` or any `supabase.com` URL for tests. If the only URL available is the main Supabase one, stop and tell me.
2. The test fixtures apply `migrations/*.sql` to the **test** database only.
3. Run `pytest -q`.
4. If anything fails, fix the code, not the test, unless the test contradicts CLAUDE.md. In that case, tell me. Never weaken `tests/test_migrations_safe.py`.
5. Report: passed/failed/skipped counts, plus one line per fix you made.
