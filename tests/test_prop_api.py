"""Product setup and source checking use real completed runs and saved snapshots."""

import csv
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import io
import json
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from alphaquest.app import create_app
from alphaquest import prop_api
from alphaquest.prop.rules import ResolvedSimulation
from alphaquest.strategy import CloseIntent, EntryIntent
from review_execution import ScheduledStrategy
from test_backtest_api import run_fixture
from test_prop_sessions import bars_at, save_run


def setup_body(client, record, **changes):
    context = client.get("/api/prop-simulations/sources/" + record["id"])
    assert context.status_code == 200, context.text
    body = dict(source_backtest_id=record["id"], profile_id="apex_50k_eod_rithmic", phase="evaluation",
                observation_mode="bar_close", quantity=2, fee="0", account_start_utc=context.json()["account_start_utc"],
                end_utc=context.json()["end_utc"], instrument_symbol="TEST", currency="USD", contract_limit_weight="1",
                contract_limit_source_url="https://example.com/explicit-test-units", instrument_basis="Explicit synthetic USD test units",
                calendar=dict(mode="weekday_approximation", coverage_assumption="Complete synthetic fixture window",
                              start_time="05:00", end_time="05:30", bar_interval_seconds=300))
    body.update(changes)
    return body


def save(client, body):
    response = client.post("/api/prop-simulations/setups", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def check(client, setup):
    response = client.post(f"/api/prop-simulations/setups/{setup['id']}/check")
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("platform", ["rithmic", "tradovate", "wealthcharts"])
@pytest.mark.parametrize("phase", ["evaluation", "funded"])
def test_real_saved_run_setup_check_exports_and_restart(tmp_path, platform, phase):
    db = tmp_path / "datasets.sqlite3"
    with TestClient(create_app(db)) as client:
        dataset, record = run_fixture(client)
        source_dir = client.app.state.runs.root / record["id"]
        original = {p.name: p.read_bytes() for p in source_dir.iterdir() if p.is_file()}
        body = setup_body(client, record, profile_id="apex_50k_eod_" + platform, phase=phase, quantity=1)
        setup = save(client, body)
        assert setup["status"] == "draft" and setup["kind"] == "setup"
        config = ResolvedSimulation.from_dict(setup["resolved"]).config
        assert config.phase == phase and config.quantity == 1
        assert (config.fees.attempt_fee is None) == (phase == "funded")
        result = check(client, setup)
        assert result["status"] == "compatible", result
        assert result["summary"]["source_contracts"] == 2
        assert Decimal(result["summary"]["source_net_pnl"]) == 26
        assert {key: Decimal(result["summary"][key]) for key in ("gross_pnl", "total_commissions", "slippage_cost", "net_pnl")} == dict(
            gross_pnl=15, total_commissions=2, slippage_cost=5, net_pnl=13)
        endpoint = f"/api/prop-simulations/checks/{result['id']}"
        closes = client.get(endpoint + "/observations?mode=trade_close&limit=1").json()
        assert closes["total"] == 1 and Decimal(closes["items"][0]["equity_change"]) == 13
        marks = client.get(endpoint + "/observations?mode=bar_close&limit=2").json()
        assert marks["total"] == 7 and len(marks["items"]) == 2
        assert len(client.get(endpoint + "/observations?mode=bar_close&offset=2&limit=2").json()["items"]) == 2
        assert client.get(endpoint + "/observations?trading_date=2020-01-01").json()["total"] == 0
        assert client.get(endpoint + "/observations?limit=101").status_code == 422
        source = client.get(endpoint + "/exports/source.json").json()
        assert json.loads(source["manifest_json"])["run_metadata"] == record["run_metadata"]
        for artifact in source["artifacts"]:
            assert sha256(original[artifact["name"]]).hexdigest() == artifact["sha256"]
        rows = list(csv.DictReader(io.StringIO(client.get(endpoint + "/exports/observations.csv").text)))
        assert len(rows) == 8 and sum(r["mode"] == "trade_close" for r in rows) == 1
        snapshot = client.get(f"/api/prop-simulations/setups/{setup['id']}/exports/simulation.json").json()
        assert snapshot == setup["resolved"]
        assert client.get(endpoint + "/exports/preview.sqlite3").status_code == 404
        assert client.get(f"/api/prop-simulations/setups/{setup['id']}/exports/not-a-file").status_code == 404
        assert all((source_dir / name).read_bytes() == value for name, value in original.items())
        assert client.delete("/api/datasets/" + dataset["id"]).status_code == 204
        assert check(client, setup)["status"] == "compatible"  # frozen run survives dataset deletion
    with TestClient(create_app(db)) as client:
        loaded = client.get(f"/api/prop-simulations/setups/{setup['id']}").json()
        assert loaded["resolved"] == setup["resolved"] and loaded["latest_check"]["status"] == "compatible"
        assert client.get(f"/api/prop-simulations/setups?source_backtest_id={record['id']}").json()["total"] == 1


@pytest.mark.parametrize("changes", [
    {"quantity": True}, {"quantity": "1"}, {"quantity": 1.5}, {"quantity": 0}, {"quantity": 10001},
    {"fee": -1}, {"fee": "-1"}, {"fee": "NaN"}, {"fee": "1e99"}, {"fee": "0.0000000000000000001"},
    {"phase": "both"}, {"currency": "EUR"}, {"profile_id": "apex_legacy"}, {"contract_limit_weight": "0"},
    {"contract_limit_source_url": "http://example.com/units"}, {"account_start_utc": "2026-01-05T00:00:00"},
    {"end_utc": "2020-01-05T00:00:00Z"}, {"extra": 1},
])
def test_invalid_setup_does_not_publish(tmp_path, changes):
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        _, record = run_fixture(client)
        response = client.post("/api/prop-simulations/setups", json=setup_body(client, record, **changes))
        assert response.status_code == 422, response.text
        assert client.get(f"/api/prop-simulations/setups?source_backtest_id={record['id']}").json()["total"] == 0
        assert list(client.app.state.prop_runs.root.iterdir()) == []


def test_snapshot_reopens_and_checks_without_current_template(tmp_path, monkeypatch):
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        _, record = run_fixture(client)
        body = setup_body(client, record)
        original = save(client, body)
        before = client.get(f"/api/prop-simulations/setups/{original['id']}/exports/profile.json").content
        get_profile = prop_api.get_profile

        def changed_template(*args):
            profile = get_profile(*args)
            return replace(profile, version="1.0.1", evaluation=replace(profile.evaluation, limits=replace(
                profile.evaluation.limits, daily_loss_limit=Decimal("1100"))))

        monkeypatch.setattr(prop_api, "get_profile", changed_template)
        updated = save(client, body)
        assert updated["resolved"]["rules"]["profile_sha256"] != original["resolved"]["rules"]["profile_sha256"]
        assert client.get(f"/api/prop-simulations/setups/{original['id']}/exports/profile.json").content == before
        monkeypatch.setattr(prop_api, "get_profile", lambda *args: (_ for _ in ()).throw(RuntimeError("Template unavailable")))
        assert client.get(f"/api/prop-simulations/setups/{original['id']}").status_code == 200
        assert check(client, original)["status"] == "compatible"


@pytest.mark.parametrize("problem", ["missing", "variable", "overnight", "currency", "reconciliation"])
def test_rejected_source_is_saved_with_reason_without_preview(tmp_path, problem):
    bars = bars_at([datetime(2026, 1, day, 14, tzinfo=timezone.utc) + timedelta(minutes=i) for day in (5, 6, 7) for i in range(3)],
                   ["100"] * 3 + ["100", "100.5", "102"] + ["100"] * 3)
    strategy = ScheduledStrategy({4: EntryIntent(2, "entry")}, {6: CloseIntent("exit")})
    if problem == "variable":
        strategy = ScheduledStrategy({1: EntryIntent(2, "one"), 4: EntryIntent(1, "two")}, {3: strategy.closes[6], 6: strategy.closes[6]})
    elif problem == "overnight":
        strategy = ScheduledStrategy({3: EntryIntent(2, "overnight")}, {4: strategy.closes[6]})
    store, record, _ = save_run(tmp_path, bars, strategy)
    if problem == "reconciliation":
        path = store.root / record["id"] / "trades.csv"
        path.write_text(path.read_text().replace("26.00", "27.00"))
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        body = setup_body(client, record, instrument_symbol="SYNTHETIC")
        body["calendar"].update(start_time="09:00", end_time="09:02", bar_interval_seconds=60)
        if problem == "missing":
            body["calendar"]["end_time"] = "09:03"
        elif problem == "currency":
            body["instrument_symbol"] = "WRONG"
        setup = save(client, body)
        rejected = check(client, setup)
        assert rejected["status"] == "rejected" and rejected["error"]
        expected = {"missing": "coverage", "variable": "Variable", "overnight": "session", "currency": "symbol", "reconciliation": "match"}[problem]
        assert expected.lower() in rejected["error"].lower()
        assert client.get(f"/api/prop-simulations/checks/{rejected['id']}/observations").status_code == 409
        assert client.get(f"/api/prop-simulations/checks/{rejected['id']}/exports/source.json").status_code == 404
        loaded = client.get(f"/api/prop-simulations/setups/{setup['id']}").json()
        assert loaded["status"] == "draft" and loaded["latest_check"] == rejected


def test_zero_sessions_and_sunday_dst_are_in_product_preview(tmp_path):
    stamps = [datetime(2026, 3, 6, 14, tzinfo=timezone.utc), datetime(2026, 3, 9, 0, tzinfo=timezone.utc)]
    _, record, _ = save_run(tmp_path, bars_at(stamps), ScheduledStrategy())
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        calendar = dict(mode="explicit", coverage_assumption="Explicit synthetic DST observations", days=[
            dict(trading_date="2026-03-06", status="covered", windows=[dict(first_utc="2026-03-06T14:00:00Z", last_utc="2026-03-06T14:00:00Z", bar_interval_seconds=60)]),
            dict(trading_date="2026-03-07", status="closed"), dict(trading_date="2026-03-08", status="closed"),
            dict(trading_date="2026-03-09", status="covered", windows=[dict(first_utc="2026-03-09T00:00:00Z", last_utc="2026-03-09T00:00:00Z", bar_interval_seconds=60)]),
        ])
        setup = save(client, setup_body(client, record, instrument_symbol="SYNTHETIC", calendar=calendar))
        result = check(client, setup)
        assert result["status"] == "compatible" and result["summary"]["zero_trade_sessions"] == 2
        sessions = client.get(f"/api/prop-simulations/checks/{result['id']}/sessions").json()["items"]
        assert [s["status"] for s in sessions] == ["covered", "closed", "closed", "covered"]
        assert [s["open_utc"][11:13] for s in (sessions[0], sessions[-1])] == ["23", "22"]
        assert client.get(f"/api/prop-simulations/checks/{result['id']}/observations?trading_date=2026-03-09").json()["total"] == 1


def test_trade_relative_marks_and_surrounding_zero_trade_days(tmp_path):
    stamps = [datetime(2026, 1, day, 14, minute, tzinfo=timezone.utc) for day in (5, 6, 7) for minute in range(3)]
    bars = bars_at(stamps, ["100"] * 3 + ["100", "100.5", "102"] + ["100"] * 3)
    _, record, _ = save_run(tmp_path, bars, ScheduledStrategy({4: EntryIntent(2, "entry")}, {6: CloseIntent("exit")}))
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        setup = save(client, setup_body(client, record, instrument_symbol="SYNTHETIC", quantity=1,
                     calendar=dict(mode="weekday_approximation", start_time="09:00", end_time="09:02",
                                   bar_interval_seconds=60, coverage_assumption="Complete three-minute synthetic windows")))
        result = check(client, setup)
        assert result["status"] == "compatible" and result["summary"]["zero_trade_sessions"] == 2
        endpoint = f"/api/prop-simulations/checks/{result['id']}"
        sessions = client.get(endpoint + "/sessions").json()["items"]
        assert [s["trade_count"] for s in sessions] == [0, 1, 0]
        assert [Decimal(s["net_pnl"]) for s in sessions] == [0, 13, 0]
        marks = client.get(endpoint + "/observations?trading_date=2026-01-06").json()["items"]
        assert [Decimal(m["equity_change"]) for m in marks] == list(map(Decimal, ("-3.5", "1.5", "13")))
        assert Decimal(marks[-1]["source_equity"]) == 10026
        assert client.get(endpoint + "/observations?mode=trade_close&trading_date=2026-01-05").json()["total"] == 0


def test_storage_failure_does_not_publish_check_or_overwrite_previous(tmp_path, monkeypatch):
    with TestClient(create_app(tmp_path / "datasets.sqlite3"), raise_server_exceptions=False) as client:
        _, record = run_fixture(client)
        setup = save(client, setup_body(client, record))
        original = check(client, setup)
        store = client.app.state.prop_runs
        original_publish = store._publish

        def interrupted(path, table, *args):
            if table == "prop_checks":
                raise OSError("No output space")
            return original_publish(path, table, *args)

        monkeypatch.setattr(store, "_publish", interrupted)
        assert client.post(f"/api/prop-simulations/setups/{setup['id']}/check").status_code == 500
        loaded = client.get(f"/api/prop-simulations/setups/{setup['id']}").json()
        assert loaded["latest_check"] == original
        assert sorted(p.name for p in store.root.iterdir()) == sorted([setup["id"], original["id"]])


def test_tampered_resolved_profile_is_not_opened(tmp_path):
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        _, record = run_fixture(client)
        setup = save(client, setup_body(client, record))
        with client.app.state.prop_runs.connect() as conn:
            setup["resolved"]["rules"]["profile"]["version"] = "1.0.1"
            conn.execute("UPDATE prop_setups SET payload=? WHERE id=?", (json.dumps(setup), setup["id"]))
        assert client.get(f"/api/prop-simulations/setups/{setup['id']}").status_code == 409
        assert client.post(f"/api/prop-simulations/setups/{setup['id']}/check").status_code == 409


def test_missing_calendar_date_rejected_and_old_review_endpoints_retired(tmp_path):
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        _, record = run_fixture(client)
        body = setup_body(client, record, calendar=dict(mode="explicit", coverage_assumption="Explicit source dates", days=[dict(trading_date="2026-01-06", status="closed")]))
        assert client.post("/api/prop-simulations/setups", json=body).status_code == 422
        assert client.get("/api/prop-review/latest").status_code == 404
        assert client.post("/api/prop-review", json={}).status_code == 404
        assert client.get(f"/api/prop-simulations/setups/{uuid4().hex}").status_code == 404
        assert client.get(f"/api/prop-simulations/sources/{uuid4().hex}").status_code == 404
