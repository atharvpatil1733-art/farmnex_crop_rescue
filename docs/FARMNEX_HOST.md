# Facts about the FarmNex main backend (the host)

Checked against `atharvpatil1733-art/farmnex_main` on 2026-09-29. Where this file and `SPEC.md`
disagree about the **host**, this file wins. The component contract itself (`drop-in-contract`
skill) is unchanged.

The full host-side guide is `docs/integration/crop-rescue.md` in the farmnex_main repo.

| Topic | FarmNex main backend | So in this repo… |
|---|---|---|
| Login | Its own RS256 JWT; `get_current_user` is in `app/api/dependencies/current_user.py` and returns a `User` with `user.role` loaded | Nothing to add here — the host wraps the router |
| User id | `user.id` is an internal integer the app never sees; `user.public_id` is a UUID | The host override returns **`str(user.public_id)`**, and checks the role is `FARMER` (others get 403) |
| Database driver | **Async** SQLAlchemy + `asyncpg` (`DATABASE_URL=postgresql+asyncpg://…`) | The host must **not** call `configure(engine=engine)` with its engine (it's async; ours is sync). It sets **`CR_DATABASE_URL`** (Supabase session pooler, `postgresql+psycopg://…:5432/postgres?sslmode=require`). Falling back to the host's `DATABASE_URL` fails with `MissingGreenlet` |
| URL prefix | Everything is under `/api/v2` | Mounted as `include_router(router, prefix="/api/v2", …)` → `/api/v2/rescue/...`. Dart client paths must include `/api/v2` |
| Where it's copied | `backend/app/modules/crop_rescue/` | Relative imports only (already true) |
| Import time | Host imports the package inside its `mount_components()` after a flag check (`ENABLE_CROP_RESCUE`) | Settings validation errors only disable Crop Rescue, never crash the host |
| `.env` | Host runs from `backend/`; its settings don't export `.env` into `os.environ`, but it calls `load_dotenv()` first | `env_file=".env"` here still works when run from `backend/` |
| `POST /rescue/check` | Host limits it to ADMIN/MANAGER (it runs the check for every farmer) | Keep it as is |
| Flutter | One Dio: `ApiClient().dio` (adds the token, refreshes on 401) | `CropRescueApi(ApiClient().dio)`; methods take **no** `farmerId` (e.g. `fetchAlerts()`) |
| Migrations | Host keeps component SQL in `backend/migrations/` as `010_cr_crop_rescue.sql`, `011_cr_demo_seed.sql`; a person runs them in Supabase | Keep `migrations/*.sql` idempotent and add-only (already tested) |

Host wiring, for reference (lives in farmnex_main `backend/app/modules/wiring.py`, not here):

```python
from app.modules import crop_rescue                       # imported inside mount_components()

async def rescue_farmer_id(user: User = Depends(get_current_user)) -> str:
    if user.role is None or user.role.name != "FARMER":
        raise HTTPException(403, "Only farmers can use Crop Rescue.")
    return str(user.public_id)

app.include_router(crop_rescue.router, prefix="/api/v2", dependencies=[Depends(get_current_user)])
app.dependency_overrides[crop_rescue.current_farmer_id] = rescue_farmer_id
# lifespan: crop_rescue.start_scheduler() / crop_rescue.stop_scheduler()
```
