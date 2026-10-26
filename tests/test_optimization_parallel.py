"""Real spawn workers, exact serial parity, out-of-order publication and failures."""

from datetime import datetime, timedelta
from decimal import Decimal
import csv
import io
import multiprocessing
import os
import time

import pytest

from alphaquest import optimization, optimization_api, optimization_worker
from alphaquest.optimization import MAX_WORKERS, DEFAULT_WORKERS
from test_optimization import client, optimization_body, start, wait_job
from test_backtest_api import save_fixture
from test_vwap_pullback import scenario, parameters
from dataclasses import asdict


# Top-level importable callables exercise real spawn and process crashes, not a
# thread substitute. The strategy, engine, reports and parent publisher stay real.
def gated_first_trial(trial, values, run_id):
    context = optimization_worker._context
    if trial == 1:
        deadline = time.monotonic() + 12
        while not (context.output_root / "release-first").exists():
            if time.monotonic() > deadline:
                raise RuntimeError("First-trial gate timed out")
            time.sleep(.01)
    elif (context.output_root / "fail-second").exists():
        raise RuntimeError("Controlled second-trial failure")
    return optimization_worker.run_trial(trial, values, run_id)


def crashing_trial(trial, values, run_id):
    if trial == 2:
        os._exit(17)
    return optimization_worker.run_trial(trial, values, run_id)


def wait_for(client, job_id, predicate):
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        job = client.get(f"/api/optimizations/{job_id}").json()
        if predicate(job):
            return job
        time.sleep(.02)
    pytest.fail(f"Condition not reached: {job}")


def workspace(client):
    return next(client.app.state.runs.root.glob(".optimization-*"))


def test_worker_settings_validation_and_trial_count_cap(client):
    settings = client.get("/api/optimizations/settings").json()
    assert 1 <= settings["default_workers"] == DEFAULT_WORKERS <= settings["max_workers"] == MAX_WORKERS <= 8
    dataset = save_fixture(client)
    for workers in (0, True, "2", 1.5, MAX_WORKERS + 1):
        request = {**optimization_body(dataset["id"]), "workers": workers}
        assert client.post("/api/optimizations", json=request).status_code == 422
    assert client.get("/api/optimizations").json()["total"] == 0
    request = optimization_body(dataset["id"])
    request["parameter_ranges"]["contracts"]["end"] = 1
    request["parameter_ranges"]["contracts"]["step"] = 0
    del request["workers"]
    job = wait_job(client, start(client, request))
    assert job["status"] == "complete" and job["worker_count"] == 1


@pytest.mark.skipif(MAX_WORKERS < 2, reason="Host allows one worker")
def test_parallel_matches_serial_full_reports_and_uses_distinct_processes(client):
    # Enough real replay work for both processes to start and overlap.
    stamp = datetime(2026, 1, 5)
    lines = ["Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol"]
    for minute in range(3000):
        lines.append((stamp + timedelta(minutes=minute)).strftime("%m/%d/%Y,%H:%M") + ",100,102,99,101,1,1,0")
    response = client.post("/api/datasets", params={"filename": "synthetic_parallel.csv", "name": "SYNTHETIC parallel parity", "source_timezone": "UTC", "tick_size": "0.25", "point_value": "10"}, content="\n".join(lines).encode())
    assert response.status_code == 201
    request = optimization_body(response.json()["id"])
    request["parameter_ranges"]["hold_minutes"] = {"start": 10, "end": 20, "step": 5}
    serial = wait_job(client, start(client, request))
    parallel = wait_job(client, start(client, {**request, "workers": 2}))
    assert serial["status"] == parallel["status"] == "complete", (serial, parallel)
    assert parallel["worker_count"] == 2 and len(parallel["worker_pids"]) == 2
    assert os.getpid() not in parallel["worker_pids"]
    rows = {}
    for job in (serial, parallel):
        rows[job["id"]] = client.get(f"/api/optimizations/{job['id']}/results").json()["items"]
    for left, right in zip(rows[serial["id"]], rows[parallel["id"]], strict=True):
        assert left["trial"] == right["trial"]
        assert left["parameters"] == right["parameters"]
        assert left["metrics"] == right["metrics"]
        for kind in ("trades", "equity"):
            assert client.get(f"/api/backtests/{left['run_id']}/exports/{kind}").content == client.get(f"/api/backtests/{right['run_id']}/exports/{kind}").content
    intervals = [(datetime.fromisoformat(row["execution"]["started_at_utc"]), datetime.fromisoformat(row["execution"]["finished_at_utc"]), row["execution"]["worker_pid"]) for row in rows[parallel["id"]]]
    assert any(a[2] != b[2] and max(a[0], b[0]) < min(a[1], b[1]) for a in intervals for b in intervals)
    assert not list(client.app.state.runs.root.glob(".optimization-*"))


@pytest.mark.skipif(MAX_WORKERS < 2, reason="Host allows one worker")
def test_parallel_vwap_boolean_decimal_types_and_nonzero_trades_match_serial(client):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow("Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol".split(","))
    writer.writerows(bar.source_fields for bar in scenario())
    response = client.post("/api/datasets", params={"filename": "synthetic_vwap.csv", "name": "SYNTHETIC VWAP parity", "source_timezone": "UTC", "tick_size": "0.25", "point_value": "20"}, content=buffer.getvalue())
    request = optimization_body(response.json()["id"])
    request["strategy_id"] = "vwap_pullback_risk_sizing"
    request["parameter_ranges"] = {key: {"start": str(value) if isinstance(value, Decimal) else value, "end": str(value) if isinstance(value, Decimal) else value, "step": "0" if isinstance(value, Decimal) else 0} for key, value in asdict(parameters()).items()}
    request["parameter_ranges"]["trade_longs"] = {"start": True, "end": False, "step": 1}
    request["parameter_ranges"]["mm_risk_pct"] = {"start": "1.1", "end": "1.3", "step": "0.1"}
    first = wait_job(client, start(client, request))
    second = wait_job(client, start(client, {**request, "workers": 2}))
    assert first["status"] == second["status"] == "complete"
    left = client.get(f"/api/optimizations/{first['id']}/results").json()["items"]
    right = client.get(f"/api/optimizations/{second['id']}/results").json()["items"]
    for serial, parallel in zip(left, right, strict=True):
        assert serial["parameters"] == parallel["parameters"] and serial["metrics"] == parallel["metrics"]
        assert type(parallel["parameters"]["trade_longs"]) is bool
        assert type(parallel["parameters"]["mm_risk_pct"]) is str
    assert [row["metrics"]["trades_taken"] for row in right] == [1, 0, 1, 0, 1, 0]


@pytest.mark.skipif(MAX_WORKERS < 2, reason="Host allows one worker")
def test_out_of_order_results_and_csv_snapshot_do_not_depend_on_trial_number(client, monkeypatch):
    dataset = save_fixture(client)
    monkeypatch.setattr(optimization, "run_trial", gated_first_trial)
    job_id = start(client, {**optimization_body(dataset["id"]), "workers": 2})
    try:
        job = wait_for(client, job_id, lambda job: job["completed_trials"] >= 1)
        rows = client.app.state.optimizations.page(job, "trial", "asc", 0, 50)
        assert rows["total"] == len(rows["items"]) == job["completed_trials"]
        assert rows["items"][0]["trial"] == 2
        exported = client.get(f"/api/optimizations/{job_id}/exports/results")
        assert "\n1," not in exported.text
        assert client.get("/api/optimizations").status_code == 200
        # All children use the frozen file, including the gated first trial
        # which has not read its bars yet when the original is deleted.
        assert client.delete(f"/api/datasets/{dataset['id']}").status_code == 204
    finally:
        (workspace(client) / "release-first").touch()
    final = wait_job(client, job_id)
    assert final["status"] == "complete" and final["completed_trials"] == 3
    assert client.app.state.optimizations.page(job, "trial", "asc", 0, 50) == rows
    # Legacy job records still use the prior serial snapshot boundary.
    legacy = {key: value for key, value in final.items() if key != "results_snapshot_rowid"}
    legacy["completed_trials"] = 2
    assert [row["trial"] for row in client.app.state.optimizations.page(legacy, "trial", "asc", 0, 50)["items"]] == [1, 2]


@pytest.mark.skipif(MAX_WORKERS < 2, reason="Host allows one worker")
def test_parallel_failure_stops_new_trials_and_retains_other_inflight_success(client, monkeypatch):
    dataset = save_fixture(client)
    # Marker is installed before submitting workers, in the coordinator's owned workspace.
    def run_with_failure(job_id, context, trials, workers, active, progress, save_progress, failures):
        (context.output_root / "fail-second").touch()
        return run_parallel(job_id, context, trials, workers, active, progress, save_progress, failures)
    store = client.app.state.optimizations
    run_parallel = store._run_parallel
    monkeypatch.setattr(store, "_run_parallel", run_with_failure)
    monkeypatch.setattr(optimization, "run_trial", gated_first_trial)
    job_id = start(client, {**optimization_body(dataset["id"]), "workers": 2})
    try:
        job = wait_for(client, job_id, lambda job: bool(job["failed_trials"]))
        assert job["status"] == "running"  # first trial is still safely finishing
    finally:
        (workspace(client) / "release-first").touch()
    job = wait_job(client, job_id)
    assert job["status"] == "failed" and job["completed_trials"] == 1
    assert "Controlled second-trial failure" in job["error"]
    rows = client.get(f"/api/optimizations/{job_id}/results").json()["items"]
    assert [row["trial"] for row in rows] == [1]
    assert not list(store.runs.root.glob(".optimization-*"))


@pytest.mark.skipif(MAX_WORKERS < 2, reason="Host allows one worker")
def test_crashed_process_is_failed_without_hanging_or_lingering_children(client, monkeypatch):
    dataset = save_fixture(client)
    before = {child.pid for child in multiprocessing.active_children()}
    monkeypatch.setattr(optimization, "run_trial", crashing_trial)
    job_id = start(client, {**optimization_body(dataset["id"]), "workers": 2})
    job = wait_job(client, job_id)
    assert job["status"] == "failed" and job["failed_trials"], job
    assert not list(client.app.state.runs.root.glob(".optimization-*"))
    assert {child.pid for child in multiprocessing.active_children()} <= before
