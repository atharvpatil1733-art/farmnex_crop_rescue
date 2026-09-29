"""The SQLAlchemy Core engine used by `repository.py`.

A host with a synchronous engine may call `configure(engine=...)` to share
its pool. An async engine (FarmNex uses asyncpg) is refused. If nothing is
injected, a sync engine is created lazily (on first use, never at import)
from `CR_DATABASE_URL`, falling back to `DATABASE_URL`; a URL with an async
driver is refused. Importing this module must never crash when the env isn't
set.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url

from .config import settings

_injected_engine: Engine | None = None
_lazy_engine: Engine | None = None


def configure(engine: Engine | None = None) -> None:
    """Inject the host's own SQLAlchemy engine, or clear a previous injection.

    Calling this with `engine=None` returns to lazy engine creation from
    config on the next call to `get_engine()`.
    """
    global _injected_engine, _lazy_engine
    if engine is not None and engine.dialect.is_async:
        raise TypeError(
            "crop_rescue needs a synchronous SQLAlchemy engine; the one passed is async. "
            "Do not pass the host's async engine: set CR_DATABASE_URL "
            "(postgresql+psycopg://...) and let the module create its own."
        )
    _injected_engine = engine
    _lazy_engine = None  # drop any previously lazily-created engine


def get_engine() -> Engine:
    """The engine to use: the injected one if set, else a lazily created one.

    Raises RuntimeError (not at import time) if neither an engine was
    injected nor a database URL is configured.
    """
    global _lazy_engine
    if _injected_engine is not None:
        return _injected_engine
    if _lazy_engine is None:
        url = settings.database_url
        if url is None:
            raise RuntimeError(
                "No database configured: call crop_rescue.configure(engine=...) "
                "or set CR_DATABASE_URL (or DATABASE_URL)."
            )
        raw_url = url.get_secret_value()
        try:
            is_async = make_url(raw_url).get_dialect().is_async
        except Exception:
            # SQLAlchemy's own message would quote the URL, and with it the password.
            raise RuntimeError("The database URL is not valid. Check CR_DATABASE_URL.") from None
        if is_async:
            raise RuntimeError(
                "The database URL uses an async driver (for example +asyncpg). "
                "Set CR_DATABASE_URL to a postgresql+psycopg:// URL instead of "
                "falling back to the host's DATABASE_URL."
            )
        _lazy_engine = create_engine(raw_url)
    return _lazy_engine
