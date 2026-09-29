import pytest

from crop_rescue.config import Settings

CR_VARS = [
    "CR_DATABASE_URL",
    "DATABASE_URL",
    "CR_TEST_DATABASE_URL",
    "CR_CHECK_INTERVAL_HOURS",
    "CR_ALERT_HOURS",
    "CR_Q10",
    "CR_DEFAULT_TEMP_C",
    "CR_USE_OPEN_METEO",
    "CR_RADIUS_KM",
    "CR_ROAD_FACTOR",
    "CR_AVG_SPEED_KMPH",
    "CR_LOADING_HOURS",
    "CR_TRANSPORT_RS_PER_KM",
    "CR_TOP_N",
    "CR_ENABLE_SCHEDULER",
    "CR_ENABLE_SIMULATE",
]


@pytest.fixture
def clean_env(monkeypatch):
    for name in CR_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_defaults(clean_env):
    s = Settings(_env_file=None)
    assert s.database_url is None
    assert s.test_database_url is None
    assert s.check_interval_hours == 12
    assert s.alert_hours == 48
    assert s.q10 == 2.0
    assert s.default_temp_c == 30
    assert s.use_open_meteo is False
    assert s.radius_km == 50
    assert s.road_factor == 1.3
    assert s.avg_speed_kmph == 35
    assert s.loading_hours == 2
    assert s.transport_rs_per_km == 25
    assert s.top_n == 3
    assert s.enable_scheduler is True
    assert s.enable_simulate is True


def test_env_overrides(clean_env):
    clean_env.setenv("CR_Q10", "3")
    clean_env.setenv("CR_ENABLE_SIMULATE", "false")
    s = Settings(_env_file=None)
    assert s.q10 == 3.0
    assert s.enable_simulate is False


def test_database_url_falls_back_to_host_database_url(clean_env):
    clean_env.setenv("DATABASE_URL", "postgresql+psycopg://host/db")
    s = Settings(_env_file=None)
    assert s.database_url.get_secret_value() == "postgresql+psycopg://host/db"


def test_test_database_url_never_falls_back(clean_env):
    clean_env.setenv("CR_DATABASE_URL", "postgresql+psycopg://main/db")
    clean_env.setenv("DATABASE_URL", "postgresql+psycopg://host/db")
    s = Settings(_env_file=None)
    assert s.test_database_url is None


def test_connection_strings_are_hidden_in_repr(clean_env):
    clean_env.setenv("CR_DATABASE_URL", "postgresql+psycopg://user:hunter2@host/db")
    s = Settings(_env_file=None)
    assert "hunter2" not in repr(s)
    assert "hunter2" not in str(s)
