"""Compact trials retain ordinary reports, exact trades, and optional full detail."""

import gzip
import json
from decimal import Decimal

import pytest

from test_optimization import client, optimization_body, start, wait_job
from test_backtest_api import save_fixture


def compact_trial(client):
    dataset = save_fixture(client)
    job = wait_job(client, start(client, optimization_body(dataset["id"])))
    assert job["status"] == "complete"
    row = client.get(f"/api/optimizations/{job['id']}/results").json()["items"][0]
    return client.get(f"/api/backtests/{row['run_id']}").json()


def test_compact_trial_downloads_and_compressed_detail_reuse_preserve_original(client):
    compact = compact_trial(client)
    run_id = compact["id"]
    report = client.get(f"/api/backtests/{run_id}/exports/report").json()
    assert report["report_storage"]["detail"] == "compact"
    assert "trades" not in report and "equity" not in report
    assert compact["summary"]["total_net_pnl"] == "13.00"
    original = {name: client.get(f"/api/backtests/{run_id}/exports/{name}").content for name in ("trades", "equity")}
    full = client.post(f"/api/backtests/{run_id}/detailed")
    assert full.status_code == 201, full.text
    full = full.json()
    assert full["id"] != run_id
    assert full["run_metadata"]["detailed_from_run_id"] == run_id
    assert full["summary"] == compact["summary"]
    assert full["report_storage"] == {**compact["report_storage"], "detail": "full", "compression": "gzip", "per_bar_equity_retained": True}
    download = client.get(f"/api/backtests/{full['id']}/exports/report")
    assert download.headers["content-type"] == "application/gzip"
    expanded = json.loads(gzip.decompress(download.content))
    assert len(expanded["equity"]) == compact["run_metadata"]["selection"]["row_count"] + 1
    assert len(expanded["trades"]) == compact["summary"]["trades_taken"]
    assert Decimal(expanded["equity"][-1]["equity"]) == 10013
    for name in original:
        assert client.get(f"/api/backtests/{full['id']}/exports/{name}").content == original[name]
    assert client.get(f"/api/backtests/{run_id}").json() == compact
    assert client.post(f"/api/backtests/{run_id}/detailed").json() == full
    assert client.get("/api/backtests").json()["total"] == 4
    assert client.post(f"/api/backtests/{full['id']}/detailed").status_code == 409


def test_duplicate_detailed_replay_is_rejected_while_active(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from alphaquest.strategies import consecutive_green_hold as sample
    record = compact_trial(client)
    entered, release = Event(), Event()
    original = sample.ConsecutiveGreenHold.on_bar
    def pause(self, bar, position):
        if bar.bar_number == 2:
            entered.set()
            assert release.wait(10)
        return original(self, bar, position)
    monkeypatch.setattr(sample.ConsecutiveGreenHold, "on_bar", pause)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.post, f"/api/backtests/{record['id']}/detailed")
        try:
            assert entered.wait(5)
            response = client.post(f"/api/backtests/{record['id']}/detailed")
            assert response.status_code == 409
        finally:
            release.set()
        assert pending.result().status_code == 201
    assert client.get("/api/backtests").json()["total"] == 4


@pytest.mark.parametrize("boundary", ["dataset_missing", "strategy_changed", "replay_changed"])
def test_detailed_replay_rejects_missing_or_changed_inputs_without_overwriting(client, monkeypatch, boundary):
    from alphaquest.strategies import consecutive_green_hold as sample
    record = compact_trial(client)
    if boundary == "dataset_missing":
        client.delete(f"/api/datasets/{record['run_metadata']['dataset']['id']}")
    elif boundary == "strategy_changed":
        with client.app.state.runs.connect() as conn:
            changed = json.loads(json.dumps(record))
            changed["run_metadata"]["strategy"]["source_sha256"] = "changed"
            conn.execute("UPDATE runs SET manifest=? WHERE id=?", (json.dumps(changed), record["id"]))
    else:
        monkeypatch.setattr(sample.ConsecutiveGreenHold, "on_bar", lambda *args: None)
    response = client.post(f"/api/backtests/{record['id']}/detailed")
    assert response.status_code == 422, response.text
    assert client.get("/api/backtests").json()["total"] == 3
    report = client.get(f"/api/backtests/{record['id']}/exports/report").json()
    assert report["report_storage"]["detail"] == "compact"
    assert not list(client.app.state.runs.root.glob(".pending-*"))
    assert not client.app.state.runs.detail_active
