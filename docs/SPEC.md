# SPEC — FarmNex Crop Rescue (detailed spec)

The always-on rules live in CLAUDE.md. This file holds the detail. **Read only the sections your current phase needs** (docs/BUILD_PLAN.md lists them per phase). Where this file says "the Database safety rules", it means that section of CLAUDE.md.

## Crop data (the only source of shelf-life numbers)

**Source:** Hardenburg, Watada & Wang (1986), *The Commercial Storage of Fruits, Vegetables, and Florist and Nursery Stocks*, USDA-ARS Agriculture Handbook 66. Reproduced as Table 1 in University of Maine Cooperative Extension Bulletin #4135 (reprinted from Kansas State University): https://extension.umaine.edu/publications/4135e/

The table gives storage life **at the recommended storage temperature**. We take the **lower bound** of each range, which is the conservative choice and favours alerting early. `ref_temp_c` is the midpoint of the recommended range, converted from °F.

| code | name (EN / MR) | Table 1 row | Recommended °F | ref_temp_c | Storage life in table | ref_life_hours |
|---|---|---|---|---|---|---|
| `tomato` | Tomato / टोमॅटो | Tomatoes, mature green | 55–70 | 17.0 | 1–3 weeks | 168 |
| `spinach` | Spinach / पालक | Spinach | 32 | 0.0 | 10–14 days | 240 |
| `okra` | Okra / भेंडी | Okra | 45–50 | 8.6 | 7–10 days | 168 |
| `brinjal` | Brinjal / वांगी | Eggplant | 46–54 | 10.0 | 1 week | 168 |
| `cauliflower` | Cauliflower / फुलकोबी | Cauliflower | 32 | 0.0 | 3–4 weeks | 504 |
| `grapes` | Grapes / द्राक्षे | Grapes, American | 31–32 | -0.3 | 2–8 weeks | 336 |
| `capsicum` | Capsicum / ढोबळी मिरची | Peppers, sweet | 45–55 | 10.0 | 2–3 weeks | 336 |
| `cucumber` | Cucumber / काकडी | Cucumbers | 50–55 | 11.4 | 10–14 days | 240 |

These are already in `crop_rescue/data/crops.json`.

**Known limitations** (state these in the README and do not hide them):
- The grapes row in the handbook is for American (labrusca) grapes. Maharashtra grows mainly vinifera table grapes, so treat this as an approximation. The lower bound keeps it conservative.
- Onion and potato are left out on purpose. They are storage crops that last months when cured, and they are not the Crop Rescue use case.

---

## Algorithm (keep it exactly this simple)

### 1. Shelf life at a temperature: Q10 rule — `core/shelf_life.py`

```
life_hours(T) = ref_life_hours / Q10 ** ((T - ref_temp_c) / 10)
```

- `Q10` defaults to `CR_Q10 = 2.0`. **This is a modelling assumption, not measured data.** Label it that way in the README and in `/rescue/crops`. The common rule of thumb for produce is 2–3; we pick the conservative end.
- If `T <= ref_temp_c` (cold storage), use `ref_life_hours`. Never extend life beyond the handbook value.

### 2. Freshness accumulation: runs on every check

Each lot stores `freshness_used`, a fraction from 0 to 1 where 1 means spoiled.

```
freshness_used += elapsed_hours / life_hours(T_during_interval)
remaining_hours  = max(0, (1 - freshness_used) * life_hours(T_now))
spoil_eta        = now + remaining_hours
```

Accumulation (rather than simply subtracting hours) is what lets a hot day eat freshness faster than a cool night. That is the one idea judges should take away.

### 3. Status rules — `core/status.py`

Let `ALERT_H = CR_ALERT_HOURS` (48) and `INTERVAL_H = CR_CHECK_INTERVAL_HOURS` (12).

| Condition | Status |
|---|---|
| `remaining_hours <= 0` | `SPOILED` |
| `remaining_hours <= ALERT_H + INTERVAL_H` | `AT_RISK` → fire the rescue alert **once** |
| otherwise | `FRESH` |

**Why `48 + 12`:** checks run every 12 hours, so a lot at 55 hours at this check would be at 43 hours by the next one. Alerting at 60 hours or less guarantees the farmer gets **at least 48 hours of notice**. Put this sentence in the README.

When a lot is registered and its total life at the current temperature is already under 60 hours (for example spinach on a hot day), it goes `AT_RISK` immediately. That is correct behaviour, and it is a good demo point: leafy greens can't wait.

`storage_mode` is either `ambient` or `cold`. In `cold` mode, `T = ref_temp_c`. This shows judges the value of the cold chain in one toggle.

### 4. Temperature source

In priority order:
1. `temperature_c` passed in the request (check or simulate)
2. Open-Meteo current temperature for the lot's lat/lng, **only if `CR_USE_OPEN_METEO=true`**. Use a 3-second timeout and fall back on any error.
3. `CR_DEFAULT_TEMP_C` (default `30.0`, a stated assumption for a Pune-area afternoon)

Record which source was used on each check (`temp_source` column) so the demo can show it.

### 5. Rescue matching — `core/matching.py`

Input: an at-risk lot plus candidate rows from the `cr_buyer_pool` view where `crop_code` matches.

1. **Distance:** haversine km, multiplied by `CR_ROAD_FACTOR` (1.3) to approximate road distance. Drop buyers beyond `CR_RADIUS_KM` (50).
2. **Time-feasible:** `travel_h = road_km / CR_AVG_SPEED_KMPH (35) + CR_LOADING_HOURS (2)`. Drop the buyer if `travel_h >= remaining_hours`.
3. **Net price per kg:** `price_per_kg - (road_km * CR_TRANSPORT_RS_PER_KM (25)) / qty_kg`, where `qty_kg = min(lot qty, buyer max_qty_kg)`.
4. **Floor:** drop the buyer if `net_price < lot.floor_price_per_kg`. This stops buyers from waiting for panic prices.
5. **Score** (weights come from config; min-max normalise across candidates):
   `0.5*net_price + 0.2*time_margin + 0.2*reliability + 0.1*qty_fit`
   - `time_margin = (remaining_hours - travel_h) / remaining_hours`
   - `qty_fit = qty_kg / lot.qty_kg`
6. Return the top `CR_TOP_N` (3). Each result includes a one-line plain-English `reason`, for example "₹18.4/kg after transport, 12 km away, reaches with 30 h to spare".

No partial allocation across multiple buyers. It is out of scope.

---

## Database — `migrations/001_crop_rescue.sql`

These tables go into the **same Supabase PostgreSQL project the main backend already uses**. Run the SQL once in the Supabase SQL editor. The `cr_` prefix keeps them apart from the existing tables.

```sql
cr_lots (
  id UUID PK DEFAULT gen_random_uuid(),
  farmer_id TEXT NOT NULL,
  crop_code TEXT NOT NULL,
  quantity_kg NUMERIC NOT NULL CHECK (quantity_kg > 0),
  harvested_at TIMESTAMPTZ NOT NULL,
  lat DOUBLE PRECISION NOT NULL, lng DOUBLE PRECISION NOT NULL,
  storage_mode TEXT NOT NULL DEFAULT 'ambient',   -- ambient | cold
  floor_price_per_kg NUMERIC NOT NULL DEFAULT 0,
  freshness_used DOUBLE PRECISION NOT NULL DEFAULT 0,
  remaining_hours DOUBLE PRECISION,
  spoil_eta TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'FRESH',           -- FRESH | AT_RISK | SPOILED | SOLD
  last_checked_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
cr_checks (id, lot_id FK, checked_at, temperature_c, temp_source, elapsed_hours,
           freshness_used, remaining_hours, status)            -- audit trail, powers a chart
cr_alerts (id, lot_id FK, farmer_id, kind TEXT,               -- 'AT_RISK' | 'SPOILED'
           title, body, payload JSONB, created_at, read_at NULL,
           dedup_key TEXT UNIQUE)                              -- farmer_id:lot_id:kind
cr_demo_buyers (buyer_id, buyer_name, crop_code, price_per_kg, max_qty_kg,
                lat, lng, reliability)                          -- DEMO data only
CREATE VIEW cr_buyer_pool AS SELECT buyer_id, buyer_name, crop_code, price_per_kg,
       max_qty_kg, lat, lng, reliability FROM cr_demo_buyers;
```

All statements are idempotent (`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `CREATE OR REPLACE VIEW` on `cr_` views only), so running the file twice is safe. Wrap the file in `BEGIN; ... COMMIT;` so it either fully applies or changes nothing. The only other statement allowed is `ALTER TABLE cr_<name> ENABLE ROW LEVEL SECURITY;` on the new `cr_` tables. This stops the public Supabase anon key from reading them through Supabase's auto-generated API. The backend connects directly as the database owner, so it is unaffected, and no policies are needed.

`002_demo_seed.sql` inserts **only** into `cr_demo_buyers`, with `ON CONFLICT DO NOTHING`.

**`cr_buyer_pool` is the single integration seam for buyers.** In the real app the team replaces this view with a `SELECT` over the main app's buyer tables. The Python code only ever reads the view.

`cr_alerts` doubles as an **outbox**. `dedup_key UNIQUE` plus `INSERT ... ON CONFLICT DO NOTHING` guarantees that no alert is sent twice.

Demo buyers: about 10 rows around Pune, Nashik and Chakan with coordinates, spread across the 8 crops. Add a SQL comment `-- DEMO DATA, NOT REAL BUYERS` and use obviously fictional names such as "Demo Buyer 1 (Hadapsar)". Pick prices that look plausible but are clearly labelled as demo values.

---

## Database connection

- `configure(engine=...)` lets the host pass in **its own SQLAlchemy engine**, so Crop Rescue shares the main backend's connection pool. This is the preferred setup.
- If no engine is passed, create one lazily (on first use, never at import) from `CR_DATABASE_URL`, falling back to `DATABASE_URL`.
- The Supabase URL needs the `postgresql+psycopg://` driver prefix and `?sslmode=require`. Where to find it: Supabase dashboard → **Connect** → **Session pooler** string, then change `postgresql://` to `postgresql+psycopg://`. This is the database connection string. The Supabase anon and service API keys are not needed.
- Tests use `CR_TEST_DATABASE_URL` only (see the Database safety rules).

---

## Who is the farmer (ownership)

`crop_rescue/deps.py` defines one FastAPI dependency:

```python
def current_farmer_id(farmer_id: str | None = Query(None, description="Dev/demo only")) -> str:
    """Default: reads ?farmer_id= (for local testing and the demo).
    In the main backend this is overridden to return the logged-in user's id."""
    if not farmer_id:
        raise HTTPException(401, "Farmer not identified")
    return farmer_id
```

Every farmer-facing endpoint gets the farmer from `Depends(current_farmer_id)`, **never from the request body**. In the main backend, one line replaces it with the real login:

```python
app.dependency_overrides[crop_rescue.current_farmer_id] = lambda user=Depends(get_current_user): str(user.id)
```

After that the `?farmer_id=` query parameter is ignored, and the farmer is always the logged-in user.

**Ownership rule:** `/rescue/lots/{id}`, `/matches`, `/sold` and `/alerts/{id}/read` return **404** if the lot or alert belongs to another farmer. Use 404 rather than 403 so other farmers' lot ids aren't revealed. This check lives in `service.py`.

---

## API contract — `APIRouter(prefix="/rescue", tags=["crop-rescue"])`

Once mounted, these live at `https://<main-backend-url>/rescue/...` and show up in the main backend's existing `/docs` under a **crop-rescue** section.

| Method | Path | Purpose |
|---|---|---|
| GET | `/rescue/health` | `{ok, crops: 8, db: true}` |
| GET | `/rescue/crops` | the 8 crops plus life at 25/30/35 °C, with the source and the Q10 assumption |
| POST | `/rescue/lots` | register a lot for the **current farmer**. Body: `crop_code, quantity_kg, harvested_at, lat, lng, storage_mode?, floor_price_per_kg?, temperature_c?` (no `farmer_id` in the body). Runs the first check immediately and returns the lot. |
| GET | `/rescue/lots` | the current farmer's lots with status, remaining_hours and spoil_eta |
| GET | `/rescue/lots/{id}` | one of the current farmer's lots plus its `checks` history (404 if not theirs) |
| GET | `/rescue/lots/{id}/matches` | top 3 buyers (404 if not theirs, 409 if the lot is not AT_RISK) |
| POST | `/rescue/lots/{id}/sold` | mark SOLD so it stops alerting (404 if not theirs) |
| POST | `/rescue/check` | run the engine over all open lots now (the same job the scheduler runs). Needs no farmer. |
| POST | `/rescue/simulate` | **demo button.** Body: `hours` (e.g. 24), `temperature_c?`, `lot_id?`. Advances the **current farmer's** lots (or that one lot) by `hours` without waiting, then runs the status rules and alerts. Returns **404 when `CR_ENABLE_SIMULATE=false`**, so it can be switched off after the demo. |
| GET | `/rescue/alerts?unread_only=true` | the current farmer's alerts. Flutter polls this every 30 s on the farmer home screen. |
| POST | `/rescue/alerts/{id}/read` | mark read (404 if not theirs) |

- Endpoints are plain sync `def` (FastAPI runs them in a threadpool), so they work whether the host is sync or async.
- Every endpoint has a `summary` and `description`, and every request model has `json_schema_extra` examples, so "Try it out" in `/docs` works in one click for judges.
- Times are ISO 8601 UTC. Money is ₹ per kg. Hours are rounded to one decimal place in responses.
- Errors use `{"detail": "..."}` (FastAPI default) with sensible 404/409/422 codes.
- The AT_RISK alert body is a sentence a farmer can read, for example: "Your 500 kg tomato lot has about 52 hours left. 3 buyers near you can take it. Tap to see offers." The `payload` contains `lot_id`, `remaining_hours` and the top-3 matches.

**Push notifications (FCM) are optional.** `configure(on_alert=callback)` lets the host send an FCM push when an alert is created. By default the component only writes to `cr_alerts`, and Flutter polls. Do not add a Firebase dependency.

---

## Config (`CR_` env vars, all with defaults)

`CR_DATABASE_URL` (falls back to `DATABASE_URL`), `CR_CHECK_INTERVAL_HOURS=12`, `CR_ALERT_HOURS=48`, `CR_Q10=2.0`, `CR_DEFAULT_TEMP_C=30`, `CR_USE_OPEN_METEO=false`, `CR_RADIUS_KM=50`, `CR_ROAD_FACTOR=1.3`, `CR_AVG_SPEED_KMPH=35`, `CR_LOADING_HOURS=2`, `CR_TRANSPORT_RS_PER_KM=25`, `CR_TOP_N=3`, `CR_ENABLE_SCHEDULER=true`, `CR_ENABLE_SIMULATE=true` (set it to `false` after the demo). For tests only: `CR_TEST_DATABASE_URL`.

The host only needs to set these if it wants to change a default.

---

## Scheduler

`start_scheduler()` and `stop_scheduler()` use APScheduler's `BackgroundScheduler` with one interval job that calls the same function as `POST /rescue/check`. The job runs in a background thread, so it never blocks API requests. The host calls these two functions from its existing `lifespan`. Make the job idempotent (dedup keys). Log one line per run: `checked=N at_risk=M spoiled=K`.

**Crash-proof:** wrap the whole job body in `try/except Exception`, log the error with `logger.exception`, and return. A failed run must never stop the scheduler or the host backend. Also set `max_instances=1` and `coalesce=True` so runs never pile up.

If the host runs multiple workers, set `CR_ENABLE_SCHEDULER=false` on all but one, or trigger `/rescue/check` from an external cron.

**Check-on-read safety net:** a hosted backend may sleep when idle, which would skip scheduler runs. So `GET /rescue/lots` and `GET /rescue/alerts` first run the check if the newest `cr_checks.checked_at` is older than `CR_CHECK_INTERVAL_HOURS`. The farmer can never see a stale status, even if the background job didn't run. Keep this to about 5 lines in `service.py`.

---

## Local development (`dev_app.py`)

A 15-line FastAPI app that does `include_router(router)` plus the scheduler lifespan. It exists **only** so this repo can be run and tested on its own with `CR_DATABASE_URL=$CR_TEST_DATABASE_URL uvicorn dev_app:app --reload`. **Always point it at the test database, never the main Supabase one.** It is never copied into the main backend and never deployed.

---

## Tests (pytest) — must pass before done

- `shelf_life`: cold (`T <= ref`) returns `ref_life_hours`; +10 °C halves life when Q10=2; the table values match crops.json.
- Accumulation: 12 h at 20 °C then 12 h at 35 °C uses more freshness than 24 h at 20 °C.
- Status: 61 h → FRESH, 60 h → AT_RISK, 0 → SPOILED. The alert fires once only (a second check creates no duplicate).
- The "at least 48 h notice" property: simulate a lot through 12-hour steps at a constant temperature and assert that the first AT_RISK alert happens with `remaining_hours >= 48`.
- Matching: buyers beyond the radius, buyers that are too slow, and buyers below the floor are all excluded. The ordering follows the score. Returns at most 3.
- API: create lot → simulate 36 h → alert appears → matches return 3 → sold → no more alerts.
- Mounting: a fresh FastAPI app with `include_router(router, dependencies=[Depends(fake_auth)])` rejects requests when `fake_auth` raises 401. This proves the host's auth wraps it correctly.
- Ownership: with `current_farmer_id` overridden to farmer A, farmer B's lot returns 404 on get, matches, sold and alert read. Listing shows only A's lots. `farmer_id` in a POST body is ignored or rejected.
- Nested placement: copy `crop_rescue/` to `tmp/app/modules/crop_rescue/`, then `from app.modules.crop_rescue import router` and mount it. It must work, which proves imports are relative.
- Scheduler safety: make the repository raise inside the job and assert the job logs and returns without raising.
- Simulate switch: with `CR_ENABLE_SIMULATE=false`, `/rescue/simulate` → 404.
- Migration safety (`tests/test_migrations_safe.py`): no forbidden statement and no object without the `cr_` prefix in any `.sql` file. Needs no database.
- **DB tests use only `CR_TEST_DATABASE_URL`** (a real Postgres, e.g. the docker `db` service; **no SQLite**). If it isn't set, skip them with a clear message. Never fall back to the main Supabase URL.

---

## Demo script (put it in README)

0. Open the **main backend's** `/docs` and scroll to the **crop-rescue** section, or use the Flutter app.
1. Register 500 kg of tomato, ambient, 30 °C, harvested now. Status is FRESH with about 68 h left.
2. Register the same tomato in **cold** mode. It stays FRESH with 168 h. *"Cold chain buys you days."*
3. Register spinach at 30 °C. It goes AT_RISK immediately. *"Leafy greens can't wait."*
4. Press **Simulate +12 h** on the ambient tomato lot. It crosses 60 h, goes AT_RISK, and the alert shows up in the farmer app with 3 buyers and reasons.
5. The farmer taps a buyer and marks the lot SOLD. Alerts stop.

---

## INTEGRATION.md must contain exactly these 5 steps

1. **Add the module** to the main backend, for example at `app/modules/crop_rescue/` (any location works because imports are relative). Add the runtime lines from `requirements.txt` to the backend's requirements.
2. **Create the tables:** open the main app's Supabase project → SQL Editor → run `migrations/001_crop_rescue.sql`, then `002_demo_seed.sql` for the demo buyers. These only **add** new `cr_` tables. Nothing existing is changed.
3. **Register the router** in the backend's `main.py`:
   ```python
   from app.modules import crop_rescue   # adjust to where you placed it
   from app.modules.crop_rescue import router as rescue_router, start_scheduler, stop_scheduler

   crop_rescue.configure(engine=engine)   # reuse the backend's existing SQLAlchemy engine (optional)

   @asynccontextmanager
   async def lifespan(app):
       start_scheduler()
       yield
       stop_scheduler()

   app = FastAPI(lifespan=lifespan)       # or add these two calls to the existing lifespan
   app.include_router(rescue_router, dependencies=[Depends(get_current_user)])  # existing login check
   # the farmer is always the logged-in user:
   app.dependency_overrides[crop_rescue.current_farmer_id] = lambda user=Depends(get_current_user): str(user.id)
   ```
4. **Flutter:** copy `integration/flutter/crop_rescue_api.dart` into the app. Create it with the app's existing Dio, `CropRescueApi(dio)`, so the base URL and login token carry over. Call `fetchAlerts(farmerId)` on the farmer home screen every 30 s.
5. **Real buyers (later):** redefine the `cr_buyer_pool` view as a `SELECT` over the main app's real buyer tables. No Python changes are needed.

Also include a `curl` smoke test for each endpoint against the main backend URL, using whatever auth header the backend already uses. Add a note: set `CR_ENABLE_SIMULATE=false` once the demo is over.

---

