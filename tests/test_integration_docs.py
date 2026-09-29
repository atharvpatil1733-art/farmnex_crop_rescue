"""The Dart client and INTEGRATION.md must not drift from the backend. No database needed."""

from __future__ import annotations

import re
import typing
from pathlib import Path

import pytest
from pydantic import BaseModel

from crop_rescue import schemas

ROOT = Path(__file__).resolve().parent.parent
DART = (ROOT / "integration" / "flutter" / "crop_rescue_api.dart").read_text(encoding="utf-8")
INTEGRATION = (ROOT / "INTEGRATION.md").read_text(encoding="utf-8")

RESPONSE_MODELS = [
    schemas.CropOut,
    schemas.CropsOut,
    schemas.CheckOut,
    schemas.LotOut,
    schemas.LotDetailOut,
    schemas.MatchOut,
    schemas.SimulateOut,
    schemas.CheckRunOut,
    schemas.AlertOut,
    schemas.HealthOut,
]


def _dart_class_body(name: str) -> str:
    start = DART.index(f"class {name} ")
    match = re.search(r"^}", DART[start:], re.MULTILINE)
    return DART[start : start + match.end()]


@pytest.mark.parametrize("model", RESPONSE_MODELS, ids=lambda m: m.__name__)
def test_dart_class_reads_every_json_key(model: type[BaseModel]):
    body = _dart_class_body(model.__name__)
    own_keys = model.model_fields.keys()
    if model is schemas.LotDetailOut:  # inherits the lot keys via LotOut.fromJson
        own_keys = ["checks"]
    for key in own_keys:
        assert f"json['{key}']" in body, f"{model.__name__}.{key} missing in Dart"


@pytest.mark.parametrize("model", RESPONSE_MODELS, ids=lambda m: m.__name__)
def test_dart_class_reads_no_unknown_key(model: type[BaseModel]):
    body = _dart_class_body(model.__name__)
    known = set(model.model_fields)
    if model is schemas.LotDetailOut:
        known = {"checks"}
    for key in re.findall(r"json\['([a-z0-9_]+)'\]", body):
        assert key in known, f"Dart {model.__name__} reads '{key}', which the backend never sends"


def _dart_line(body: str, key: str) -> str:
    return next(line for line in body.splitlines() if f"json['{key}']" in line)


def _is_optional(annotation) -> bool:
    return type(None) in typing.get_args(annotation)


def _base_type(annotation):
    args = [a for a in typing.get_args(annotation) if a is not type(None)]
    return args[0] if args else annotation


@pytest.mark.parametrize("model", RESPONSE_MODELS, ids=lambda m: m.__name__)
def test_dart_nullability_and_number_types_match_the_schema(model: type[BaseModel]):
    body = _dart_class_body(model.__name__)
    if model is schemas.LotDetailOut:
        return
    for key, field in model.model_fields.items():
        line = _dart_line(body, key)
        dart_nullable = "OrNull" in line or bool(re.search(r"as [\w<>, ]+\?", line))
        assert dart_nullable == _is_optional(field.annotation), f"{model.__name__}.{key} nullability"
        base = _base_type(field.annotation)
        if base is int:
            assert "as int" in line, f"{model.__name__}.{key} should be int in Dart"
        elif base is float:
            assert "_d(" in line or "_dOrNull(" in line, f"{model.__name__}.{key} should be double"


def test_every_dart_route_exists_on_the_backend():
    from crop_rescue import api

    backend = {(m, r.path) for r in api.router.routes for m in r.methods}
    dart = set()
    for verb, path in re.findall(r"_dio\.(get|post)\(\s*'([^']+)'", DART):
        dart.add((verb.upper(), re.sub(r"\$(\w+)", lambda m: "{" + {"lotId": "lot_id", "alertId": "alert_id"}[m.group(1)] + "}", path)))
    assert dart <= backend, dart - backend
    assert {p for _, p in backend - dart} == {"/rescue/check"}  # the only route with no Dart method


def test_dart_request_keys_match_the_request_models():
    create = DART[DART.index("Future<LotOut> createLot") : DART.index("Future<List<LotOut>> listLots")]
    for key in schemas.LotCreate.model_fields:
        assert f"'{key}'" in create, key
    simulate = DART[DART.index("Future<SimulateOut> simulate") : DART.index("Future<List<AlertOut>>")]
    for key in schemas.SimulateRequest.model_fields:
        assert f"'{key}'" in simulate, key
    assert "'unread_only'" in DART


def test_dart_client_takes_an_existing_dio_and_no_farmer_id():
    assert re.search(r"CropRescueApi\(this\._dio\)", DART)
    code = re.sub(r"//.*", "", DART)
    assert not re.search(r"farmer", code, re.IGNORECASE)


def test_dart_client_has_a_method_for_each_endpoint():
    for method in (
        "fetchCrops", "createLot", "listLots", "getLot", "getMatches",
        "markSold", "simulate", "fetchAlerts", "markAlertRead",
    ):
        assert re.search(rf"Future<[^>]+>+ {method}\(", DART), method


def test_integration_md_has_exactly_five_numbered_steps():
    steps = re.findall(r"^### (\d+)\. ", INTEGRATION, re.MULTILINE)
    assert steps == ["1", "2", "3", "4", "5"]


def test_integration_md_has_the_required_content():
    assert "app.dependency_overrides[crop_rescue.current_farmer_id]" in INTEGRATION
    assert "include_router(rescue_router, dependencies=[Depends(get_current_user)])" in INTEGRATION
    assert "CR_ENABLE_SIMULATE=false" in INTEGRATION
    assert "ValidationError" in INTEGRATION  # fail-fast troubleshooting note
    assert "001_crop_rescue.sql" in INTEGRATION and "002_demo_seed.sql" in INTEGRATION
    for path in (
        "/rescue/health", "/rescue/crops", "/rescue/lots", "/rescue/lots/<LOT_ID>",
        "/rescue/lots/<LOT_ID>/matches", "/rescue/lots/<LOT_ID>/sold", "/rescue/simulate",
        "/rescue/alerts", "/rescue/alerts/<ALERT_ID>/read", "/rescue/check",
    ):
        assert path in INTEGRATION, path
    assert "curl" in INTEGRATION
