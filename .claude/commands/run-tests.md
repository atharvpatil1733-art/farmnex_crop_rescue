---
description: Start the test Postgres if needed and run the full test suite
---

1. If `CR_TEST_DATABASE_URL` is not set, run `docker compose up -d db` and wait until it's healthy. Then use `postgresql+psycopg://farmnex:farmnex@localhost:5433/crop_rescue_test`.
2. Run `pytest -q`.
3. If anything fails, fix the code, not the test, unless the test contradicts CLAUDE.md. In that case, tell me.
4. Report: passed/failed counts, plus one line per fix you made.
