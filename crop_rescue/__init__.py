"""FarmNex Crop Rescue: a drop-in FastAPI router module.

Public surface: `router, start_scheduler, stop_scheduler, settings,
configure, current_farmer_id`. The host touches only these six names.
Everything else in this package is an internal implementation detail.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from . import db as _db
from . import service as _service
from .api import router
from .config import settings
from .deps import current_farmer_id
from .scheduler import start_scheduler, stop_scheduler

if TYPE_CHECKING:
    from sqlalchemy import Engine

    from .repository import AlertRecord

__all__ = [
    "router",
    "start_scheduler",
    "stop_scheduler",
    "settings",
    "configure",
    "current_farmer_id",
]


def configure(engine: "Engine | None" = None, on_alert: "Callable[[AlertRecord], None] | None" = None) -> None:
    """Wire the host's own SQLAlchemy engine and/or an alert callback (e.g. an
    FCM push) into this module. Both are optional; call with only the one
    you want to set.

        crop_rescue.configure(engine=app_engine)                # share the pool
        crop_rescue.configure(on_alert=send_fcm_push)            # optional push
    """
    if engine is not None:
        _db.configure(engine=engine)
    if on_alert is not None:
        _service.configure_on_alert(on_alert)
