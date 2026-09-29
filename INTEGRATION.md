# Integrating Crop Rescue into the FarmNex backend

**Read this if you did not build Crop Rescue.** It takes about 30 minutes. You need edit access to the main backend, the Supabase project of the live app, and the Flutter app.

## What you are adding

Crop Rescue is a small FastAPI module (`crop_rescue/`). It:

1. keeps a **freshness clock** for each harvested lot (the crop's shelf life, shortened by heat);
2. **alerts the farmer** before the lot spoils (status `FRESH` becomes `AT_RISK`, normally with at least 48 hours to spare);
3. suggests the **top 3 nearby buyers** for an at-risk lot.

It runs **inside your existing backend**: same server, same URL, same login, same Supabase database. There is no separate service and there are no API keys. The Flutter app calls your backend as usual.

**What it touches in your database:** it adds four new tables and one view, all named `cr_...`. It never reads, changes or deletes any existing table. Nothing existing is altered.

## The 5 steps

### 1. Add the module

Copy the `crop_rescue/` folder into the backend, for example to `backend/app/modules/crop_rescue/`. Any location works, because the module only uses relative imports.

Add these lines to the backend's dependencies (skip any it already has). FarmNex production installs from `backend/pyproject.toml`, so add them there **and** in `requirements.txt`:

```
fastapi>=0.110
pydantic>=2.6
pydantic-settings>=2.2
sqlalchemy>=2.0
psycopg[binary]>=3.1
apscheduler>=3.10,<4
httpx>=0.27
```

Do not copy `dev_app.py`, `tests/` or `docs/`. They are for running this repo on its own.

### 2. Create the tables (once, by hand)

1. Open the Supabase project of the live app, then **SQL Editor**, then **New query**.
2. Paste the whole of `migrations/001_crop_rescue.sql` and click **Run**.
3. Optional, demo only: do the same with `migrations/002_demo_seed.sql`. It adds 10 fictional buyers ("Demo Buyer 1", ...) around Pune and Nashik so the buyer suggestions have something to show. Skip it once step 5 is done.

4. **Already ran an earlier `001`?** Also run `migrations/003_lot_temperature.sql`. It adds one nullable `temperature_c` column to `cr_lots` (a fresh `001` already has it), and is safe to run twice.

FarmNex keeps its own copies of these files in `backend/migrations/` (for example `010_cr_crop_rescue.sql` and `011_cr_demo_seed.sql`). Keep them identical to the ones here; a person still runs them in Supabase by hand.

All these files only **add** `cr_` tables, indexes and a view, and are safe to run twice. **Do not re-run `001` after step 5**: it would put the demo `cr_buyer_pool` view back over your real-buyers one. To confirm, open **Table Editor**: you should see `cr_lots`, `cr_checks`, `cr_alerts` and `cr_demo_buyers`.

Nothing else creates these tables. If you skip this step, the module still starts and `/rescue/health` can still say `"db": true` (it only tests the connection), but registering a lot fails with a database error until the tables exist.

Row-level security is switched on for the four `cr_` tables with no policies. That only blocks anyone using the Supabase REST API with the anon key. Your backend is not affected as long as it connects as the table owner or another role that bypasses RLS (the Supabase `postgres` login does). With any other role the tables would look empty. It is not a substitute for the per-farmer checks in the module (see "How the farmer is identified" below).

### 3. Register the router in `main.py`

```python
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException

from app.modules import crop_rescue          # adjust to where you placed it
from app.modules.crop_rescue import router as rescue_router, start_scheduler, stop_scheduler

# FarmNex names below (User, get_current_user, /api/v2).
# Do NOT call crop_rescue.configure(engine=...) with an async engine such as FarmNex's (asyncpg); ours is sync.
# Set CR_DATABASE_URL instead (see "Database connection" below).

async def rescue_farmer_id(user: User = Depends(get_current_user)) -> str:
    if user.role is None or user.role.name != "FARMER":
        raise HTTPException(403, "Only farmers can use Crop Rescue.")
    return str(user.public_id)                # the public UUID; the internal integer id is never used

@asynccontextmanager
async def lifespan(app):
    start_scheduler()
    yield
    stop_scheduler()

app = FastAPI(lifespan=lifespan)              # or add these two calls to your existing lifespan
app.include_router(rescue_router, prefix="/api/v2", dependencies=[Depends(get_current_user)])   # your existing login check
# the farmer is always the logged-in user:
app.dependency_overrides[crop_rescue.current_farmer_id] = rescue_farmer_id
```

FarmNex's `get_current_user` (in `app/api/dependencies/current_user.py`) already returns the `User` with its role loaded. Everything in FarmNex is under `/api/v2`, so the endpoints are `/api/v2/rescue/...`. On another backend, replace `get_current_user`, the role check and the prefix with your own.

**The `dependency_overrides` line is not optional.** Without it, the module reads the farmer from a `?farmer_id=` URL parameter, which anyone could change. With it, the farmer always comes from the login and that parameter is ignored.

**Database connection.** Crop Rescue uses its own **synchronous** connection, separate from the backend's async pool. Set `CR_DATABASE_URL` in the backend's environment: Supabase dashboard, **Connect**, **Session pooler** string (port 5432), then change `postgresql://` to `postgresql+psycopg://` and end it with `?sslmode=require`. The module builds the connection the first time it is used. This is a database connection string, not an API key. Keep it in environment variables only.

**Never rely on the `DATABASE_URL` fallback, and never pass the backend's own engine.** FarmNex's `DATABASE_URL` is `postgresql+asyncpg://...`. Using it (or its engine) fails with `MissingGreenlet`. The module refuses both with a clear error message instead.

**Optional push notifications.** By default an alert is only written to `cr_alerts` and the app polls for it. To also send a push, pass a callback: `crop_rescue.configure(on_alert=my_fcm_sender)`. It receives the new alert after it is saved. The callback is synchronous and runs in the request or scheduler thread, so keep it fast (hand the push off to a background task). If it raises, the error is logged and the alert is kept.

**Several server workers?** The scheduler starts once per worker. Set `CR_ENABLE_SCHEDULER=false` on all but one, or leave it off everywhere and call `POST /rescue/check` from an external cron. Even without the scheduler, listing lots or alerts re-checks anything overdue, so a farmer never sees a stale status.

### 4. Flutter

Copy `integration/flutter/crop_rescue_api.dart` into the app (it needs only the `dio` package). Create it with the app's **existing** Dio, so the base URL and login token carry over:

```dart
final rescue = CropRescueApi(ApiClient().dio);   // FarmNex's one Dio: adds the token, refreshes on 401
```

Paths are built under `/api/v2` by default (`CropRescueApi(dio, prefix: '/api/v2')`). If your backend mounts the router somewhere else, pass that `prefix`. No method takes a farmer id, because the backend gets the farmer from the login token. Call `rescue.fetchAlerts()` on the farmer home screen every 30 seconds. Use `createLot`, `listLots`, `getLot`, `getMatches` (only works while a lot is `AT_RISK`), `markSold`, `simulate` (demo button), `markAlertRead` and `fetchCrops` for the rest.

### 5. Real buyers (later)

Until you do this, buyers come from the 10 fictional demo buyers. To use real ones, redefine the `cr_buyer_pool` view as a `SELECT` over your real buyer tables. It must return exactly these columns, with these names and in this order: `buyer_id, buyer_name, crop_code, price_per_kg, max_qty_kg, lat, lng, reliability` (`reliability` is a number from 0 to 1). No Python changes are needed. This is the only place Crop Rescue reads buyer data.

## Smoke tests (curl)

Replace `BASE` with your backend URL **including the `/api/v2` prefix** and `AUTH` with the header your backend already uses. Paths below are relative to that prefix (`/rescue/...`).

```bash
BASE=https://your-backend.example.com/api/v2
AUTH="Authorization: Bearer <a-farmer-login-token>"   # must be a FARMER account; other roles get 403
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)   # your computer's clock; if it runs ahead of the server, step 3 answers 422

# 1. Is it mounted and can it reach the database?  Expect {"ok":true,"crops":8,"db":true}
curl -H "$AUTH" $BASE/rescue/health

# 2. The 8 crops and their shelf life at 25/30/35 C
curl -H "$AUTH" $BASE/rescue/crops

# 3. Register 500 kg of tomato, harvested now.  Expect status FRESH, about 68 h left. Note the "id".
curl -X POST -H "$AUTH" -H "Content-Type: application/json" $BASE/rescue/lots \
  -d "{\"crop_code\":\"tomato\",\"quantity_kg\":500,\"harvested_at\":\"$NOW\",\"lat\":18.5204,\"lng\":73.8567,\"temperature_c\":30}"

# 4. List your lots, and open one with its check history
curl -H "$AUTH" $BASE/rescue/lots
curl -H "$AUTH" $BASE/rescue/lots/<LOT_ID>

# 5. Demo: fast-forward 36 hours.  The lot becomes AT_RISK.
curl -X POST -H "$AUTH" -H "Content-Type: application/json" $BASE/rescue/simulate \
  -d '{"hours":36,"lot_id":"<LOT_ID>"}'

# 6. The alert, then the top 3 buyers (409 if the lot is not AT_RISK; an empty list if no buyers exist, e.g. 002 was skipped)
curl -H "$AUTH" "$BASE/rescue/alerts?unread_only=true"
curl -H "$AUTH" $BASE/rescue/lots/<LOT_ID>/matches

# 7. Mark the alert read, then mark the lot sold (alerts stop)
curl -X POST -H "$AUTH" $BASE/rescue/alerts/<ALERT_ID>/read
curl -X POST -H "$AUTH" $BASE/rescue/lots/<LOT_ID>/sold

# 8. Run the engine over every open lot now (the same job the scheduler runs). Needs an ADMIN or MANAGER token, not a farmer's
curl -X POST -H "$AUTH" $BASE/rescue/check
```

A request with no or a wrong token must return 401, a login that is not a FARMER must return 403, and another farmer's lot id must return 404. Your backend's `/docs` page now has a **crop-rescue** section where each endpoint can be tried in one click.

## How the farmer is identified

Every farmer-facing endpoint takes the farmer from `current_farmer_id`, never from the request body. A lot or alert that belongs to someone else returns **404** (not 403), so other farmers' ids are not revealed. `POST /rescue/check` needs no farmer: it processes every farmer's open lots, so it must be limited to ADMIN or MANAGER accounts (FarmNex does this on the host side). The module itself does not check roles.

The module opens its own database transactions on its own connection. It never joins or interferes with a transaction your backend has open.

## Configuration (all optional)

Every setting has a default. Set an environment variable only to change one.

| Variable | Default | Meaning |
|---|---|---|
| `CR_DATABASE_URL` | none | **required on FarmNex**: `postgresql+psycopg://...:5432/postgres?sslmode=require`, never the async `DATABASE_URL` |
| `CR_ALERT_HOURS` | 48 | minimum notice before spoilage |
| `CR_CHECK_INTERVAL_HOURS` | 12 | how often lots are re-checked |
| `CR_Q10` | 2.0 | how fast heat shortens shelf life (an assumption) |
| `CR_DEFAULT_TEMP_C` | 30 | temperature when the request gives none |
| `CR_USE_OPEN_METEO` | false | look up the current temperature online (3 s timeout) |
| `CR_RADIUS_KM`, `CR_ROAD_FACTOR`, `CR_AVG_SPEED_KMPH`, `CR_LOADING_HOURS`, `CR_TRANSPORT_RS_PER_KM`, `CR_TOP_N` | 50, 1.3, 35, 2, 25, 3 | buyer matching |
| `CR_ENABLE_SCHEDULER` | true | run the background check |
| `CR_ENABLE_SIMULATE` | true | the demo fast-forward endpoint |

**Set `CR_ENABLE_SIMULATE=false` once the demo is over.** After that `/rescue/simulate` returns 404.

## Troubleshooting

- **The backend won't start after adding the module.** Settings are checked when the module is imported (fail-fast), so a bad value stops startup with a `ValidationError` that names the variable, for example `CR_Q10=abc`. Fix or remove that `CR_*` variable.
- **`/rescue/health` says `"db": false`.** The module cannot connect: `CR_DATABASE_URL` is missing or wrong (step 3).
- **Registering a lot fails with a database error, but health says `"db": true`.** The tables do not exist yet (step 2).
- **Every call returns 403 "Only farmers can use Crop Rescue."** The logged-in user is not a FARMER. Log in with a farmer account.
- **Every call returns 401 "Farmer not identified".** The `dependency_overrides` line in step 3 is missing or runs before the router is used.
- **`/rescue/lots/<id>/matches` returns 409.** The lot is not `AT_RISK` yet. That is expected.
- **Creating a lot returns 422.** `harvested_at` is in the future or has no time zone, or `crop_code` is not one of the 8 crops.
