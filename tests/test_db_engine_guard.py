"""A host with an async engine (FarmNex: asyncpg) must get a clear error, not MissingGreenlet later."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine

from crop_rescue import db


@pytest.fixture(autouse=True)
def _reset_db_state(monkeypatch):
    monkeypatch.setattr(db, "_injected_engine", None)
    monkeypatch.setattr(db, "_lazy_engine", None)


def test_configure_rejects_an_async_engine():
    async_engine = SimpleNamespace(dialect=SimpleNamespace(is_async=True))  # what an asyncpg engine reports
    with pytest.raises(TypeError, match="synchronous"):
        db.configure(engine=async_engine)


def test_configure_accepts_a_sync_engine():
    engine = create_engine("sqlite://")
    db.configure(engine=engine)
    assert db.get_engine() is engine


def test_lazy_engine_rejects_an_async_url(monkeypatch):
    monkeypatch.setattr(db.settings, "database_url", SecretStr("postgresql+asyncpg://u:p@localhost/x"))
    with pytest.raises(RuntimeError, match="async driver"):
        db.get_engine()


def test_lazy_engine_accepts_the_real_farmnex_style_psycopg_url(monkeypatch):
    monkeypatch.setattr(
        db.settings, "database_url", SecretStr("postgresql+psycopg://u:p@localhost:5432/postgres?sslmode=require")
    )
    engine = db.get_engine()  # building an engine opens no connection
    assert engine.dialect.driver == "psycopg"


def test_a_malformed_url_error_never_contains_the_password(monkeypatch):
    monkeypatch.setattr(db.settings, "database_url", SecretStr("not a url, password hunter2"))
    with pytest.raises(RuntimeError) as err:
        db.get_engine()
    assert "hunter2" not in str(err.value)
    assert err.value.__cause__ is None
