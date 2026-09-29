# FarmNex Crop Rescue

**The problem.** Vegetables and fruit spoil within days, and farmers usually find out when it is too late to sell them at a fair price.
**Our answer.** A freshness clock for every harvested lot: it warns the farmer **at least 48 hours before spoilage** (for any lot registered with more than 60 hours of life left) and suggests the **3 best nearby buyers**, with a one-line reason for each.

It is a small FastAPI **router module** (`crop_rescue/`). It is copied into the existing FarmNex backend and mounted with `app.include_router(...)`. It runs in the same server, uses the same login and the same Supabase database (its own `cr_` tables), and needs no separate service and no API keys. See [INTEGRATION.md](INTEGRATION.md) for the 5 steps.

## How it works, in plain words

**1. Every crop has a known shelf life.** Government-published storage tables say how long each crop lasts at its ideal temperature. For example, mature green tomatoes last about 7 days (168 hours) at 17 °C; ripe tomatoes will last less. We use 8 crops: tomato, spinach, okra, brinjal, cauliflower, grapes, capsicum and cucumber. The numbers live in `crop_rescue/data/crops.json` and nothing else feeds the clock.

**2. Heat shortens it.** Produce ages faster in the heat. A common rule of thumb says every **10 °C hotter roughly halves** the shelf life. So that tomato lasts about 96 hours at 25 °C and about 68 hours at 30 °C. We never make life *longer* than the table says, so cold storage caps at the table value.

**3. We add up freshness, hour by hour.** Think of a fuel tank. Each lot starts full. Every hour a hot day empties it faster than a cool night. At each check we work out how much of the tank was used since the last check, at the temperature of that period, and how many hours are left at today's temperature. The clock starts at **harvest time**, not registration time, because produce starts ageing when it leaves the field.

**4. We warn early enough.** The lot is checked every 12 hours. If we only warned at exactly 48 hours left, a lot with 55 hours left now would have 43 hours left at the next check, and the farmer would get less than 48 hours of notice. So we raise the alert at **48 + 12 = 60 hours or less**. The farmer therefore gets at least 48 hours of notice, as long as the lot had more than 60 hours left when registered and the temperature stays about the same between checks. The status moves `FRESH` then `AT_RISK` (alert sent once) then `SPOILED`.

**5. We find buyers who can actually take it.** For an at-risk lot we look at nearby buyers of that crop and drop any who are:
- too far (more than 50 km by road),
- too slow (the trip plus loading would take longer than the lot has left),
- below the farmer's minimum price after paying for transport.

Those left are scored, after each measure is scaled to 0-1 across the candidates: **50% net price** (price minus transport cost per kg), **20% spare time**, **20% buyer reliability**, **10% how much of the lot they can take**. The top 3 are shown with a reason such as *"₹18.4/kg after transport · 12 km (straight line) · 30 h to spare"*.

Everything is rule-based and can be explained on one page. There is no machine learning, so every number can be traced.

### The formulas (for the curious)

```
shelf life at T  = ref_life / 2 ** ((T - ref_temp) / 10)     (T above ref_temp; otherwise ref_life)
freshness used  += hours since last check / shelf life at that period's temperature
hours left       = (1 - freshness used) * shelf life at today's temperature
AT_RISK when hours left <= 48 + 12
```

Code: `crop_rescue/core/shelf_life.py`, `status.py`, `matching.py`. These are pure functions with no database and no clock, so they are easy to test.

## Source of the numbers

Shelf lives come from **USDA Agriculture Handbook 66**: Hardenburg, Watada and Wang (1986), *The Commercial Storage of Fruits, Vegetables, and Florist and Nursery Stocks*. We used the table as reproduced in University of Maine Cooperative Extension Bulletin #4135: https://extension.umaine.edu/publications/4135e/

The table gives storage life at the recommended storage temperature. We take the **lower bound** of each range, which is the cautious choice and favours alerting early. The reference temperature is the middle of the recommended range, converted from °F.

## Assumptions (please read)

The handbook does not say how shelf life changes with temperature, and we do not have real buyers yet. These values are **our modelling choices, not measured data**. Each can be changed with an environment variable, except the score weights, which are constants in `core/matching.py`.

| Assumption | Value | Why | Variable |
|---|---|---|---|
| **Q10**: how much faster produce ages per 10 °C | 2.0 | Rule of thumb for produce is 2 to 3; we take the lower end, which is the optimistic one (a higher Q10 would alert earlier). Not measured for each crop. | `CR_Q10` |
| **Default temperature** when none is given | 30 °C | A Pune-area afternoon. Live temperature (Open-Meteo, 3 s timeout) is optional and off by default. | `CR_DEFAULT_TEMP_C` |
| **Demo buyers** | 10 fictional buyers | Names, prices and locations around Pune and Nashik are invented for the demo (`migrations/002_demo_seed.sql`). Real buyers replace them by redefining one view. | `cr_buyer_pool` view |
| **Transport cost** | ₹25 per km | A flat guess for a small load. | `CR_TRANSPORT_RS_PER_KM` |
| **Average speed** | 35 km/h | A guess for Maharashtra rural roads. | `CR_AVG_SPEED_KMPH` |
| **Loading time** | 2 hours | A guess for loading and unloading. | `CR_LOADING_HOURS` |
| **Road factor** | 1.3 | Road distance is taken as 1.3 times the straight line. No maps service is called. | `CR_ROAD_FACTOR` |
| **Search radius** | 50 km | Beyond this, produce would not arrive fresh. | `CR_RADIUS_KM` |
| **Alert notice / check interval** | 48 h / 12 h | The 48-hour promise and how often lots are re-checked. | `CR_ALERT_HOURS`, `CR_CHECK_INTERVAL_HOURS` |
| **Score weights** | 50 / 20 / 20 / 10 % | Price matters most to the farmer. | constants in `core/matching.py` |

### Known limitations

- **Grapes:** the handbook row is for American (*labrusca*) grapes. Maharashtra grows mainly *vinifera* table grapes, so this is an approximation. The lower bound keeps it cautious.
- **Onion and potato** are left out on purpose: cured, they keep for months and are not a rescue case.
- **Very perishable lots:** a lot registered with under 60 hours of life left (for example spinach on a hot day, demo step 3) is alerted at once with whatever time remains. It cannot be given 48 hours it does not have.
- **The 48-hour promise assumes a roughly steady temperature** between checks. A sudden heat wave inside a 12-hour window can use freshness faster than the check assumes. The next check catches it.
- One temperature per check, for the whole lot. No humidity, ripeness or handling damage.
- Buyer prices are fixed offers. There is no live market feed and no partial sale across several buyers.

## Try it

```bash
pip install -r requirements.txt
docker compose up -d db          # throwaway Postgres for tests and the demo, never the main database
export CR_TEST_DATABASE_URL=postgresql+psycopg://farmnex:farmnex@localhost:5433/crop_rescue_test
pytest -q                        # all tests; database tests need the line above
pytest tests/test_demo.py -s     # replays the demo below with a PASS/FAIL per step
```

To click through it by hand, apply `migrations/001_crop_rescue.sql` and `002_demo_seed.sql` to the test database, then run `CR_DATABASE_URL=$CR_TEST_DATABASE_URL uvicorn dev_app:app` and open http://localhost:8000/docs. In this local app the farmer is the `?farmer_id=` parameter; in the main backend it always comes from the login. **Never point the local app at the main Supabase database.**

## Demo script (5 steps)

Open the main backend's `/docs` and scroll to the **crop-rescue** section (or use the Flutter app). A recorded run is in [docs/demo_transcript.md](docs/demo_transcript.md).

1. **Register 500 kg of tomato**, ambient, 30 °C, harvested now. Status is `FRESH` with about **68 hours** left.
2. **Register the same tomato in cold storage.** It stays `FRESH` with **168 hours**. *"Cold chain buys you days."*
3. **Register spinach** at 30 °C. It is `AT_RISK` immediately. *"Leafy greens can't wait."*
4. **Press Simulate +12 h** on the ambient tomato. It drops under 60 hours and goes `AT_RISK`. The alert appears with **3 buyers and a reason for each**.
5. **The farmer marks the lot SOLD.** The alerts stop.

After the demo, set `CR_ENABLE_SIMULATE=false` so the fast-forward endpoint returns 404.

## Safety

- It only **adds** `cr_` tables, indexes and a view. It never reads or changes any existing FarmNex table (`tests/test_migrations_safe.py` enforces this).
- Each farmer sees only their own lots and alerts; someone else's id returns 404.
- The background job can never crash the host backend.

## Layout

```
crop_rescue/    the module that goes into the main backend
migrations/     001_crop_rescue.sql, 002_demo_seed.sql   (run by hand in the Supabase SQL editor)
integration/    flutter/crop_rescue_api.dart
tests/          pytest suite     dev_app.py   local runner (never deployed)
docs/           SPEC.md, BUILD_PLAN.md, demo_transcript.md
```
