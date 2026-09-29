# Crop Rescue demo transcript

Farmer `demo-farmer-1`, test database, temperature 30 C.
Recorded by `pytest tests/test_demo.py` in GitHub Actions (CI run for commit 1a2fec8) against a throwaway Postgres. Times and ids differ per run.


## 1. Tomato 500 kg, ambient, 30 C: PASS
- status=FRESH remaining_hours=68.2 spoil_eta=2026-10-02T00:05:22.597134Z
- check `status FRESH`: ok
- check `about 68 h left`: ok

## 2. Same tomato, cold storage: PASS
- status=FRESH remaining_hours=168.0
- check `status FRESH`: ok
- check `168 h left`: ok

## 3. Spinach at 30 C: PASS
- status=AT_RISK remaining_hours=30.0
- check `status AT_RISK at once`: ok

## 4. Simulate +12 h on the ambient tomato: PASS
- status=AT_RISK remaining_hours=56.2
- alert: Your 500 kg tomato lot needs a buyer soon
- buyer: Demo Buyer 1 (Hadapsar): ₹19.4/kg after transport · 7 km · 54 h to spare
- buyer: Demo Buyer 10 (Pimpri): ₹19.5/kg after transport · 14 km · 54 h to spare
- buyer: Demo Buyer 2 (Pimpri): ₹17.6/kg after transport · 14 km · 54 h to spare
- check `status AT_RISK`: ok
- check `one alert for the lot`: ok
- check `3 buyers`: ok
- check `each buyer has a reason`: ok

## 5. Mark the tomato SOLD: PASS
- alerts before=2, after another +24 h and a check=2
- check `sold accepted`: ok
- check `no new alert for the sold lot`: ok

## Extra. Another farmer cannot see the lot: PASS
- demo-farmer-2 GET lot -> 404
- check `404`: ok
- check `empty list`: ok
