-- FarmNex Crop Rescue: demo buyer seed data.
--
-- DEMO DATA, NOT REAL BUYERS. Fictional names and prices for the SIH demo
-- only. Inserts only into cr_demo_buyers, with ON CONFLICT DO NOTHING, so
-- running this file twice never duplicates rows and never touches anything
-- else. Run 001_crop_rescue.sql first.

BEGIN;

INSERT INTO cr_demo_buyers (buyer_id, buyer_name, crop_code, price_per_kg, max_qty_kg, lat, lng, reliability)
VALUES
    ('demo-buyer-1', 'Demo Buyer 1 (Hadapsar)',        'tomato',      20.0, 400, 18.5089, 73.9260, 0.90),
    ('demo-buyer-2', 'Demo Buyer 2 (Pimpri)',          'tomato',      18.5, 600, 18.6298, 73.7997, 0.80),
    ('demo-buyer-3', 'Demo Buyer 3 (Chakan)',          'spinach',     15.0, 250, 18.7578, 73.8590, 0.85),
    ('demo-buyer-4', 'Demo Buyer 4 (Market Yard)',     'okra',        22.0, 300, 18.4930, 73.8560, 0.75),
    ('demo-buyer-5', 'Demo Buyer 5 (Hadapsar)',        'brinjal',     16.0, 350, 18.5089, 73.9260, 0.88),
    ('demo-buyer-6', 'Demo Buyer 6 (Nashik Road)',     'cauliflower', 14.0, 500, 19.9975, 73.7898, 0.70),
    ('demo-buyer-7', 'Demo Buyer 7 (Nashik)',          'grapes',      45.0, 800, 20.0059, 73.7910, 0.92),
    ('demo-buyer-8', 'Demo Buyer 8 (Chakan)',          'capsicum',    28.0, 300, 18.7578, 73.8590, 0.78),
    ('demo-buyer-9', 'Demo Buyer 9 (Market Yard)',     'cucumber',    12.0, 400, 18.4930, 73.8560, 0.82),
    ('demo-buyer-10', 'Demo Buyer 10 (Pimpri)',        'tomato',      21.0, 300, 18.6298, 73.7997, 0.95)
ON CONFLICT (buyer_id) DO NOTHING;

COMMIT;
