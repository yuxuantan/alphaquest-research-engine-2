"""Reusable profile prices and immutable phase-specific fee resolution."""

from dataclasses import replace
from datetime import date
from decimal import Decimal as D

from fastapi.testclient import TestClient
import pytest

from alphaquest.app import create_app
from alphaquest.prop import ResolvedSimulation, get_profile, resolve_profile, resolve_simulation
from alphaquest.prop.types import ProfileFees, UserFees
from test_backtest_api import run_fixture
from test_prop_api import check, save, setup_body
from test_prop_configuration import request


PROFILE = "apex_50k_eod_rithmic"
URL = "/api/prop-simulations/profiles/" + PROFILE + "/fees"


def defaults(client, attempt="35", activation="140"):
    response = client.put(URL, json={"attempt_fee": attempt, "activation_fee": activation})
    assert response.status_code == 200, response.text
    return response.json()


def test_profile_prices_change_identity_without_mutating_legacy_snapshots():
    base = resolve_profile(replace(get_profile(), version="1.0.0", fee_defaults=None))
    # Exact pre-feature golden hash remains valid; absent defaults stay absent.
    assert base.profile_sha256 == "581942fc25da4756e2e033ea11ce2673b15d21f844d51a02c5a1ac4b5e7f0599"
    assert "fee_defaults" not in base.to_dict()["profile"]
    fees = ProfileFees("USD", date(2026, 10, 26), D("35"), D("140"))
    profile = replace(get_profile(), fee_defaults=fees)
    assert resolve_profile(profile).profile_sha256 != base.profile_sha256
    equivalent = replace(profile, fee_defaults=replace(fees, attempt_fee=D("35.00")))
    assert resolve_profile(equivalent).profile_sha256 == resolve_profile(profile).profile_sha256
    captured = resolve_simulation(request(fees=UserFees("USD", attempt_fee=D("35"), origin="profile_default")), profile)
    assert ResolvedSimulation.from_json(captured.to_json()) == captured
    assert type(base).from_json(base.to_json()).to_json() == base.to_json()
    for bad in (UserFees("USD", attempt_fee=D("36"), origin="profile_default"),
                UserFees("USD", activation_fee=D("35"), origin="profile_default")):
        with pytest.raises(ValueError):
            resolve_simulation(request(phase="funded" if bad.activation_fee is not None else "evaluation", fees=bad), profile)
    with pytest.raises(ValueError, match="captured"):
        resolve_simulation(request(fees=UserFees("USD", attempt_fee=D("35"), origin="profile_default")), base.profile)
    with pytest.raises(ValueError, match="currency"):
        replace(profile, fee_defaults=replace(fees, currency="EUR"))


@pytest.mark.parametrize("payload", [
    {}, {"attempt_fee": ""}, {"attempt_fee": -1}, {"attempt_fee": "-1"},
    {"attempt_fee": "NaN"}, {"attempt_fee": "Infinity"}, {"attempt_fee": True},
    {"attempt_fee": "1e99"}, {"attempt_fee": "0.0000000000000000001"},
    {"attempt_fee": "35", "activation_fee": "-1"}, {"attempt_fee": "35", "extra": 1},
])
def test_invalid_profile_prices_never_replace_previous_defaults(tmp_path, payload):
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        before = defaults(client)
        assert client.put(URL, json=payload).status_code == 422
        assert client.get("/api/prop-simulations/profiles").json()[0] == before


def test_phase_defaults_override_restart_and_saved_result_preservation(tmp_path):
    db = tmp_path / "datasets.sqlite3"
    with TestClient(create_app(db)) as client:
        _, record = run_fixture(client)
        body = setup_body(client, record)
        del body["fee"]  # Omission inherits a profile default; never means zero.
        assert D(save(client, body)["resolved"]["config"]["fees"]["attempt_fee"]) == 49
        defaults(client)
        original = save(client, body)
        config = ResolvedSimulation.from_dict(original["resolved"]).config
        assert config.fees.attempt_fee == 35 and config.fees.activation_fee is None
        assert config.fees.origin == "profile_default"
        assert check(client, original)["status"] == "compatible"
        response = client.post(f"/api/prop-simulations/setups/{original['id']}/run")
        assert response.status_code == 201, response.text
        result = response.json()
        assert result["summary"]["balance"] == "50026"
        assert result["summary"]["external_costs"] == "35"
        assert result["summary"]["modeled_net_cash"] == "-35"
        setup_export = client.get(f"/api/prop-simulations/setups/{original['id']}/exports/simulation.json").content
        result_export = client.get(f"/api/prop-simulations/results/{result['id']}/exports/report.json").content
        funded = save(client, {**body, "phase": "funded"})
        f = ResolvedSimulation.from_dict(funded["resolved"]).config.fees
        assert f.activation_fee == 140 and f.attempt_fee is None
        override = save(client, {**body, "fee": "0"})
        assert override["resolved"]["config"]["fees"]["origin"] == "user_supplied"
        assert D(override["resolved"]["config"]["fees"]["attempt_fee"]) == 0
        defaults(client, "49", "150")
        newer = save(client, {**body, "fee": None})
        assert D(newer["resolved"]["config"]["fees"]["attempt_fee"]) == 49
        assert newer["resolved"]["rules"]["profile_sha256"] != original["resolved"]["rules"]["profile_sha256"]
        tradovate = save(client, {**body, "profile_id": "apex_50k_eod_tradovate"})
        assert D(tradovate["resolved"]["config"]["fees"]["attempt_fee"]) == 49
        assert D(tradovate["resolved"]["rules"]["profile"]["fee_defaults"]["activation_fee"]) == 129
    with TestClient(create_app(db)) as client:
        assert client.get("/api/prop-simulations/profiles").json()[0]["display"]["fee_defaults"]["attempt_fee"] == "49"
        assert client.get(f"/api/prop-simulations/setups/{original['id']}").json()["resolved"] == original["resolved"]
        assert client.get(f"/api/prop-simulations/setups/{original['id']}/exports/simulation.json").content == setup_export
        assert client.get(f"/api/prop-simulations/results/{result['id']}/exports/report.json").content == result_export


def test_zero_price_and_missing_other_phase_are_explicit(tmp_path):
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        defaults(client, "0", None)
        _, record = run_fixture(client)
        body = setup_body(client, record, fee=None)
        assert D(save(client, body)["resolved"]["config"]["fees"]["attempt_fee"]) == 0
        assert client.post("/api/prop-simulations/setups", json={**body, "phase": "funded"}).status_code == 422
        assert client.put("/api/prop-simulations/profiles/unknown/fees", json={"attempt_fee": "0"}).status_code == 422


@pytest.mark.parametrize("platform", ["rithmic", "tradovate", "wealthcharts"])
@pytest.mark.parametrize("suffix,attempt,activation", [("", 49, 129), ("_no_activation", 109, 0)])
def test_user_supplied_pricing_options_inherit_separate_phase_prices(tmp_path, platform, suffix, attempt, activation):
    profile_id = "apex_50k_eod_" + platform + suffix
    profile = get_profile(profile_id)
    assert profile.version == "1.1.0"
    assert profile.fee_defaults == ProfileFees("USD", date(2026, 10, 26), D(attempt), D(activation))
    assert profile.evaluation == get_profile("apex_50k_eod_" + platform).evaluation
    assert profile.funded == get_profile("apex_50k_eod_" + platform).funded
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        catalog = client.get("/api/prop-simulations/profiles").json()
        assert len(catalog) == 6 and len({view["snapshot"]["profile_sha256"] for view in catalog}) == 6
        _, record = run_fixture(client)
        for phase in ("evaluation", "funded"):
            setup = save(client, setup_body(client, record, profile_id=profile_id, phase=phase, fee=None))
            fees = ResolvedSimulation.from_dict(setup["resolved"]).config.fees
            assert fees.attempt_fee == (attempt if phase == "evaluation" else None)
            assert fees.activation_fee == (activation if phase == "funded" else None)
            assert fees.origin == "profile_default"


def test_no_activation_option_cannot_silently_acquire_an_activation_fee(tmp_path):
    profile_id = PROFILE + "_no_activation"
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        before = client.get("/api/prop-simulations/profiles").json()
        for activation in ("129", None):
            response = client.put(f"/api/prop-simulations/profiles/{profile_id}/fees",
                                  json={"attempt_fee": "109", "activation_fee": activation})
            assert response.status_code == 422 and "zero activation" in response.json()["detail"]
            assert client.get("/api/prop-simulations/profiles").json() == before
        _, record = run_fixture(client)
        response = client.post("/api/prop-simulations/setups", json=setup_body(
            client, record, profile_id=profile_id, phase="funded", fee="129"))
        assert response.status_code == 422 and "zero activation" in response.json()["detail"]
        assert client.get("/api/prop-simulations/setups", params={"source_backtest_id": record["id"]}).json()["total"] == 0
