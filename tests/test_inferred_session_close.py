"""Independent expected exits for the explicitly permitted session lookahead."""

from dataclasses import asdict, replace
from datetime import timedelta
from decimal import Decimal
import csv
import io
import json

from research_fixtures import ResearchClient as TestClient
import pytest

from alphaquest.app import create_app
from alphaquest.execution import Trade, execute
from alphaquest.reporting import json_value
from alphaquest.strategies.vwap_pullback_risk_sizing import VwapPullbackRiskSizing
from test_vwap_pullback import CONFIG, CT, bar, parameters, replay, scenario


D = Decimal


def session_rows(*, close=(12, 0), short=False, month=1, missing_cutoff=False, evening=False):
    rows = scenario(month=month)[:123]
    cutoff = (close[0], close[1] - 5) if close[1] >= 5 else (close[0] - 1, close[1] + 55)
    if close >= (16, 0):
        cutoff = (15, 55)
    rows.append(bar(124, 9, 3, "116", "120", "110", "116", month=month))
    # Last available bar before a missing exact cutoff: independent reference117.
    if missing_cutoff:
        h, m = cutoff
        rows.append(bar(125, h, m - 1, "116", "120", "110", "117", month=month))
    else:
        rows.append(bar(125, *cutoff, "117", "120", "110", "118", month=month))
    rows.append(bar(126, *close, "120", "140", "100", "125", month=month))
    if evening:
        rows.append(bar(127, 17, 1, "125", "150", "100", "130", month=month))
        rows.append(bar(128, 23, 59, "130", "150", "100", "135", month=month))
    if short:
        rows = [replace(row, open=200-row.open, high=200-row.low, low=200-row.high, close=200-row.close) for row in rows]
    return rows


@pytest.mark.parametrize("close,expected", [((16, 0), "15:55"), ((12, 0), "11:55"), ((12, 15), "12:10")])
@pytest.mark.parametrize("short", [False, True])
@pytest.mark.parametrize("month", [1, 7])
def test_exact_cutoff_real_close_prices_and_reconciled_costs(close, expected, short, month):
    strategy, trades, events = replay(session_rows(close=close, short=short, month=month),
        parameters(use_eod_flat=True, trade_longs=not short, trade_shorts=short, max_trades_per_day=5))
    assert len(trades) == 1
    trade = trades[0]
    assert trade.exit_reason == "eod_flat"
    assert trade.exit_time_utc.astimezone(CT).strftime("%H:%M") == expected
    assert trade.exit_deadline_utc == trade.exit_time_utc
    assert trade.exit_reference_price == (82 if short else 118)
    assert trade.exit_fill_price == D("82.25" if short else "117.75")
    assert (trade.gross_pnl, trade.total_commissions, trade.net_pnl) == (50, 2, 48)
    assert events[-1].equity == 10048
    assert strategy.trades_today == 1
    assert strategy.session_flattening["sessions"] == 1
    assert strategy.session_flattening["lookahead"] is True


def test_last_evening_bars_do_not_shift_daytime_close_and_incomplete_evening_cannot_enter():
    strategy, trades, _ = replay(session_rows(evening=True), parameters(use_eod_flat=True))
    assert len(trades) == 1 and trades[0].exit_time_utc.astimezone(CT).strftime("%H:%M") == "11:55"
    metadata = strategy.session_flattening
    assert metadata["sessions"] == 2 and metadata["sessions_without_cutoff_bar"] == 1
    assert metadata["examples"][0]["inferred_close"].endswith("12:00:00-06:00")


def test_missing_cutoff_uses_previous_real_bar_without_inventing_a_price():
    strategy, trades, _ = replay(session_rows(missing_cutoff=True), parameters(use_eod_flat=True))
    assert trades[0].exit_time_utc.astimezone(CT).strftime("%H:%M") == "11:54"
    assert trades[0].exit_reference_price == 117 and trades[0].net_pnl == 28
    assert strategy.session_flattening["sessions_using_earlier_bar"] == 1


@pytest.mark.parametrize("kind,net", [("target", D(293)), ("stop", D(-512))])
def test_exits_before_cutoff_are_preserved(kind, net):
    rows = session_rows()
    rows[123] = (bar(124, 9, 3, "116", "131", "110", "120") if kind == "target"
                 else bar(124, 9, 3, "116", "120", "89", "110"))
    _, trades, _ = replay(rows, parameters(use_eod_flat=True))
    assert trades[0].exit_reason == ("take_profit" if kind == "target" else "stop_loss")
    assert trades[0].exit_bar_number == 124 and trades[0].net_pnl == net


def test_bracket_touch_on_cutoff_bar_precedes_close_flatten():
    rows = session_rows()
    rows[124] = replace(rows[124], high=D(131))
    _, trades, _ = replay(rows, parameters(use_eod_flat=True))
    assert trades[0].exit_reason == "take_profit" and trades[0].net_pnl == 293


def test_gapped_pending_entry_at_cutoff_is_cancelled_and_cannot_reopen():
    rows = scenario()[:122]
    rows.extend([bar(123, 11, 55, "115", "120", "110", "118"),
                 bar(124, 12, 0, "120", "140", "100", "125")])
    _, trades, events = replay(rows, parameters(use_eod_flat=True, max_trades_per_day=5))
    assert trades == [] and all(event.position_contracts == 0 for event in events)


def test_truncated_final_session_is_deliberately_treated_as_early_close():
    strategy, trades, _ = replay(scenario(), parameters(use_eod_flat=True))
    assert trades == []
    example = strategy.session_flattening["examples"][0]
    assert "09:03:00" in example["inferred_close"]
    assert "08:58:00" in example["executed_cutoff"]


def test_no_available_bar_before_cutoff_disables_the_session():
    strategy, trades, _ = replay([bar(1, 12, 0)], parameters(use_eod_flat=True))
    assert trades == []
    assert strategy.session_flattening["sessions_without_cutoff_bar"] == 1


def test_legacy_next_open_eod_is_gone_but_explicit_eod_off_remains_available():
    _, trades, _ = replay(session_rows(), parameters(use_eod_flat=False))
    assert trades[0].exit_reason == "take_profit" and trades[0].net_pnl == 293
    with pytest.raises(ValueError, match="requires execute"):
        VwapPullbackRiskSizing(parameters(use_eod_flat=True), execution_config=CONFIG).on_bar(bar(1, 8, 0), None)


def test_multiple_sessions_remain_flat_until_next_day_and_reset_normally():
    rows = session_rows()
    rows.append(bar(len(rows) + 1, 23, 1))  # Original daily-reset crossing.
    rows.extend(replace(row, timestamp_utc=row.timestamp_utc + timedelta(days=1)) for row in session_rows(close=(16, 0)))
    rows = [replace(row, bar_number=i) for i, row in enumerate(rows, 1)]
    strategy, trades, events = replay(rows, parameters(use_eod_flat=True))
    assert len(trades) == 2
    assert [t.exit_time_utc.astimezone(CT).strftime("%H:%M") for t in trades] == ["11:55", "15:55"]
    assert [t.net_pnl for t in trades] == [48, 48] and events[-1].equity == 10096
    assert strategy.session_flattening["sessions"] == 2


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow("Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol".split(","))
    for row in rows:
        writer.writerow([row.date, row.time, row.open, row.high, row.low, row.close, row.volume, row.up_vol, row.down_vol])
    return stream.getvalue().encode()


def request_body(dataset_id, **overrides):
    return {"dataset_id": dataset_id, "strategy_id": "vwap_pullback_risk_sizing",
        "strategy_parameters": json.loads(json.dumps(asdict(parameters(use_eod_flat=True, **overrides)), default=json_value)),
        "execution_settings": {"initial_capital": "10000", "slippage_ticks": 1, "commission_per_contract_per_side": "1"}}


def test_api_durable_report_exports_and_selected_range_use_the_new_rule(tmp_path):
    database = tmp_path / "datasets.sqlite3"
    raw = csv_bytes(session_rows())
    with TestClient(create_app(database)) as client:
        saved = client.post("/api/datasets", params={"filename": "synthetic-early-close.csv", "name": "SYNTHETIC early close",
            "source_timezone": "UTC", "tick_size": "0.25", "point_value": "20"}, content=raw)
        assert saved.status_code == 201, saved.text
        dataset_id = saved.json()["id"]
        body = request_body(dataset_id)
        response = client.post("/api/backtests", json={**body, "from_date": "2026-01-05", "to_date": "2026-01-05"})
        assert response.status_code == 201, response.text
        record = response.json()
        run_id = record["id"]
        assert D(record["summary"]["total_net_pnl"]) == 48
        assert record["execution_assumption"].endswith("inferred_session_close")
        flatten = record["run_metadata"]["strategy"]["session_flattening"]
        assert flatten["enabled"] and flatten["lookahead"] and flatten["sessions"] == 1
        assert flatten["examples"][0]["executed_cutoff"].endswith("11:55:00-06:00")
        exports = {kind: client.get(f"/api/backtests/{run_id}/exports/{kind}").content for kind in ("trades", "equity", "report")}
        assert b"eod_flat" in exports["trades"] and b"48.00" in exports["equity"]
        from research_fixtures import reserved_source
        assert client.get(f"/api/datasets/{dataset_id}/csv").content == reserved_source(raw)[0]
        # A separate run with EOD disabled leaves the first immutable result intact.
        body["strategy_parameters"]["use_eod_flat"] = False
        baseline = client.post("/api/backtests", json=body)
        assert baseline.status_code == 201, baseline.text
        assert D(baseline.json()["summary"]["total_net_pnl"]) == 293
        for kind, content in exports.items():
            assert client.get(f"/api/backtests/{run_id}/exports/{kind}").content == content
    with TestClient(create_app(database)) as restarted:
        assert restarted.get(f"/api/backtests/{run_id}").json()["run_metadata"]["strategy"]["session_flattening"] == flatten
        assert restarted.get(f"/api/backtests/{run_id}/exports/trades").content == exports["trades"]


def test_optimization_workers_prepared_features_and_full_detail_match_inferred_exits(tmp_path):
    from test_optimization import start, wait_job
    database = tmp_path / "datasets.sqlite3"
    with TestClient(create_app(database)) as client:
        saved = client.post("/api/datasets", params={"filename": "synthetic-close.csv", "name": "SYNTHETIC optimization close",
            "source_timezone": "UTC", "tick_size": "0.25", "point_value": "20"}, content=csv_bytes(session_rows()))
        assert saved.status_code == 201, saved.text
        body = request_body(saved.json()["id"])
        values = body.pop("strategy_parameters")
        ranges = {name: {"start": value, "end": value, "step": "0" if type(value) is str else 0}
                  for name, value in values.items()}
        ranges["position_size"] = {"start": 1, "end": 3, "step": 1}
        body.update(method="exhaustive", workers=2, reuse_results=False, parameter_ranges=ranges)
        cached = wait_job(client, start(client, {**body, "prepare_data": True}))
        plain = wait_job(client, start(client, {**body, "prepare_data": False}))
        assert cached["status"] == plain["status"] == "complete", (cached, plain)
        assert cached["cached_feature_series"] == 3 and plain["cached_feature_series"] == 0
        results = []
        for job in (cached, plain):
            rows = client.get(f"/api/optimizations/{job['id']}/results").json()["items"]
            rows.sort(key=lambda row: row["parameters"]["position_size"])
            assert [D(row["metrics"]["total_net_pnl"]) for row in rows] == [48, 96, 144]
            results.append(rows)
        for first, second in zip(*results):
            for kind in ("trades", "equity"):
                assert client.get(f"/api/backtests/{first['run_id']}/exports/{kind}").content == client.get(f"/api/backtests/{second['run_id']}/exports/{kind}").content
        compact_id = results[0][0]["run_id"]
        response = client.post(f"/api/backtests/{compact_id}/detailed")
        assert response.status_code == 201, response.text
        assert D(response.json()["summary"]["total_net_pnl"]) == 48
