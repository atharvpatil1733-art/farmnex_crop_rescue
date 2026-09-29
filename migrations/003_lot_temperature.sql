-- FarmNex Crop Rescue: keep the temperature the farmer gave at registration.
--
-- Safety: adds one nullable column to our own cr_lots table, nothing else.
-- Idempotent (IF NOT EXISTS), wrapped in BEGIN/COMMIT. Run by hand in the
-- Supabase SQL editor after 001.

BEGIN;

ALTER TABLE cr_lots ADD COLUMN IF NOT EXISTS temperature_c DOUBLE PRECISION;

COMMIT;
