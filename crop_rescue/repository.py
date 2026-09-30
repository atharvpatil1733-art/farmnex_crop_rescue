"""SQL layer. SQLAlchemy Core only (no ORM), so it can't clash with the
host's models. Every table is defined against a private `MetaData()`
instance, never the host's.

Ownership (farmer A can't touch farmer B's lot) is enforced here by always
filtering on `farmer_id`, but turning "not found" into an HTTP 404 is
`service.py`'s job, not this module's.

Never reads or joins a table that isn't `cr_`-prefixed. Buyers come only
through the `cr_buyer_pool` view.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import uuid

import sqlalchemy as sa
from sqlalchemy import Connection, Engine
from sqlalchemy.dialects.postgresql import insert as pg_insert

metadata = sa.MetaData()

# Every function takes either an Engine (runs in its own transaction) or a
# Connection (runs inside the caller's transaction, so service.py can make
# several writes commit or roll back together).
Bind = Engine | Connection


@contextmanager
def _use(bind: Bind) -> Iterator[Connection]:
    """The caller's connection as-is, or a new committed transaction for an Engine."""
    if isinstance(bind, Connection):
        yield bind
    else:
        with bind.begin() as conn:
            yield conn


cr_lots = sa.Table(
    "cr_lots",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
    sa.Column("farmer_id", sa.Text, nullable=False),
    sa.Column("crop_code", sa.Text, nullable=False),
    sa.Column("quantity_kg", sa.Numeric(asdecimal=False), nullable=False),
    sa.Column("harvested_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("lat", sa.Float, nullable=False),
    sa.Column("lng", sa.Float, nullable=False),
    sa.Column("storage_mode", sa.Text, nullable=False, server_default="ambient"),
    sa.Column("floor_price_per_kg", sa.Numeric(asdecimal=False), nullable=False, server_default="0"),
    sa.Column("temperature_c", sa.Float),
    sa.Column("freshness_used", sa.Float, nullable=False, server_default="0"),
    sa.Column("remaining_hours", sa.Float),
    sa.Column("spoil_eta", sa.DateTime(timezone=True)),
    sa.Column("status", sa.Text, nullable=False, server_default="FRESH"),
    sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
)

cr_checks = sa.Table(
    "cr_checks",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
    sa.Column("lot_id", sa.Uuid, nullable=False),
    sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    sa.Column("temperature_c", sa.Float, nullable=False),
    sa.Column("temp_source", sa.Text, nullable=False),
    sa.Column("elapsed_hours", sa.Float, nullable=False),
    sa.Column("freshness_used", sa.Float, nullable=False),
    sa.Column("remaining_hours", sa.Float, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
)

cr_alerts = sa.Table(
    "cr_alerts",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
    sa.Column("lot_id", sa.Uuid, nullable=False),
    sa.Column("farmer_id", sa.Text, nullable=False),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("title", sa.Text, nullable=False),
    sa.Column("body", sa.Text, nullable=False),
    sa.Column("payload", sa.JSON),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    sa.Column("read_at", sa.DateTime(timezone=True)),
    sa.Column("dedup_key", sa.Text, nullable=False, unique=True),
)

# Read-only: the single integration seam for buyers (see CLAUDE.md).
cr_buyer_pool = sa.Table(
    "cr_buyer_pool",
    metadata,
    sa.Column("buyer_id", sa.Text),
    sa.Column("buyer_name", sa.Text),
    sa.Column("crop_code", sa.Text),
    sa.Column("price_per_kg", sa.Numeric(asdecimal=False)),
    sa.Column("max_qty_kg", sa.Numeric(asdecimal=False)),
    sa.Column("lat", sa.Float),
    sa.Column("lng", sa.Float),
    sa.Column("reliability", sa.Float),
)


@dataclass(frozen=True)
class LotRecord:
    id: str
    farmer_id: str
    crop_code: str
    quantity_kg: float
    harvested_at: datetime
    lat: float
    lng: float
    storage_mode: str
    floor_price_per_kg: float
    temperature_c: float | None
    freshness_used: float
    remaining_hours: float | None
    spoil_eta: datetime | None
    status: str
    last_checked_at: datetime
    created_at: datetime


@dataclass(frozen=True)
class CheckRecord:
    id: str
    lot_id: str
    checked_at: datetime
    temperature_c: float
    temp_source: str
    elapsed_hours: float
    freshness_used: float
    remaining_hours: float
    status: str


@dataclass(frozen=True)
class AlertRecord:
    id: str
    lot_id: str
    farmer_id: str
    kind: str
    title: str
    body: str
    payload: dict | None
    created_at: datetime
    read_at: datetime | None
    dedup_key: str


@dataclass(frozen=True)
class BuyerRecord:
    buyer_id: str
    buyer_name: str
    crop_code: str
    price_per_kg: float
    max_qty_kg: float
    lat: float
    lng: float
    reliability: float


def _lot_from_row(row: sa.Row) -> LotRecord:
    """Convert a lot row to a record with a string ID and float quantity and price."""
    m = row._mapping
    return LotRecord(
        id=str(m["id"]),
        farmer_id=m["farmer_id"],
        crop_code=m["crop_code"],
        quantity_kg=float(m["quantity_kg"]),
        harvested_at=m["harvested_at"],
        lat=m["lat"],
        lng=m["lng"],
        storage_mode=m["storage_mode"],
        floor_price_per_kg=float(m["floor_price_per_kg"]),
        temperature_c=m["temperature_c"],
        freshness_used=m["freshness_used"],
        remaining_hours=m["remaining_hours"],
        spoil_eta=m["spoil_eta"],
        status=m["status"],
        last_checked_at=m["last_checked_at"],
        created_at=m["created_at"],
    )


def _check_from_row(row: sa.Row) -> CheckRecord:
    """Convert a freshness-check row to a record with string check and lot IDs."""
    m = row._mapping
    return CheckRecord(
        id=str(m["id"]),
        lot_id=str(m["lot_id"]),
        checked_at=m["checked_at"],
        temperature_c=m["temperature_c"],
        temp_source=m["temp_source"],
        elapsed_hours=m["elapsed_hours"],
        freshness_used=m["freshness_used"],
        remaining_hours=m["remaining_hours"],
        status=m["status"],
    )


def _alert_from_row(row: sa.Row) -> AlertRecord:
    """Convert an alert row to a record with string alert and lot IDs."""
    m = row._mapping
    return AlertRecord(
        id=str(m["id"]),
        lot_id=str(m["lot_id"]),
        farmer_id=m["farmer_id"],
        kind=m["kind"],
        title=m["title"],
        body=m["body"],
        payload=m["payload"],
        created_at=m["created_at"],
        read_at=m["read_at"],
        dedup_key=m["dedup_key"],
    )


def _buyer_from_row(row: sa.Row) -> BuyerRecord:
    """Convert a buyer-view row to a record with float price and capacity."""
    m = row._mapping
    return BuyerRecord(
        buyer_id=m["buyer_id"],
        buyer_name=m["buyer_name"],
        crop_code=m["crop_code"],
        price_per_kg=float(m["price_per_kg"]),
        max_qty_kg=float(m["max_qty_kg"]),
        lat=m["lat"],
        lng=m["lng"],
        reliability=m["reliability"],
    )


def insert_lot(
    bind: Bind,
    *,
    farmer_id: str,
    crop_code: str,
    quantity_kg: float,
    harvested_at: datetime,
    lat: float,
    lng: float,
    storage_mode: str,
    floor_price_per_kg: float,
    temperature_c: float | None,
    freshness_used: float,
    remaining_hours: float,
    spoil_eta: datetime | None,
    status: str,
    last_checked_at: datetime,
) -> LotRecord:
    """Register a new lot, already carrying the result of its first check."""
    stmt = (
        sa.insert(cr_lots)
        .values(
            farmer_id=farmer_id,
            crop_code=crop_code,
            quantity_kg=quantity_kg,
            harvested_at=harvested_at,
            lat=lat,
            lng=lng,
            storage_mode=storage_mode,
            floor_price_per_kg=floor_price_per_kg,
            temperature_c=temperature_c,
            freshness_used=freshness_used,
            remaining_hours=remaining_hours,
            spoil_eta=spoil_eta,
            status=status,
            last_checked_at=last_checked_at,
        )
        .returning(cr_lots)
    )
    with _use(bind) as conn:
        row = conn.execute(stmt).one()
    return _lot_from_row(row)


def _is_uuid(value: str) -> bool:
    """True if `value` parses as a UUID (a bad id must give "not found", not a database error)."""
    try:
        uuid.UUID(str(value))
    except ValueError:
        return False
    return True


def get_lot(bind: Bind, lot_id: str, farmer_id: str) -> LotRecord | None:
    """A lot by id, scoped to `farmer_id`. None if missing, not a UUID, or owned by someone else."""
    if not _is_uuid(lot_id):
        return None
    stmt = sa.select(cr_lots).where(cr_lots.c.id == lot_id, cr_lots.c.farmer_id == farmer_id)
    with _use(bind) as conn:
        row = conn.execute(stmt).one_or_none()
    return _lot_from_row(row) if row is not None else None


def list_lots(bind: Bind, farmer_id: str, status: str | None = None) -> list[LotRecord]:
    """All of a farmer's lots, newest first, optionally filtered by status."""
    stmt = sa.select(cr_lots).where(cr_lots.c.farmer_id == farmer_id)
    if status is not None:
        stmt = stmt.where(cr_lots.c.status == status)
    stmt = stmt.order_by(cr_lots.c.created_at.desc())
    with _use(bind) as conn:
        rows = conn.execute(stmt).all()
    return [_lot_from_row(row) for row in rows]


def list_active_lots(bind: Bind) -> list[LotRecord]:
    """Every lot the scheduler still needs to check (not SOLD or SPOILED)."""
    stmt = sa.select(cr_lots).where(cr_lots.c.status.notin_(["SOLD", "SPOILED"]))
    with _use(bind) as conn:
        rows = conn.execute(stmt).all()
    return [_lot_from_row(row) for row in rows]


def update_lot_after_check(
    bind: Bind,
    lot_id: str,
    farmer_id: str,
    *,
    freshness_used: float,
    remaining_hours: float,
    spoil_eta: datetime | None,
    status: str,
    last_checked_at: datetime,
) -> LotRecord | None:
    """Persist the result of a freshness check. None if the lot isn't found."""
    stmt = (
        sa.update(cr_lots)
        .where(cr_lots.c.id == lot_id, cr_lots.c.farmer_id == farmer_id)
        .values(
            freshness_used=freshness_used,
            remaining_hours=remaining_hours,
            spoil_eta=spoil_eta,
            status=status,
            last_checked_at=last_checked_at,
        )
        .returning(cr_lots)
    )
    with _use(bind) as conn:
        row = conn.execute(stmt).one_or_none()
    return _lot_from_row(row) if row is not None else None


def mark_lot_sold(bind: Bind, lot_id: str, farmer_id: str) -> LotRecord | None:
    """Mark a lot SOLD. None if it isn't found (or belongs to someone else)."""
    if not _is_uuid(lot_id):
        return None
    stmt = (
        sa.update(cr_lots)
        .where(cr_lots.c.id == lot_id, cr_lots.c.farmer_id == farmer_id)
        .values(status="SOLD")
        .returning(cr_lots)
    )
    with _use(bind) as conn:
        row = conn.execute(stmt).one_or_none()
    return _lot_from_row(row) if row is not None else None


def insert_check(
    bind: Bind,
    *,
    lot_id: str,
    temperature_c: float,
    temp_source: str,
    elapsed_hours: float,
    freshness_used: float,
    remaining_hours: float,
    status: str,
) -> CheckRecord:
    """Append one row to the audit trail. Never updated or deleted."""
    stmt = (
        sa.insert(cr_checks)
        .values(
            lot_id=lot_id,
            temperature_c=temperature_c,
            temp_source=temp_source,
            elapsed_hours=elapsed_hours,
            freshness_used=freshness_used,
            remaining_hours=remaining_hours,
            status=status,
        )
        .returning(cr_checks)
    )
    with _use(bind) as conn:
        row = conn.execute(stmt).one()
    return _check_from_row(row)


def insert_alert(
    bind: Bind,
    *,
    lot_id: str,
    farmer_id: str,
    kind: str,
    title: str,
    body: str,
    payload: dict | None,
    dedup_key: str,
) -> AlertRecord | None:
    """Insert an alert, or do nothing if `dedup_key` already exists.

    Returns None on a duplicate, so the caller knows not to notify twice.
    """
    stmt = (
        pg_insert(cr_alerts)
        .values(
            lot_id=lot_id,
            farmer_id=farmer_id,
            kind=kind,
            title=title,
            body=body,
            payload=payload,
            dedup_key=dedup_key,
        )
        .on_conflict_do_nothing(index_elements=[cr_alerts.c.dedup_key])
        .returning(cr_alerts)
    )
    with _use(bind) as conn:
        row = conn.execute(stmt).one_or_none()
    return _alert_from_row(row) if row is not None else None


def list_alerts(bind: Bind, farmer_id: str, unread_only: bool = False) -> list[AlertRecord]:
    """A farmer's alerts, newest first."""
    stmt = sa.select(cr_alerts).where(cr_alerts.c.farmer_id == farmer_id)
    if unread_only:
        stmt = stmt.where(cr_alerts.c.read_at.is_(None))
    stmt = stmt.order_by(cr_alerts.c.created_at.desc())
    with _use(bind) as conn:
        rows = conn.execute(stmt).all()
    return [_alert_from_row(row) for row in rows]


def mark_alert_read(bind: Bind, alert_id: str, farmer_id: str, read_at: datetime) -> AlertRecord | None:
    """Mark one of a farmer's alerts read. None if it isn't found."""
    if not _is_uuid(alert_id):
        return None
    stmt = (
        sa.update(cr_alerts)
        .where(cr_alerts.c.id == alert_id, cr_alerts.c.farmer_id == farmer_id)
        .values(read_at=read_at)
        .returning(cr_alerts)
    )
    with _use(bind) as conn:
        row = conn.execute(stmt).one_or_none()
    return _alert_from_row(row) if row is not None else None


def list_checks_for_lot(bind: Bind, lot_id: str) -> list[CheckRecord]:
    """A lot's full audit trail, newest first."""
    stmt = sa.select(cr_checks).where(cr_checks.c.lot_id == lot_id).order_by(cr_checks.c.checked_at.desc())
    with _use(bind) as conn:
        rows = conn.execute(stmt).all()
    return [_check_from_row(row) for row in rows]


def list_buyers_for_crop(bind: Bind, crop_code: str) -> list[BuyerRecord]:
    """Candidate buyers for a crop, read only from `cr_buyer_pool`."""
    stmt = sa.select(cr_buyer_pool).where(cr_buyer_pool.c.crop_code == crop_code)
    with _use(bind) as conn:
        rows = conn.execute(stmt).all()
    return [_buyer_from_row(row) for row in rows]
