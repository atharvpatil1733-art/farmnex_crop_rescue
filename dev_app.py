"""Local development only. Never copied into the main backend, never
deployed. Always point CR_DATABASE_URL at the TEST database:

    CR_DATABASE_URL=$CR_TEST_DATABASE_URL uvicorn dev_app:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from crop_rescue import router, start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the scheduler on development app startup and stop it after serving."""
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="FarmNex Crop Rescue (dev)", lifespan=lifespan)
app.include_router(router)
