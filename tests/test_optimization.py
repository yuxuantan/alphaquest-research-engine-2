from dataclasses import asdict
from decimal import Decimal
import csv
import io
import json
from threading import Event
import time

from fastapi.testclient import TestClient
import pytest

from alphaquest.app import create_app
from alphaquest.optimization import combinations, grid
from alphaquest.optimization_api import ParameterRange
from alphaquest.strategies.registry import get_strategy
from alphaquest.strategies import consecutive_green_hold as sample
from test_backtest_api import save_fixture, body


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        yield client


def optimization_body(dataset_id):
    request = body(dataset_id)
    del request["strategy_parameters"]
    request.update(method="exhaustive", workers=1, parameter_ranges={
        "green_bar_count": {"start": 3, "end": 3, "step": 0},
        "hold_minutes": {"start": 20, "end": 20, "step": 0},
        "contracts": {"start": 1, "end": 3, "step": 1},
    })
    return request


def wait_job(client, job_id):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        job = client.get(f"/api/optimizations/{job_id}").json()
        if job["status"] not in ("queued", "running"):
            return job
        time.sleep(.02)
    pytest.fail("Optimization did not finish")


def start(client, request):
    response = client.post("/api/optimizations", json=request)
    assert response.status_code == 202, response.text
    return response.json()["id"]


def test_every_combination_matches_independent_arithmetic_and_regular_reports(client):
    dataset = save_fixture(client)
    request = optimization_body(dataset["id"])
    # Two axes: hold 20/25 (same final bar), contracts 1/2/3 = six distinct runs.
    request["parameter_ranges"]["hold_minutes"] = {"start": 20, "end": 25, "step": 5}
    job_id = start(client, request)
    job = wait_job(client, job_id)
    assert job["status"] == "complete", job
    assert job["completed_trials"] == job["total_trials"] == 6
    rows = client.get(f"/api/optimizations/{job_id}/results").json()["items"]
    assert len({row["run_id"] for row in rows}) == 6
    assert [(row["parameters"]["hold_minutes"], row["parameters"]["contracts"]) for row in rows] == [(h, q) for h in (20, 25) for q in (1, 2, 3)]
    for row in rows:
        q = row["parameters"]["contracts"]
        # Entry 100.25, exit 101.75, point value 10, two sides at 1 CU.
        assert Decimal(row["metrics"]["total_net_pnl"]) == 13 * q
        assert Decimal(row["metrics"]["total_gross_pnl"]) == 15 * q
        assert Decimal(row["metrics"]["total_commissions"]) == 2 * q
        assert row["metrics"]["trades_taken"] == 1
        report = client.get(f"/api/backtests/{row['run_id']}").json()
        assert report["run_metadata"]["strategy"]["parameters"] == row["parameters"]
        assert report["summary"]["total_net_pnl"] == row["metrics"]["total_net_pnl"]
    for column in ["trial", "run_id", *job["metric_columns"], *(f"param.{name}" for name in job["axes"])]:
        for direction in ("asc", "desc"):
            response = client.get(f"/api/optimizations/{job_id}/results", params={"sort": column, "direction": direction, "limit": 2, "offset": 1})
            assert response.status_code == 200, response.text
            assert response.json()["total"] == 6 and len(response.json()["items"]) == 2
    descending = client.get(f"/api/optimizations/{job_id}/results?sort=total_net_pnl&direction=desc").json()["items"]
    assert [Decimal(row["metrics"]["total_net_pnl"]) for row in descending] == [39, 39, 26, 26, 13, 13]
    exported = client.get(f"/api/optimizations/{job_id}/exports/results?sort=total_net_pnl&direction=desc")
    data = list(csv.DictReader(io.StringIO(exported.text)))
    assert [Decimal(row["total_net_pnl"]) for row in data] == [39, 39, 26, 26, 13, 13]
    assert client.get("/api/backtests").json()["total"] == 6


@pytest.mark.parametrize("spec", [
    {"start": 3, "end": 1, "step": 1},
    {"start": 1, "end": 2, "step": 0},
    {"start": 1, "end": 1, "step": 1},
    {"start": 1, "end": 2, "step": -1},
    {"start": 0, "end": 2, "step": 1},
    {"start": True, "end": 2, "step": 1},
    {"start": 1, "end": 2, "step": True},
    {"start": 1, "end": 2, "step": 0.5},
    {"start": 1, "end": 10001, "step": 1},
    {"start": "1", "end": "2", "step": "1"},
    {"start": 1, "end": 2, "step": 1, "step_count": 999},
])
def test_invalid_grids_save_nothing(client, spec):
    dataset = save_fixture(client)
    request = optimization_body(dataset["id"])
    request["parameter_ranges"]["contracts"] = spec
    response = client.post("/api/optimizations", json=request)
    assert response.status_code == 422, response.text
    assert client.get("/api/optimizations").json()["total"] == 0
    assert client.get("/api/backtests").json()["total"] == 0


def vwap_ranges():
    return {name: ParameterRange(start=str(value) if isinstance(value, Decimal) else value,
                                 end=str(value) if isinstance(value, Decimal) else value, step="0" if isinstance(value, Decimal) else 0)
            for name, value in asdict(get_strategy("vwap_pullback_risk_sizing").module.Parameters()).items()}


def test_decimal_and_boolean_grid_is_exact_and_coupled_validation_precedes_execution():
    definition = get_strategy("vwap_pullback_risk_sizing")
    ranges = vwap_ranges()
    ranges["mm_risk_pct"] = ParameterRange(start="0.10000000000000000000000000001", end="0.30000000000000000000000000003", step="0.10000000000000000000000000001")
    ranges["trade_shorts"] = ParameterRange(start=False, end=True, step=1)
    axes, total = grid(definition, ranges)
    assert total == 6
    assert axes["mm_risk_pct"] == ["0.10000000000000000000000000001", "0.20000000000000000000000000002", "0.30000000000000000000000000003"]
    assert axes["trade_shorts"] == [False, True]
    assert len(list(combinations(axes))) == 6
    ranges["mm_risk_pct"] = ParameterRange(start="0", end="1", step="0.3")
    assert grid(definition, ranges)[0]["mm_risk_pct"] == ["0", "0.3", "0.6", "0.9"]
    ranges = vwap_ranges()
    ranges["entry_start_time"] = ParameterRange(start=900, end=1000, step=50)
    # 09:50 is valid; an interior 09:75 must be caught before any run.
    ranges["entry_start_time"] = ParameterRange(start=950, end=1000, step=25)
    with pytest.raises(ValueError, match="HHMM"):
        grid(definition, ranges)
    ranges = vwap_ranges()
    ranges["stop_swing_len"] = ParameterRange(start=20, end=30, step=10)
    with pytest.raises(ValueError, match="max_bars_back"):
        grid(definition, ranges)
    for value in ("NaN", "Infinity", "1e1000000", "1e-1000000", "invalid"):
        ranges = vwap_ranges()
        ranges["mm_risk_pct"] = ParameterRange(start=value, end=value, step="0")
        with pytest.raises(ValueError):
            grid(definition, ranges)


def test_limit_missing_parameters_and_method_are_rejected(client):
    dataset = save_fixture(client)
    request = optimization_body(dataset["id"])
    request["parameter_ranges"]["contracts"] = {"start": 1, "end": 100, "step": 1}
    request["parameter_ranges"]["hold_minutes"] = {"start": 1, "end": 101, "step": 1}
    assert client.post("/api/optimizations", json=request).status_code == 422
    request = optimization_body(dataset["id"])
    for bad in ({**request, "method": "genetic"}, {**request, "parameter_ranges": {}}, {**request, "dataset_id": "missing"}):
        assert client.post("/api/optimizations", json=bad).status_code in (422, 404)
    assert client.get("/api/optimizations").json()["total"] == 0


def test_partial_failure_retains_saved_trials_and_never_reports_complete(client, monkeypatch):
    dataset = save_fixture(client)
    original = sample.ConsecutiveGreenHold.on_bar
    def fail_second(self, bar, position):
        if self.parameters.contracts == 2:
            raise RuntimeError("Second trial failed")
        return original(self, bar, position)
    monkeypatch.setattr(sample.ConsecutiveGreenHold, "on_bar", fail_second)
    job_id = start(client, optimization_body(dataset["id"]))
    job = wait_job(client, job_id)
    assert job["status"] == "failed" and job["completed_trials"] == 1
    assert "Second trial failed" in job["error"]
    assert client.get(f"/api/optimizations/{job_id}/results").json()["total"] == 1
    assert client.get("/api/backtests").json()["total"] == 1


def test_source_snapshot_survives_deletion_during_first_trial_and_restart(tmp_path, monkeypatch):
    database = tmp_path / "datasets.sqlite3"
    entered, release = Event(), Event()
    original = sample.ConsecutiveGreenHold.on_bar
    def pause(self, bar, position):
        if self.parameters.contracts == 1 and bar.bar_number == 2:
            entered.set()
            assert release.wait(10)
        return original(self, bar, position)
    monkeypatch.setattr(sample.ConsecutiveGreenHold, "on_bar", pause)
    with TestClient(create_app(database)) as client:
        dataset = save_fixture(client)
        job_id = start(client, optimization_body(dataset["id"]))
        try:
            assert entered.wait(5)
            job = client.get(f"/api/optimizations/{job_id}").json()
            assert job["status"] == "running" and job["completed_trials"] == 0
            assert client.delete(f"/api/datasets/{dataset['id']}").status_code == 204
        finally:
            release.set()
        job = wait_job(client, job_id)
        assert job["status"] == "complete", job
        rows = client.get(f"/api/optimizations/{job_id}/results").json()
    with TestClient(create_app(database)) as client:
        assert client.get(f"/api/optimizations/{job_id}").json() == job
        assert client.get(f"/api/optimizations/{job_id}/results").json() == rows
        # An abandoned job is explicitly interrupted on next start, preserving trials.
        client.app.state.optimizations.update(job_id, status="running")
    with TestClient(create_app(database)) as client:
        assert client.get(f"/api/optimizations/{job_id}").json()["status"] == "interrupted"
        assert client.get(f"/api/optimizations/{job_id}/results").json() == rows


def test_sort_uses_exact_numeric_order_nulls_last_and_stable_ties(client):
    dataset = save_fixture(client)
    job_id = start(client, optimization_body(dataset["id"]))
    wait_job(client, job_id)
    store = client.app.state.optimizations
    values = ["100000000000000000000000000000.1", "100000000000000000000000000000.2", "9"]
    with store.runs.connect() as conn:
        for trial, value in enumerate(values, 1):
            row = json.loads(conn.execute("SELECT payload FROM optimization_trials WHERE optimization_id=? AND trial=?", (job_id, trial)).fetchone()[0])
            row["metrics"]["total_net_pnl"] = value
            row["metrics"]["win_rate_pct"] = None if trial == 1 else "0"
            conn.execute("UPDATE optimization_trials SET payload=? WHERE optimization_id=? AND trial=?", (json.dumps(row), job_id, trial))
    for direction, expected in (("asc", [3, 1, 2]), ("desc", [2, 1, 3])):
        page = client.get(f"/api/optimizations/{job_id}/results", params={"sort": "total_net_pnl", "direction": direction}).json()
        assert [row["trial"] for row in page["items"]] == expected
        page = client.get(f"/api/optimizations/{job_id}/results", params={"sort": "win_rate_pct", "direction": direction}).json()
        assert [row["trial"] for row in page["items"]] == [2, 3, 1]
    for suffix in ("results", "exports/results"):
        for params in ({"sort": "unknown"}, {"direction": "drop table"}):
            assert client.get(f"/api/optimizations/{job_id}/{suffix}", params=params).status_code == 422
    for params in ({"offset": -1}, {"limit": 1001}, {"limit": 0}):
        assert client.get(f"/api/optimizations/{job_id}/results", params=params).status_code == 422


def test_result_page_snapshot_excludes_trials_published_after_its_job_snapshot(client):
    dataset = save_fixture(client)
    job_id = start(client, optimization_body(dataset["id"]))
    job = wait_job(client, job_id)
    # A reader holding a count of two must not see later-published trial three,
    # even when it would sort first (also protects multi-page CSV snapshots).
    job["completed_trials"] = 2
    with client.app.state.runs.connect() as conn:
        job["results_snapshot_rowid"] = conn.execute("SELECT rowid FROM optimization_trials WHERE optimization_id=? AND trial=2", (job_id,)).fetchone()[0]
    page = client.app.state.optimizations.page(job, "total_net_pnl", "desc", 0, 50)
    assert page["total"] == 2
    assert [row["trial"] for row in page["items"]] == [2, 1]


def test_zero_trade_grids_and_no_bars_date_selection_are_explicit(client):
    dataset = save_fixture(client)
    request = optimization_body(dataset["id"])
    request["parameter_ranges"]["green_bar_count"] = {"start": 8, "end": 9, "step": 1}
    job_id = start(client, request)
    assert wait_job(client, job_id)["status"] == "complete"
    rows = client.get(f"/api/optimizations/{job_id}/results?sort=win_rate_pct&direction=desc").json()["items"]
    assert len(rows) == 6
    assert all(row["metrics"]["trades_taken"] == 0 and row["metrics"]["win_rate_pct"] is None
               and Decimal(row["metrics"]["total_net_pnl"]) == 0 for row in rows)
    request["from_date"] = "2030-01-01"
    empty_id = start(client, request)
    job = wait_job(client, empty_id)
    assert job["status"] == "failed" and job["completed_trials"] == 0
    assert "No bars" in job["error"]


def test_queued_jobs_run_sequentially(client, monkeypatch):
    dataset = save_fixture(client)
    entered, release = Event(), Event()
    original = sample.ConsecutiveGreenHold.on_bar
    def pause(self, bar, position):
        if self.parameters.contracts == 1 and bar.bar_number == 2 and not release.is_set():
            entered.set()
            assert release.wait(10)
        return original(self, bar, position)
    monkeypatch.setattr(sample.ConsecutiveGreenHold, "on_bar", pause)
    first = start(client, optimization_body(dataset["id"]))
    try:
        assert entered.wait(5)
        second = start(client, optimization_body(dataset["id"]))
        assert client.get(f"/api/optimizations/{second}").json()["status"] == "queued"
        assert client.get("/api/backtests").json()["total"] == 0
    finally:
        release.set()
    assert wait_job(client, first)["status"] == "complete"
    assert wait_job(client, second)["status"] == "complete"
    assert client.get("/api/backtests").json()["total"] == 6


@pytest.mark.parametrize("start_value,end_value,count,expected", [
    (True, False, 2, [True, False]),
    (False, True, 2, [False, True]),
    (True, True, 1, [True]),
    (False, False, 1, [False]),
])
def test_boolean_grids_are_categorical_in_both_orders(start_value, end_value, count, expected):
    definition = get_strategy("vwap_pullback_risk_sizing")
    ranges = vwap_ranges()
    ranges["use_adx_elev"] = ParameterRange(start=start_value, end=end_value, step=0 if start_value == end_value else 1)
    axes, total = grid(definition, ranges)
    assert axes["use_adx_elev"] == expected
    assert total == count
    assert all(type(value) is bool for value in axes["use_adx_elev"])


@pytest.mark.parametrize("start_value,end_value,step", [
    (True, False, 0), (True, False, 2), (False, True, -1), (True, True, 1), (False, False, 1),
])
def test_invalid_boolean_steps_have_boolean_specific_errors(start_value, end_value, step):
    ranges = vwap_ranges()
    ranges["use_adx_elev"] = ParameterRange(start=start_value, end=end_value, step=step)
    with pytest.raises(ValueError, match="use_adx_elev: boolean step"):
        grid(get_strategy("vwap_pullback_risk_sizing"), ranges)


@pytest.mark.parametrize("start_value,end_value,step,expected", [
    (1, 6, 2, [1, 3, 5]), (1, 5, 2, [1, 3, 5]),
    (1, 2, 5, [1]), (3, 3, 0, [3]),
])
def test_integer_step_uses_end_as_inclusive_limit(start_value, end_value, step, expected):
    ranges = {name: ParameterRange(**spec) for name, spec in optimization_body("unused")["parameter_ranges"].items()}
    ranges["contracts"] = ParameterRange(start=start_value, end=end_value, step=step)
    axes, total = grid(get_strategy("consecutive_green_hold"), ranges)
    assert axes["contracts"] == expected and total == len(expected)


def test_step_grid_cartesian_product_is_24_actual_backtests(client):
    dataset = save_fixture(client)
    request = optimization_body(dataset["id"])
    request["parameter_ranges"] = {
        "green_bar_count": {"start": 2, "end": 3, "step": 1},
        "hold_minutes": {"start": 10, "end": 25, "step": 5},
        "contracts": {"start": 1, "end": 5, "step": 2},
    }
    job = wait_job(client, start(client, request))
    assert job["status"] == "complete"
    assert job["step_counts"] == {"green_bar_count": 2, "hold_minutes": 4, "contracts": 3}
    assert job["completed_trials"] == job["total_trials"] == 24
    rows = client.get(f"/api/optimizations/{job['id']}/results").json()["items"]
    expected = {(a, b, c) for a in (2, 3) for b in (10, 15, 20, 25) for c in (1, 3, 5)}
    assert {tuple(row["parameters"].values()) for row in rows} == expected
    assert client.get("/api/backtests").json()["total"] == 24
