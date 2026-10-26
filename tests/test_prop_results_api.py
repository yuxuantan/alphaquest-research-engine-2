"""Durable evaluation execution, reconciliation, source integrity and failure atomicity."""

import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import io
import json

from fastapi.testclient import TestClient
import pytest

from alphaquest.app import create_app
from alphaquest.strategy import EntryIntent, CloseIntent
from review_execution import ScheduledStrategy
from test_prop_sessions import bars_at, save_run
from test_backtest_api import run_fixture
from test_prop_api import setup_body, save, check


def run(client, setup):
    response = client.post(f"/api/prop-simulations/setups/{setup['id']}/run")
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("quantity,balance", [(2, "50026"), (1, "50013")])
@pytest.mark.parametrize("mode", ["bar_close", "trade_close"])
def test_actual_source_results_reconcile_export_and_reopen(tmp_path, quantity, balance, mode):
    db = tmp_path / "datasets.sqlite3"
    with TestClient(create_app(db)) as client:
        _, source = run_fixture(client)
        folder = client.app.state.runs.root / source["id"]
        original = {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}
        setup = save(client, setup_body(client, source, quantity=quantity, observation_mode=mode, fee="35"))
        check(client, setup)
        result = run(client, setup)
        summary = result["summary"]
        assert summary["balance"] == summary["equity"] == balance
        assert summary["outcome"] == "unresolved_data_end"
        assert summary["modeled_net_cash"] == "-35" and result["status"] == "complete"
        assert summary["processed_trades"] == summary["completed_source_trades"] == 1
        assert result["resolved"] == setup["resolved"] and result["reconciliation"]["passed"] is True
        base = f"/api/prop-simulations/results/{result['id']}"
        page = client.get(base + "/events?limit=2").json()
        assert len(page["items"]) == 2 and page["total"] == summary["event_count"]
        assert client.get(base + "/events?limit=101").status_code == 422
        chart = client.get(base + "/chart?max_points=20").json()
        events = list(csv.DictReader(io.StringIO(client.get(base + "/exports/events.csv").text)))
        by_sequence = {int(event["sequence"]): event for event in events}
        for point in chart["items"]:
            assert point["equity"] == by_sequence[point["sequence"]]["equity"]
            assert point["trailing_floor"] == by_sequence[point["sequence"]]["trailing_floor"]
        assert Decimal(sum((Decimal(e["realized_delta"]) for e in events))) + 50000 == Decimal(balance)
        for filename, artifact in result["artifacts"].items():
            data = client.get(base + "/exports/" + filename).content
            assert sha256(data).hexdigest() == artifact["sha256"] and len(data) == artifact["byte_count"]
        assert client.get(base + "/exports/events.sqlite3").status_code == 404
        assert all((folder / name).read_bytes() == value for name, value in original.items())
    with TestClient(create_app(db)) as restarted:
        assert restarted.get(base).json() == result
        assert restarted.get(f"/api/prop-simulations/results?setup_id={setup['id']}").json()["total"] == 1


@pytest.mark.parametrize("problem", ["no_check", "funded", "oversize", "partial", "future"])
def test_invalid_operation_publishes_no_financial_outcome(tmp_path, problem):
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        _, source = run_fixture(client)
        body = setup_body(client, source)
        if problem == "funded":
            body["phase"] = "funded"
        elif problem == "oversize":
            body["quantity"] = 7
        elif problem == "partial":
            body["account_start_utc"] = "2026-01-05T00:00:00Z"
        elif problem == "future":
            body["end_utc"] = "2026-01-06T23:00:00Z"
        setup = save(client, body)
        if problem != "no_check":
            check(client, setup)
        before = sorted(p.name for p in client.app.state.prop_runs.root.iterdir())
        response = client.post(f"/api/prop-simulations/setups/{setup['id']}/run")
        assert response.status_code == 422, response.text
        assert "outcome" not in response.json()
        assert client.get(f"/api/prop-simulations/results?setup_id={setup['id']}").json()["total"] == 0
        assert sorted(p.name for p in client.app.state.prop_runs.root.iterdir()) == before


@pytest.mark.parametrize("corrupt", [False, True])
def test_source_is_revalidated_even_after_compatible_check(tmp_path, corrupt):
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        _, source = run_fixture(client)
        setup = save(client, setup_body(client, source))
        check(client, setup)
        folder = client.app.state.runs.root / source["id"]
        if corrupt:
            path = folder / "trades.csv"
            path.write_text(path.read_text().replace("26.00", "27.00"))
        else:
            path = folder / "report.json"
            path.write_text(json.dumps(json.loads(path.read_text())))  # semantically valid, changed bytes
        response = client.post(f"/api/prop-simulations/setups/{setup['id']}/run")
        assert response.status_code == 422
        assert client.get(f"/api/prop-simulations/results?setup_id={setup['id']}").json()["total"] == 0
        if not corrupt:
            assert "identity changed" in response.json()["detail"]
            check(client, setup)
            assert run(client, setup)["summary"]["balance"] == "50026"


def test_failed_publication_keeps_earlier_result_and_removes_partial_output(tmp_path, monkeypatch):
    with TestClient(create_app(tmp_path / "datasets.sqlite3"), raise_server_exceptions=False) as client:
        _, source = run_fixture(client)
        setup = save(client, setup_body(client, source)); check(client, setup)
        original = run(client, setup)
        store = client.app.state.prop_runs
        paths = sorted(p.name for p in store.root.iterdir())
        publish = store._publish

        def fail(path, table, *args):
            if table == "prop_results":
                raise OSError("Output device unavailable")
            return publish(path, table, *args)

        monkeypatch.setattr(store, "_publish", fail)
        assert client.post(f"/api/prop-simulations/setups/{setup['id']}/run").status_code == 500
        assert sorted(p.name for p in store.root.iterdir()) == paths
        assert client.get(f"/api/prop-simulations/results/{original['id']}").json() == original
        assert client.get(f"/api/prop-simulations/results?setup_id={setup['id']}").json()["total"] == 1


def test_result_does_not_resolve_current_templates(tmp_path, monkeypatch):
    from alphaquest import prop_api
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        _, source = run_fixture(client)
        setup = save(client, setup_body(client, source)); check(client, setup)
        monkeypatch.setattr(prop_api, "get_profile", lambda *args: (_ for _ in ()).throw(RuntimeError("No current templates")))
        result = run(client, setup)
        assert result["resolved"] == setup["resolved"]
        assert client.get(f"/api/prop-simulations/results/{result['id']}").json() == result


def test_bounded_chart_uses_actual_saved_extrema_and_paged_events(tmp_path):
    stamps = [datetime(2026, 1, 5, 14, tzinfo=timezone.utc) + timedelta(minutes=i) for i in range(120)]
    prices = ["100"] * 120
    prices[50], prices[-1] = "120", "102"
    _, record, _ = save_run(tmp_path, bars_at(stamps, prices), ScheduledStrategy({1: EntryIntent(2, "entry")}, {120: CloseIntent("exit")}))
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        body = setup_body(client, record, instrument_symbol="SYNTHETIC",
                          calendar=dict(mode="weekday_approximation", start_time="09:00", end_time="10:59", bar_interval_seconds=60, coverage_assumption="Complete two-hour synthetic window"))
        setup = save(client, body); check(client, setup); result = run(client, setup)
        base = f"/api/prop-simulations/results/{result['id']}"
        chart = client.get(base + "/chart?max_points=20").json()
        assert chart["sampled"] is True and len(chart["items"]) <= 20
        assert max(Decimal(p["equity"]) for p in chart["items"]) == 50393
        assert chart["items"][0]["sequence"] == 0
        assert chart["items"][-1]["sequence"] == result["summary"]["event_count"] - 1
        assert len(client.get(base + "/events?offset=50&limit=50").json()["items"]) == 50


def test_reconciliation_failure_cannot_publish_a_result(tmp_path, monkeypatch):
    from alphaquest.prop import runs
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        _, source = run_fixture(client)
        setup = save(client, setup_body(client, source)); check(client, setup)
        original = runs.replay_evaluation

        def broken(*args):
            summary = original(*args)
            summary["balance"] += Decimal("1")
            summary["equity"] = summary["balance"]
            return summary

        monkeypatch.setattr(runs, "replay_evaluation", broken)
        response = client.post(f"/api/prop-simulations/setups/{setup['id']}/run")
        assert response.status_code == 422 and "reconciliation" in response.json()["detail"]
        assert client.get(f"/api/prop-simulations/results?setup_id={setup['id']}").json()["total"] == 0
