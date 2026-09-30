"""CR_* settings. Every value has a default, so the host only sets what it changes.

Connection strings are secrets: they are SecretStr so they never show up in a
repr or a log line.
"""

from __future__ import annotations

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CR_", env_file=".env", extra="ignore")

    # Main database (the team's Supabase). Set CR_DATABASE_URL (sync psycopg URL); the
    # DATABASE_URL fallback is for simple hosts and is refused if it uses an async driver.
    # This fallback is for the production engine only; tests never read this
    # field, only test_database_url below.
    database_url: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("CR_DATABASE_URL", "DATABASE_URL")
    )
    # Throwaway Postgres for tests and /demo only. Never falls back to anything.
    test_database_url: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("CR_TEST_DATABASE_URL")
    )

    # Shelf-life clock
    check_interval_hours: float = Field(default=12, gt=0)
    alert_hours: float = Field(default=48, gt=0)
    q10: float = Field(default=2.0, gt=1)  # assumption: produce rule of thumb is 2-3
    default_temp_c: float = 30.0  # assumption: a Pune-area afternoon
    use_open_meteo: bool = False

    # Buyer matching
    radius_km: float = Field(default=50, gt=0)
    road_factor: float = Field(default=1.3, ge=1)  # assumption: road km / straight-line km
    avg_speed_kmph: float = Field(default=35, gt=0)  # assumption
    loading_hours: float = Field(default=2, ge=0)  # assumption
    transport_rs_per_km: float = Field(default=25, ge=0)  # assumption
    top_n: int = Field(default=3, ge=1)

    # Switches
    enable_scheduler: bool = True
    enable_simulate: bool = False  # demo only: set CR_ENABLE_SIMULATE=true for the demo, off otherwise


settings = Settings()
