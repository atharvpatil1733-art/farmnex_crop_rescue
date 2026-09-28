# FarmNex Crop Rescue

> Placeholder. Claude Code rewrites this in Phase 6 (see docs/BUILD_PLAN.md).

A shelf-life clock for harvested produce. It warns the farmer **at least 48 hours before spoilage** and suggests the 3 best nearby buyers.

It is a FastAPI **router module**. You build and test it here, then copy `crop_rescue/` into the main FarmNex backend and mount it with `app.include_router(...)`. It uses the same Supabase PostgreSQL database and is called by the Flutter app through the main backend's URL.

**Start here:** open this repo in Claude Code and run `/build-phase 1`.
