"""Shared fixtures for tests that need a real Postgres.

Only ever points at `CR_TEST_DATABASE_URL` (a throwaway Postgres, e.g. the
`docker compose` `db` service). Never falls back to `CR_DATABASE_URL`,
`DATABASE_URL` or any `supabase.com` URL. If `CR_TEST_DATABASE_URL` isn't
set, every test that needs `cr_engine` is skipped with a clear message.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy as sa

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def _test_database_url() -> str | None:
    """Read only the test database URL, rejecting URLs containing supabase.com."""
    url = os.environ.get("CR_TEST_DATABASE_URL")
    if url and "supabase.com" in url:
        raise RuntimeError("CR_TEST_DATABASE_URL must never point at a supabase.com database")
    return url


@pytest.fixture(scope="session")
def cr_engine():
    """A SQLAlchemy engine for CR_TEST_DATABASE_URL, with migrations applied.

    Skips the test if CR_TEST_DATABASE_URL isn't set. Never touches any
    other database.
    """
    url = _test_database_url()
    if not url:
        pytest.skip("CR_TEST_DATABASE_URL is not set; skipping tests that need a real database")

    engine = sa.create_engine(url)
    for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
        sql = migration.read_text(encoding="utf-8")
        with engine.begin() as conn:
            conn.exec_driver_sql(sql)
    yield engine
    engine.dispose()


@pytest.fixture
def db(cr_engine):
    """`cr_engine` with every cr_ table emptied, so each test starts clean."""
    with cr_engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM cr_alerts")
        conn.exec_driver_sql("DELETE FROM cr_checks")
        conn.exec_driver_sql("DELETE FROM cr_lots")
        conn.exec_driver_sql("DELETE FROM cr_demo_buyers")
    return cr_engine
