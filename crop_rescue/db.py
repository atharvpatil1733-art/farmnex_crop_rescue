"""The SQLAlchemy Core engine used by `repository.py`.

The host is expected to call `configure(engine=...)` once at startup with
its own SQLAlchemy engine, so Crop Rescue shares the main backend's
connection pool. If nothing is injected, an engine is created lazily (on
first use, never at import) from `CR_DATABASE_URL`, falling back to
`DATABASE_URL`. Importing this module must never crash when the env isn't
set.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine

from .config import settings

_injected_engine: Engine | None = None
_lazy_engine: Engine | None = None


def configure(engine: Engine | None = None) -> None:
    """Inject the host's own SQLAlchemy engine, or clear a previous injection.

    Calling this with `engine=None` returns to lazy engine creation from
    config on the next call to `get_engine()`.
    """
    global _injected_engine, _lazy_engine
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
        _lazy_engine = create_engine(url.get_secret_value())
    return _lazy_engine
