"""Date selection uses source-local calendar days, before strategy replay."""

import csv
from datetime import datetime
from decimal import Decimal
import io
import json
import subprocess
import sys
from uuid import uuid4

import pytest

from alphaquest import backtest_data
from alphaquest.backtest_data import DateRange, read_selected_bars
from alphaquest.datasets import COLUMNS, DatasetStore, validate_csv
from test_backtest_api import client, body


def raw_days():
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(COLUMNS)
    for day in (4, 5, 6):
        for clock, close in zip(("00:00", "00:01", "00:02", "00:03", "23:59"), (100, 101, 102, 103, 104)):
            writer.writerow([f"01/{day:02d}/2026", clock, str(Decimal(close) - Decimal("0.50")), close + 1, close - 1, close, "100.00", "45.0", "55.00"])
    return stream.getvalue().encode()


def save_range_fixture(client):
    response = client.post("/api/datasets", params={"filename": "three-days.csv", "name": "Date range review", "source_timezone": "Asia/Singapore", "tick_size": "0.25", "point_value": "10"}, content=raw_days())
    assert response.status_code == 201, response.text
    return response.json()


def test_reader_preserves_source_fields_rebases_bars_and_converts_local_day(tmp_path):
    store = DatasetStore(tmp_path / "datasets.sqlite3")
    raw = raw_days()
    saved = store.save(raw, validate_csv(raw, "days.csv", "Asia/Singapore"), "Days", "SYNTHETIC")
    source_rows = list(csv.reader(io.StringIO(raw.decode())))[1:]
    with read_selected_bars(store, saved["id"], DateRange.parse("2026-01-05", "2026-01-05")) as selected:
        assert selected.row_count == 5
        bars = list(selected.bars)
        assert selected.metadata == {"from_date": "2026-01-05", "to_date": "2026-01-05", "source_timezone": "Asia/Singapore", "warmup": "none",
                                     "row_count": 5, "start_utc": "2026-01-04T16:00:00Z", "end_utc": "2026-01-05T15:59:00Z",
                                     "first_source_bar_number": 6, "last_source_bar_number": 10}
    assert [bar.bar_number for bar in bars] == [1, 2, 3, 4, 5]
    assert [bar.source_fields for bar in bars] == [tuple(row) for row in source_rows[5:10]]
    assert str(bars[0].volume) == "100.00"
    assert store.get(saved["id"]) == saved and store.get(saved["id"], download=True) == raw


@pytest.mark.parametrize("bounds,count,first,last", [
    ({}, 15, 1, 15), ({"from_date": "2026-01-05"}, 10, 6, 15),
    ({"to_date": "2026-01-05"}, 10, 1, 10),
    ({"from_date": "2026-01-05", "to_date": "2026-01-05"}, 5, 6, 10),
    ({"from_date": "2026-01-01", "to_date": "2026-01-31"}, 15, 1, 15),
])
def test_api_saves_range_and_exact_selected_progress(client, bounds, count, first, last):
    dataset = save_range_fixture(client)
    operation = str(uuid4())
    response = client.post("/api/backtests", params={"progress_id": operation}, json={**body(dataset["id"]), **bounds})
    assert response.status_code == 201, response.text
    record = response.json()
    selection = record["run_metadata"]["selection"]
    assert selection["row_count"] == count
    assert selection["first_source_bar_number"] == first and selection["last_source_bar_number"] == last
    assert record["run_metadata"]["dataset"]["row_count"] == 16  # 15 oracle bars + one reserved fixture bar
    assert record["summary"]["trades_taken"] == count // 5
    assert Decimal(record["summary"]["total_net_pnl"]) == Decimal(26) * (count // 5)
    progress = client.get("/api/progress/" + operation).json()
    assert progress["stage"] == "done" and progress["bars_processed"] == progress["total_bars"] == count
    assert record["reconciliation"]["observed_bar_count"] == record["reconciliation"]["expected_bar_count"] == count
    assert client.get(f"/api/backtests/{record['id']}").json() == record
    assert client.get(f"/api/datasets/{dataset['id']}").json() == dataset
    from research_fixtures import reserved_source
    assert client.get(f"/api/datasets/{dataset['id']}/csv").content == reserved_source(raw_days())[0]


def test_selection_end_is_end_of_data_and_no_outside_bars_warm_up_strategy(client):
    saved = save_range_fixture(client)
    request = {**body(saved["id"]), "from_date": "2026-01-05", "to_date": "2026-01-05"}
    request["strategy_parameters"]["hold_minutes"] = 2000
    response = client.post("/api/backtests", json=request)
    assert response.status_code == 201, response.text
    record = response.json()
    trade = client.get(f"/api/backtests/{record['id']}/trades").json()["items"][0]
    assert trade["entry_bar_number"] == 3 and trade["exit_bar_number"] == 5
    assert trade["entry_time_utc"] == "2026-01-04T16:02:00Z"
    assert trade["exit_time_utc"] == "2026-01-05T15:59:00Z"
    assert trade["exit_reason"] == "end_of_data"
    assert record["period_start_utc"] == "2026-01-04T16:00:00Z"
    assert record["period_end_utc"] == "2026-01-05T15:59:00Z"
    assert Decimal(trade["net_pnl"]) == 26


@pytest.mark.parametrize("bounds", [
    {"from_date": "2026-01-06", "to_date": "2026-01-04"},
    {"from_date": "2026-02-30"}, {"to_date": "2026-01-05T00:00:00Z"},
    {"from_date": "20260105"}, {"to_date": ""}, {"from_date": 20260105}, {"to_date": True},
])
def test_invalid_dates_are_server_rejected(client, bounds):
    saved = save_range_fixture(client)
    response = client.post("/api/backtests", json={**body(saved["id"]), **bounds})
    assert response.status_code == 422, response.text
    assert client.get("/api/backtests").json()["total"] == 0


def test_empty_range_fails_without_a_completed_report(client):
    saved = save_range_fixture(client)
    operation = str(uuid4())
    response = client.post("/api/backtests", params={"progress_id": operation}, json={**body(saved["id"]), "from_date": "2026-01-07"})
    assert response.status_code == 422
    assert client.get("/api/progress/" + operation).status_code == 404  # rejected before execution
    assert client.get("/api/backtests").json()["total"] == 0
    assert list(client.app.state.runs.root.iterdir()) == []


def test_range_reader_replays_incrementally_after_disk_backed_preparation(tmp_path, monkeypatch):
    store = DatasetStore(tmp_path / "datasets.sqlite3")
    raw = raw_days()
    saved = store.save(raw, validate_csv(raw, "days.csv", "Asia/Singapore"), "Days", "SYNTHETIC")
    original = backtest_data._iter_bars
    reads = [0, 0]
    phases = []
    def tracked(*args):
        phase = len(phases)
        phases.append(phase)
        for bar in original(*args):
            reads[phase] += 1
            yield bar
    monkeypatch.setattr(backtest_data, "_iter_bars", tracked)
    with read_selected_bars(store, saved["id"], DateRange.parse("2026-01-05")) as selected:
        assert selected.row_count == 10 and reads == [15, 0]
        next(selected.bars)
        assert reads == [15, 1]


def test_dst_day_uses_local_calendar_boundaries(tmp_path):
    rows = ["03/07/2026,23:59", "03/08/2026,00:00", "03/08/2026,01:59", "03/08/2026,03:00", "03/08/2026,23:59", "03/09/2026,00:00"]
    raw = (",".join(COLUMNS) + "\n" + "\n".join(row + ",100,101,99,100,0,0,0" for row in rows) + "\n").encode()
    store = DatasetStore(tmp_path / "datasets.sqlite3")
    saved = store.save(raw, validate_csv(raw, "dst.csv", "America/New_York"), "DST", "SYNTHETIC")
    with read_selected_bars(store, saved["id"], DateRange.parse("2026-03-08", "2026-03-08")) as selected:
        bars = list(selected.bars)
    assert len(bars) == 4
    assert bars[0].timestamp_utc == datetime.fromisoformat("2026-03-08T05:00:00Z")
    assert bars[-1].timestamp_utc == datetime.fromisoformat("2026-03-09T03:59:00Z")


def test_cli_accepts_the_same_date_selection(tmp_path):
    store = DatasetStore(tmp_path / "datasets.sqlite3")
    raw = raw_days()
    saved = store.save(raw, validate_csv(raw, "days.csv", "Asia/Singapore"), "Days", "SYNTHETIC")
    store.set_instrument_settings(saved["id"], "0.25", "10")
    command = [sys.executable, "-m", "alphaquest.run_backtest", "--database", str(store.path), "--dataset-id", saved["id"], "--output", str(tmp_path / "report"),
               "--is-start", "2026-01-05", "--is-end", "2026-01-05", "--oos-start", "2026-01-06", "--oos-end", "2026-01-06", "--contracts", "2", "--initial-capital", "10000", "--slippage-ticks", "1", "--commission-per-contract-per-side", "1"]
    response = subprocess.run(command, capture_output=True, text=True, check=True)
    assert json.loads(response.stdout)["summary"]["trades_taken"] == 1
    report = json.loads((tmp_path / "report/report.json").read_text())
    assert report["run_metadata"]["selection"]["row_count"] == 5
    assert Decimal(report["summary"]["total_net_pnl"]) == 26
