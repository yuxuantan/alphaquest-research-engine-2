"""Independent replay parity, pure-feature contracts, and conservative reuse."""

from dataclasses import asdict, replace
from decimal import Decimal
import csv
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from alphaquest import backtest_data
from alphaquest.execution import execute
from alphaquest.optimization_cache import trial_key
from alphaquest.prepared_data import prepare_data
from alphaquest.strategies import registry
from alphaquest.strategy_features import Feature, create_strategy, prepare_features
from test_backtest_api import save_fixture
from test_optimization import client, optimization_body, start, wait_job
from test_vwap_pullback import CONFIG, parameters, scenario


def rows(client, job):
    assert job["status"] == "complete", job
    return client.get(f"/api/optimizations/{job['id']}/results").json()["items"]


def test_engine_identity_is_stable_across_script_and_repository_launch_paths(tmp_path):
    import subprocess
    import sys
    command = "from alphaquest.optimization_cache import engine_identity; print(engine_identity())"
    script = tmp_path / "identity.py"
    script.write_text(command)
    direct = subprocess.check_output([sys.executable, "-c", command], text=True).strip()
    external_script = subprocess.check_output([sys.executable, str(script)], text=True).strip()
    assert direct == external_script


def test_parse_once_and_date_range_has_identical_metadata_metrics_and_csv(client, monkeypatch):
    dataset = save_fixture(client)
    request = {**optimization_body(dataset["id"]), "from_date": "2026-01-05", "to_date": "2026-01-05"}
    original = backtest_data.parse_csv_row
    calls = []
    def parse(*args):
        calls.append(1)
        return original(*args)
    monkeypatch.setattr(backtest_data, "parse_csv_row", parse)
    baseline = wait_job(client, start(client, {**request, "prepare_data": False}))
    baseline_calls = len(calls)
    calls.clear()
    accelerated = wait_job(client, start(client, request))
    assert len(calls) == dataset["row_count"]
    assert baseline_calls == 6 * dataset["row_count"]  # original + date-selected CSV per trial
    for left, right in zip(rows(client, baseline), rows(client, accelerated), strict=True):
        assert left["metrics"] == right["metrics"]
        for kind in ("trades", "equity"):
            assert client.get(f"/api/backtests/{left['run_id']}/exports/{kind}").content == client.get(f"/api/backtests/{right['run_id']}/exports/{kind}").content
        records = [client.get(f"/api/backtests/{row['run_id']}").json() for row in (left, right)]
        assert records[0]["run_metadata"] == records[1]["run_metadata"]
    assert not list(client.app.state.runs.root.glob(".optimization-*"))


def test_reuse_across_jobs_preserves_reports_and_handles_partial_grid_overlap(client):
    dataset = save_fixture(client)
    request = {**optimization_body(dataset["id"]), "reuse_results": True}
    first = wait_job(client, start(client, request))
    before = rows(client, first)
    original_reports = {row["run_id"]: client.get(f"/api/backtests/{row['run_id']}/exports/report").content for row in before}
    request["parameter_ranges"]["contracts"]["end"] = 4
    second = wait_job(client, start(client, request))
    after = rows(client, second)
    assert second["reused_trials"] == 3 and second["completed_trials"] == 4
    assert [row["run_id"] for row in after[:3]] == [row["run_id"] for row in before]
    assert all(row["execution"]["reused"] for row in after[:3])
    assert Decimal(after[-1]["metrics"]["total_net_pnl"]) == 52
    third = wait_job(client, start(client, request))
    assert third["reused_trials"] == 4 and third["worker_pids"] == [] and not third["prepared_data"]
    assert client.get("/api/backtests").json()["total"] == 4
    for run_id, raw in original_reports.items():
        assert client.get(f"/api/backtests/{run_id}/exports/report").content == raw
    # An explicit fresh run computes every trial and creates separate reports.
    fresh = wait_job(client, start(client, {**request, "reuse_results": False}))
    assert fresh["reused_trials"] == 0
    assert client.get("/api/backtests").json()["total"] == 8


def test_cache_survives_restart_and_changed_engine_rejects_resume(client):
    from fastapi.testclient import TestClient
    from alphaquest.app import create_app
    dataset = save_fixture(client)
    request = {**optimization_body(dataset["id"]), "reuse_results": True}
    first = wait_job(client, start(client, request))
    with TestClient(create_app(client.app.state.runs.path.parent / "datasets.sqlite3")) as restarted:
        cached = wait_job(restarted, start(restarted, request))
        assert cached["reused_trials"] == 3
        assert [row["run_id"] for row in rows(restarted, cached)] == [row["run_id"] for row in rows(client, first)]
        # A saved incomplete attempt from different engine code cannot mix
        # its prior trials with calculations from the current engine.
        restarted.app.state.optimizations.update(first["id"], status="interrupted", engine_identity="old-engine")
        response = restarted.post(f"/api/optimizations/{first['id']}/resume")
        assert response.status_code == 422 and "Engine code has changed" in response.json()["detail"]


def test_changed_commission_and_date_selection_recompute_instead_of_reusing(client):
    dataset = save_fixture(client)
    request = {**optimization_body(dataset["id"]), "reuse_results": True}
    first = wait_job(client, start(client, request))
    cost = {**request, "execution_settings": {**request["execution_settings"], "commission_per_contract_per_side": "2"}}
    changed = wait_job(client, start(client, cost))
    assert changed["reused_trials"] == 0
    assert [Decimal(row["metrics"]["total_net_pnl"]) for row in rows(client, changed)] == [11, 22, 33]
    selected = wait_job(client, start(client, {**request, "from_date": "2026-01-05"}))
    assert selected["reused_trials"] == 0
    assert {row["run_id"] for row in rows(client, selected)}.isdisjoint(row["run_id"] for row in rows(client, first))


def test_legacy_job_without_engine_identity_can_resume_without_cache_reuse(client):
    dataset = save_fixture(client)
    job = wait_job(client, start(client, optimization_body(dataset["id"])))
    original = rows(client, job)[0]
    legacy = dict(job)
    for key in ("engine_identity", "reused_trials"):
        legacy.pop(key, None)
    legacy.update(status="interrupted", completed_trials=1)
    legacy["request"] = {key: value for key, value in job["request"].items() if key not in ("reuse_results", "prepare_data")}
    with client.app.state.runs.connect() as conn:
        conn.execute("DELETE FROM optimization_trials WHERE optimization_id=? AND trial>1", (job["id"],))
        conn.execute("UPDATE optimizations SET payload=? WHERE id=?", (json.dumps(legacy), job["id"]))
    response = client.post(f"/api/optimizations/{job['id']}/resume")
    assert response.status_code == 202, response.text
    resumed = wait_job(client, job["id"])
    assert resumed["status"] == "complete", resumed
    assert rows(client, resumed)[0] == original
    assert "engine_identity" not in resumed
    assert [Decimal(row["metrics"]["total_net_pnl"]) for row in rows(client, resumed)] == [13, 26, 39]


@pytest.mark.parametrize("change", ["missing", "modified", "catalog"])
def test_unavailable_or_corrupt_cached_report_is_recomputed(client, change):
    dataset = save_fixture(client)
    request = {**optimization_body(dataset["id"]), "reuse_results": True}
    first = wait_job(client, start(client, request))
    run_id = rows(client, first)[0]["run_id"]
    path = client.app.state.runs.root / run_id / "trades.csv"
    if change == "missing":
        path.unlink()
    elif change == "modified":
        path.write_bytes(path.read_bytes() + b"\n")
    else:
        with client.app.state.runs.connect() as conn:
            record = json.loads(conn.execute("SELECT manifest FROM runs WHERE id=?", (run_id,)).fetchone()[0])
            record["summary"]["total_net_pnl"] = "999"
            conn.execute("UPDATE runs SET manifest=? WHERE id=?", (json.dumps(record), run_id))
    second = wait_job(client, start(client, request))
    assert second["reused_trials"] == 2
    new_row = rows(client, second)[0]
    assert new_row["run_id"] != run_id and Decimal(new_row["metrics"]["total_net_pnl"]) == 13


def test_trial_identity_changes_for_every_execution_source_and_version_input(client):
    dataset = save_fixture(client)
    job = wait_job(client, start(client, optimization_body(dataset["id"])))
    values = {name: axis[0] for name, axis in job["axes"].items()}
    original = trial_key(job, values)
    variants = []
    for key in ("sha256", "source_timezone", "row_count", "instrument_settings"):
        variants.append({**job, "dataset": {**job["dataset"], key: "changed"}})
    for key in ("from_date", "to_date"):
        variants.append({**job, "request": {**job["request"], key: "2026-01-01"}})
    for key in job["execution_settings"]:
        variants.append({**job, "execution_settings": {**job["execution_settings"], key: "changed"}})
    variants.extend([{**job, "engine_identity": "changed"}, {**job, "strategy": {**job["strategy"], "source_sha256": "changed"}}])
    assert all(trial_key(variant, values) != original for variant in variants)
    assert trial_key(job, {**values, "contracts": 4}) != original
    # Scheduling choices do not alter an exact trial's mathematical identity.
    assert trial_key({**job, "request": {**job["request"], "workers": 7, "prepare_data": False}}, values) == original


def test_preparation_validates_entire_source_and_preserves_original_decimal_text(tmp_path):
    import hashlib
    from alphaquest.datasets import DatasetStore, validate_csv, InvalidDataset
    from alphaquest.optimization_worker import FrozenSource
    from alphaquest.backtest_data import DateRange, DatasetReadError
    source = DatasetStore(tmp_path / "datasets.sqlite3")
    raw = ("\ufeffDate,Time,Open,High,Low,Close,Volume,UpVol,DownVol\r\n"
           "01/05/2026,00:00,100.000000000000000000000001,102.00,99.000,101.0000,1e-5,0.00,0\r\n"
           "01/06/2026,00:00,100,102,99,101,1,0,0\r\n").encode()
    dataset = source.save(raw, validate_csv(raw, "synthetic.csv", "UTC"), "SYNTHETIC exact serialization", "TEST")
    prepared = prepare_data(source, dataset["id"], DateRange.parse("2026-01-05", "2026-01-05"), tmp_path / "prepared.bin")
    with prepared.selected() as selected:
        bars = list(selected.bars)
    assert len(bars) == 1
    assert bars[0].open.as_tuple() == Decimal("100.000000000000000000000001").as_tuple()
    assert bars[0].source_fields[5:] == ("101.0000", "1e-5", "0.00", "0")
    bad = raw.replace(b"01/06/2026,00:00,100,102,99,101", b"01/06/2026,00:00,100,102,103,101")
    path = tmp_path / "source.csv"
    path.write_bytes(bad)
    # A hash mismatch rejects before parsing, including outside the selected date.
    with pytest.raises(DatasetReadError, match="bytes do not match"):
        prepare_data(FrozenSource(dataset, path), dataset["id"], DateRange.parse("2026-01-05"), tmp_path / "bad-hash.bin")
    # Even metadata matching the altered bytes cannot hide an invalid excluded row.
    changed = {**dataset, "sha256": hashlib.sha256(bad).hexdigest(), "bytes": len(bad)}
    with pytest.raises(InvalidDataset, match="Low"):
        prepare_data(FrozenSource(changed, path), dataset["id"], DateRange.parse("2026-01-05", "2026-01-05"), tmp_path / "bad-row.bin")


@pytest.mark.parametrize("short,month,ending", [(False, 1, "target"), (True, 7, "target"), (False, 7, "both")])
def test_cached_features_match_all_events_and_strategy_state_not_only_metrics(tmp_path, short, month, ending):
    from alphaquest.datasets import DatasetStore, validate_csv
    bars = scenario(short=short, month=month, ending=ending)
    text = io.StringIO(newline="")
    writer = csv.writer(text)
    writer.writerow(backtest_data.COLUMNS)
    writer.writerows(bar.source_fields for bar in bars)
    raw = text.getvalue().encode()
    source = DatasetStore(tmp_path / "datasets.sqlite3")
    dataset = source.save(raw, validate_csv(raw, "synthetic.csv", "UTC"), "SYNTHETIC feature parity", "TEST")
    prepared = prepare_data(source, dataset["id"], None, tmp_path / "bars.bin")
    definition = registry.get_strategy("vwap_pullback_risk_sizing")
    p = parameters(trade_longs=not short, trade_shorts=short)
    values = {key: str(value) if isinstance(value, Decimal) else value for key, value in asdict(p).items()}
    paths = prepare_features(definition, prepared, [values, values], tmp_path)
    assert len(paths) == 3
    plain = definition.create(p, CONFIG)
    reference = list(execute(iter(bars), plain, CONFIG))
    # Reopening the same immutable feature streams gives independent instances.
    for _ in range(2):
        with create_strategy(definition, p, CONFIG, paths) as cached:
            assert list(execute(iter(bars), cached, CONFIG)) == reference
            for name in ("adx_value", "ny_vwap", "orb_high", "orb_low", "trades_today", "active_stop", "active_target", "last_stop_high", "last_target_low"):
                assert getattr(cached, name) == getattr(plain, name)
    feature = definition.acceleration.features[0]
    assert feature.key(p) == feature.key(replace(p, position_size=2))
    assert feature.key(p) != feature.key(replace(p, adx_len=p.adx_len + 1))
    assert feature.key(p) != feature.key(replace(p, max_bars_back=p.max_bars_back + 2))
    assert feature.key(p) != replace(feature, version="2").key(p)


def test_new_strategy_can_declare_features_without_engine_changes(client, monkeypatch):
    original = registry.get_strategy("consecutive_green_hold")
    builds = []
    def feature(bars, parameters):
        builds.append(parameters.contracts)
        for bar in bars:
            yield bar.close * parameters.contracts
    def bind(strategy, readers):
        on_bar = strategy.on_bar
        def checked(bar, position):
            assert readers["scaled_close"].at(bar.bar_number) == bar.close * strategy.parameters.contracts
            return on_bar(bar, position)
        strategy.on_bar = checked
    module = SimpleNamespace(Parameters=original.module.Parameters, STRATEGY_ID="synthetic_future_strategy", DESCRIPTION="SYNTHETIC extensibility test", __file__=__file__)
    definition = registry.StrategyDefinition(module, original.factory,
                    SimpleNamespace(features=(Feature("scaled_close", "1", ("contracts",), feature),), bind=bind))
    monkeypatch.setitem(registry.STRATEGIES, module.STRATEGY_ID, definition)
    dataset = save_fixture(client)
    request = optimization_body(dataset["id"])
    request["strategy_id"] = module.STRATEGY_ID
    request["parameter_ranges"]["hold_minutes"] = {"start": 20, "end": 25, "step": 5}
    job = wait_job(client, start(client, request))
    assert job["prepared_data"] and job["cached_feature_series"] == 3
    assert sorted(builds) == [1, 2, 3]
    assert [Decimal(row["metrics"]["total_net_pnl"]) for row in rows(client, job)] == [13, 26, 39] * 2
