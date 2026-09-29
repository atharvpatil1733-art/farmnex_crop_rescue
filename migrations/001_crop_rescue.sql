-- FarmNex Crop Rescue: schema migration.
--
-- Safety: this file only ADDS new `cr_`-prefixed tables, indexes and a view,
-- plus enables row-level security on the new tables. It never touches any
-- table that existed before it. It is idempotent: running it twice is a
-- no-op the second time. Wrapped in BEGIN/COMMIT so it either fully applies
-- or changes nothing.
--
-- Run this once, by hand, in the Supabase SQL editor. Nothing in this repo
-- runs it automatically against the main database.

BEGIN;

-- gen_random_uuid() is built into PostgreSQL 13+; no extension needed.

CREATE TABLE IF NOT EXISTS cr_lots (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    farmer_id           TEXT NOT NULL,
    crop_code           TEXT NOT NULL,
    quantity_kg         NUMERIC NOT NULL CHECK (quantity_kg > 0),
    harvested_at        TIMESTAMPTZ NOT NULL,
    lat                 DOUBLE PRECISION NOT NULL,
    lng                 DOUBLE PRECISION NOT NULL,
    storage_mode        TEXT NOT NULL DEFAULT 'ambient',   -- ambient | cold
    floor_price_per_kg  NUMERIC NOT NULL DEFAULT 0,
    temperature_c       DOUBLE PRECISION,                  -- given at registration; NULL = resolve at each check
    freshness_used     DOUBLE PRECISION NOT NULL DEFAULT 0,
    remaining_hours     DOUBLE PRECISION,
    spoil_eta           TIMESTAMPTZ,
    status              TEXT NOT NULL DEFAULT 'FRESH',     -- FRESH | AT_RISK | SPOILED | SOLD
    last_checked_at     TIMESTAMPTZ NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS cr_lots_farmer_id_idx ON cr_lots (farmer_id);
CREATE INDEX IF NOT EXISTS cr_lots_status_idx ON cr_lots (status);

-- Audit trail of every freshness check on a lot; powers a chart in the app.
CREATE TABLE IF NOT EXISTS cr_checks (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lot_id              UUID NOT NULL REFERENCES cr_lots (id),
    checked_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    temperature_c       DOUBLE PRECISION NOT NULL,
    temp_source         TEXT NOT NULL,                     -- request | open_meteo | default
    elapsed_hours       DOUBLE PRECISION NOT NULL,
    freshness_used      DOUBLE PRECISION NOT NULL,
    remaining_hours     DOUBLE PRECISION NOT NULL,
    status              TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS cr_checks_lot_id_idx ON cr_checks (lot_id);

-- Alerts double as an outbox: dedup_key + ON CONFLICT DO NOTHING guarantees
-- no alert is ever sent twice for the same lot and kind.
CREATE TABLE IF NOT EXISTS cr_alerts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lot_id              UUID NOT NULL REFERENCES cr_lots (id),
    farmer_id           TEXT NOT NULL,
    kind                TEXT NOT NULL,                     -- AT_RISK | SPOILED
    title               TEXT NOT NULL,
    body                TEXT NOT NULL,
    payload             JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    read_at             TIMESTAMPTZ,
    dedup_key           TEXT NOT NULL UNIQUE                -- farmer_id:lot_id:kind
);

CREATE INDEX IF NOT EXISTS cr_alerts_farmer_id_idx ON cr_alerts (farmer_id);
CREATE INDEX IF NOT EXISTS cr_alerts_lot_id_idx ON cr_alerts (lot_id);

-- DEMO DATA, NOT REAL BUYERS. In production this table is replaced by a
-- SELECT over the main app's own buyer tables, behind the cr_buyer_pool view.
CREATE TABLE IF NOT EXISTS cr_demo_buyers (
    buyer_id            TEXT PRIMARY KEY,
    buyer_name          TEXT NOT NULL,
    crop_code           TEXT NOT NULL,
    price_per_kg        NUMERIC NOT NULL,
    max_qty_kg          NUMERIC NOT NULL,
    lat                 DOUBLE PRECISION NOT NULL,
    lng                 DOUBLE PRECISION NOT NULL,
    reliability         DOUBLE PRECISION NOT NULL           -- 0..1
);

CREATE INDEX IF NOT EXISTS cr_demo_buyers_crop_code_idx ON cr_demo_buyers (crop_code);

-- The single integration seam for buyers: the Python code only ever reads
-- this view. Swap it for a SELECT over the real buyer tables later; no
-- Python changes needed.
CREATE OR REPLACE VIEW cr_buyer_pool AS
    SELECT buyer_id, buyer_name, crop_code, price_per_kg, max_qty_kg, lat, lng, reliability
    FROM cr_demo_buyers;

-- Stops the public Supabase anon key from reading these through the
-- auto-generated API. The backend connects as the database owner, so it is
-- unaffected; no policies are defined here (see INTEGRATION.md).
ALTER TABLE cr_lots ENABLE ROW LEVEL SECURITY;
ALTER TABLE cr_checks ENABLE ROW LEVEL SECURITY;
ALTER TABLE cr_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE cr_demo_buyers ENABLE ROW LEVEL SECURITY;

COMMIT;
