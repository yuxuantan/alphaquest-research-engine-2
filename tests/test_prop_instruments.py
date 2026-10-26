"""Sourced instrument selection, unit rejection, and immutable replay snapshots."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import date
from decimal import Decimal as D, localcontext
import json

from fastapi.testclient import TestClient
import pytest

from alphaquest.app import create_app
from alphaquest import prop_api
from alphaquest.prop.instruments import get_instrument_profile, resolve_instrument_profile, ResolvedInstrumentProfile, source_compatibility
from alphaquest.prop.sessions import InstrumentDeclaration
from review_execution import fixtures
from test_backtest_api import run_fixture
from test_prop_api import setup_body, save, check
from test_prop_results_api import run
from test_prop_sessions import DECLARATION


MANUAL_FIELDS = ("instrument_symbol", "currency", "contract_limit_weight", "contract_limit_source_url", "instrument_basis")


def instrument_source(client, instrument="nq"):
    case = deepcopy(fixtures()[0])
    case["execution_settings"]["point_value"] = "20" if instrument == "nq" else "2"
    return run_fixture(client, case)


def preset_body(client, source, instrument="nq", **changes):
    body = setup_body(client, source)
    for key in MANUAL_FIELDS:
        del body[key]
    body.update(instrument_profile_id=instrument, **changes)
    return body


@pytest.mark.parametrize("instrument,symbol,point,weight", [("nq", "NQ", "20", "1"), ("mnq", "MNQ", "2", "0.1")])
def test_sourced_profiles_exact_units_and_stable_snapshot(instrument, symbol, point, weight):
    profile = get_instrument_profile(instrument)
    assert (profile.symbol, profile.currency, profile.tick_size, profile.point_value, profile.contract_limit_weight) == (
        symbol, "USD", D(".25"), D(point), D(weight))
    assert profile.version == "1.0.0"
    assert all(s.retrieved_on == date(2026, 10, 26) and s.effective_on is None for s in profile.sources)
    assert profile.platforms == ("rithmic", "tradovate", "wealthcharts")
    captured = resolve_instrument_profile(profile)
    with localcontext() as ctx:
        ctx.prec = 1
        equivalent = replace(profile, tick_size=D(".25000"))
        assert resolve_instrument_profile(equivalent).profile_sha256 == captured.profile_sha256
        assert ResolvedInstrumentProfile.from_json(captured.to_json()) == captured
    with pytest.raises(FrozenInstanceError):
        profile.point_value = D("1")
    payload = captured.to_dict()
    payload["profile"]["point_value"] = "1"
    with pytest.raises(ValueError, match="hash"):
        ResolvedInstrumentProfile.from_dict(payload)
    for changes in ({"tick_size": D(0)}, {"point_value": D("NaN")}, {"contract_limit_weight": D("-1")},
                    {"currency": "US"}, {"platforms": ()}, {"specification_source_url": "http://example.com"}):
        with pytest.raises(ValueError):
            replace(profile, **changes)


def test_legacy_declaration_round_trip_keeps_original_shape():
    wire = DECLARATION.to_dict()
    assert set(wire) == {"symbol", "currency", "tick_size", "point_value", "contract_limit_weight", "contract_limit_source_url", "basis"}
    assert InstrumentDeclaration.from_dict(json.loads(json.dumps(wire))).to_dict() == wire


@pytest.mark.parametrize("instrument,mode,balance,net,slippage", [
    ("nq", "bar_close", "50056", "56", "20"), ("nq", "trade_close", "50056", "56", "20"),
    ("mnq", "bar_close", "50002", "2", "2"), ("mnq", "trade_close", "50002", "2", "2"),
])
def test_profile_selection_check_execution_exports_and_restart(tmp_path, instrument, mode, balance, net, slippage):
    db = tmp_path / "datasets.sqlite3"
    with TestClient(create_app(db)) as client:
        _, source = instrument_source(client, instrument)
        source_dir = client.app.state.runs.root / source["id"]
        before = {p.name: p.read_bytes() for p in source_dir.iterdir() if p.is_file()}
        views = client.get("/api/prop-simulations/instrument-profiles", params={"source_backtest_id": source["id"]}).json()
        matching = next(v for v in views if v["display"]["id"] == instrument)
        assert matching["compatibility"]["compatible"] is True
        assert matching["compatibility"]["identity_declared"] is True  # no guess from the synthetic file name
        setup = save(client, preset_body(client, source, instrument, observation_mode=mode))
        snapshot = setup["instrument"]["profile"]
        assert setup["resolved"]["config"]["instrument_profile_sha256"] == snapshot["profile_sha256"]
        assert setup["declaration"]["instrument_symbol"] is None
        checked = check(client, setup)
        assert checked["status"] == "compatible"
        assert checked["summary"]["net_pnl"] == net
        assert checked["summary"]["total_commissions"] == "4"
        assert checked["summary"]["slippage_cost"] == slippage
        result = run(client, setup)
        assert result["summary"]["balance"] == balance
        assert result["summary"]["outcome"] == "unresolved_data_end"
        assert result["instrument"] == setup["instrument"]
        for kind, identifier in (("setups", setup["id"]), ("results", result["id"])):
            assert client.get(f"/api/prop-simulations/{kind}/{identifier}/exports/instrument.json").json() == setup["instrument"]
        assert all((source_dir / name).read_bytes() == value for name, value in before.items())
    with TestClient(create_app(db)) as client:
        loaded = client.get(f"/api/prop-simulations/setups/{setup['id']}").json()
        assert loaded["instrument"] == setup["instrument"]
        assert loaded["instrument_profile_view"]["display"]["tick_size"] == "0.25"
        assert client.get(f"/api/prop-simulations/results/{result['id']}").json() == result


@pytest.mark.parametrize("changes", [{"instrument_profile_id": "unknown"}, {"instrument_profile_id": True},
                                    {"currency": "USD"}, {"contract_limit_weight": "0.1"},
                                    {"instrument_profile_id": None}])
def test_invalid_or_mixed_selection_never_publishes_setup(tmp_path, changes):
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        _, source = instrument_source(client)
        body = preset_body(client, source)
        body.update(changes)
        assert client.post("/api/prop-simulations/setups", json=body).status_code == 422
        assert list(client.app.state.prop_runs.root.iterdir()) == []


def test_mini_source_cannot_be_reinterpreted_as_micro(tmp_path):
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        _, source = instrument_source(client)
        response = client.post("/api/prop-simulations/setups", json=preset_body(client, source, "mnq"))
        assert response.status_code == 422 and "point_value" in response.json()["detail"]
        assert source["execution_settings"]["point_value"] == "20"
        altered = deepcopy(source)
        altered["run_metadata"]["dataset"].update(symbol="OTHER", currency="EUR")
        assert len(source_compatibility(get_instrument_profile("nq"), altered)["issues"]) == 2
        altered["execution_settings"]["tick_size"] = "0.5"
        assert "tick_size" in " ".join(source_compatibility(get_instrument_profile("nq"), altered)["issues"])


def test_saved_instrument_is_independent_of_current_templates_and_identity_is_bound(tmp_path, monkeypatch):
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        _, source = instrument_source(client)
        setup = save(client, preset_body(client, source))
        before = client.get(f"/api/prop-simulations/setups/{setup['id']}/exports/instrument.json").content
        original = prop_api.get_instrument_profile
        monkeypatch.setattr(prop_api, "get_instrument_profile", lambda key: replace(original(key), version="1.0.1"))
        newer = save(client, preset_body(client, source))
        assert newer["resolved"]["settings_sha256"] != setup["resolved"]["settings_sha256"]
        monkeypatch.setattr(prop_api, "get_instrument_profile", lambda *args: (_ for _ in ()).throw(RuntimeError("Catalog offline")))
        assert check(client, setup)["status"] == "compatible"
        assert run(client, setup)["summary"]["balance"] == "50056"
        assert client.get(f"/api/prop-simulations/setups/{setup['id']}/exports/instrument.json").content == before
        store = client.app.state.prop_runs
        with store.connect() as conn:
            payload = json.loads(conn.execute("SELECT payload FROM prop_setups WHERE id=?", (setup["id"],)).fetchone()[0])
            payload["instrument"]["profile"] = newer["instrument"]["profile"]
            payload["instrument"]["basis"] = newer["instrument"]["basis"]
            conn.execute("UPDATE prop_setups SET payload=? WHERE id=?", (json.dumps(payload), setup["id"]))
        assert client.get(f"/api/prop-simulations/setups/{setup['id']}").status_code == 409


def test_micro_weight_uses_account_units_without_scaling_pnl_twice(tmp_path):
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        _, source = instrument_source(client, "mnq")
        setup = save(client, preset_body(client, source, "mnq", quantity=60))
        check(client, setup)
        assert run(client, setup)["summary"]["balance"] == "50060"  # unit net = 1 USD; weight is only for limits
        too_big = save(client, preset_body(client, source, "mnq", quantity=61))
        check(client, too_big)
        rejected = client.post(f"/api/prop-simulations/setups/{too_big['id']}/run")
        assert rejected.status_code == 422 and "contract limit" in rejected.json()["detail"]
