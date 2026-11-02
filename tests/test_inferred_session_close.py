"""Independent expected exits for causal calendar session cutoffs."""

from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
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


def retime(row, day):
    local = row.timestamp_utc.astimezone(CT)
    stamp = datetime.combine(day, local.timetz()).astimezone(timezone.utc)
    cells = (stamp.strftime("%m/%d/%Y"), stamp.strftime("%H:%M"), *row.source_fields[2:])
    return replace(row, timestamp_utc=stamp, date=cells[0], time=cells[1], source_fields=cells)


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
    # Synthetic prices on real reviewed holiday/regular dates; never infer hours.
    date_by_close = {(16, 0): ("2024-01-16" if month == 1 else "2024-07-02"),
                     (12, 0): ("2024-01-15" if month == 1 else "2024-09-02"),
                     (12, 15): ("2024-11-29" if month == 1 else "2024-07-03")}
    day = datetime.fromisoformat(date_by_close[close]).date()
    rows = [retime(row, day) for row in rows]
    if evening:
        rows.append(retime(bar(127, 17, 1, "125", "150", "100", "130", month=month), day))
        rows.append(retime(bar(128, 23, 59, "130", "150", "100", "135", month=month), day))
    if short:
        rows = [replace(row, open=200-row.open, high=200-row.low, low=200-row.high, close=200-row.close) for row in rows]
    return rows


@pytest.mark.parametrize("close,expected", [((16, 0), "15:55"), ((12, 0), "11:55"), ((12, 15), "12:10")])
@pytest.mark.parametrize("short", [False, True])
@pytest.mark.parametrize("month", [1, 7])
def test_cutoff_submits_exit_for_next_observed_open_and_reconciles_costs(close, expected, short, month):
    strategy, trades, events = replay(session_rows(close=close, short=short, month=month),
        parameters(use_eod_flat=True, trade_longs=not short, trade_shorts=short, max_trades_per_day=5))
    assert len(trades) == 1
    trade = trades[0]
    assert trade.exit_reason == "eod_flat"
    assert trade.exit_deadline_utc.astimezone(CT).strftime("%H:%M") == expected
    assert trade.exit_time_utc.astimezone(CT).strftime("%H:%M") == "%02d:%02d" % close
    assert trade.exit_time_utc > trade.exit_deadline_utc
    assert trade.exit_reference_price == (80 if short else 120)
    assert trade.exit_fill_price == D("80.25" if short else "119.75")
    assert (trade.gross_pnl, trade.total_commissions, trade.net_pnl) == (90, 2, 88)
    assert events[-1].equity == 10088
    assert strategy.trades_today == 1
    assert strategy.session_flattening["sessions"] == 1
    assert strategy.session_flattening["lookahead"] is False
    assert strategy.session_flattening["order_timing"] == "next_open"


def test_last_evening_bars_do_not_shift_daytime_close_and_incomplete_evening_cannot_enter():
    strategy, trades, _ = replay(session_rows(evening=True), parameters(use_eod_flat=True))
    assert len(trades) == 1 and trades[0].exit_time_utc.astimezone(CT).strftime("%H:%M") == "12:00"
    metadata = strategy.session_flattening
    assert metadata["sessions"] == 2 and metadata["closed_sessions"] == 0
    assert metadata["examples"][0]["scheduled_close"].endswith("12:00:00-06:00")


def test_missing_cutoff_never_backdates_an_order_to_the_previous_bar():
    rows = session_rows(missing_cutoff=True)
    day = rows[-1].timestamp_utc.astimezone(CT).date()
    # 11:54 is not retrospectively promoted into the 11:55 decision bar.
    rows[-1:] = [retime(bar(126, 11, 56, "119", "120", "110", "118"), day),
                 retime(bar(127, 11, 57, "120", "140", "100", "125"), day)]
    strategy, trades, _ = replay(rows, parameters(use_eod_flat=True))
    assert trades[0].exit_reason == "eod_flat"
    assert trades[0].exit_time_utc.astimezone(CT).strftime("%H:%M") == "11:57"
    assert trades[0].exit_reference_price == 120
    assert strategy.session_flattening["examples"][0]["order_cutoff"].endswith("11:55:00-06:00")


@pytest.mark.parametrize("kind,net", [("target", D(293)), ("stop", D(-512))])
def test_exits_before_cutoff_are_preserved(kind, net):
    rows = session_rows()
    rows[123] = replace(rows[123], high=D(131), close=D(120)) if kind == "target" else replace(rows[123], low=D(89), close=D(110))
    _, trades, _ = replay(rows, parameters(use_eod_flat=True))
    assert trades[0].exit_reason == ("take_profit" if kind == "target" else "stop_loss")
    assert trades[0].exit_bar_number == 124 and trades[0].net_pnl == net


def test_bracket_touch_on_cutoff_bar_precedes_next_open_flatten():
    rows = session_rows()
    rows[124] = replace(rows[124], high=D(131))
    _, trades, _ = replay(rows, parameters(use_eod_flat=True))
    assert trades[0].exit_reason == "take_profit" and trades[0].net_pnl == 293


def test_next_open_flatten_does_not_hold_exit_bar_extremes_or_keep_old_brackets():
    from alphaquest.intratrade import IntratradeRisk
    p = parameters(use_eod_flat=True)
    rows = session_rows()
    baseline = list(execute(rows, VwapPullbackRiskSizing(p, execution_config=CONFIG), CONFIG, capture_risk=True))
    rows[-1] = replace(rows[-1], high=D(10000), low=D(1))
    extreme = list(execute(rows, VwapPullbackRiskSizing(p, execution_config=CONFIG), CONFIG, capture_risk=True))
    assert next(e for e in extreme if isinstance(e, IntratradeRisk)) == next(
        e for e in baseline if isinstance(e, IntratradeRisk))
    assert next(e for e in extreme if isinstance(e, IntratradeRisk)).exit_phase == "open"
    # An EOD market supersedes the old target, even when the next Open gaps above it.
    rows[-1] = replace(rows[-1], open=D(140), close=D(150))
    _, trades, _ = replay(rows, p)
    assert trades[0].exit_reason == "eod_flat"
    assert trades[0].exit_reference_price == 140
    assert trades[0].net_pnl == 488


def test_gapped_pending_entry_at_cutoff_is_cancelled_and_cannot_reopen():
    rows = session_rows()[:122]
    day = rows[0].timestamp_utc.astimezone(CT).date()
    rows.extend([retime(bar(123, 11, 55, "115", "120", "110", "118"), day),
                 retime(bar(124, 12, 0, "120", "140", "100", "125"), day)])
    _, trades, events = replay(rows, parameters(use_eod_flat=True, max_trades_per_day=5))
    assert trades == [] and all(event.position_contracts == 0 for event in events)


def test_truncated_final_session_keeps_the_calendar_cutoff_and_morning_entries():
    strategy, trades, _ = replay(scenario(), parameters(use_eod_flat=True))
    assert len(trades) == 1 and trades[0].exit_reason == "take_profit"
    example = strategy.session_flattening["examples"][0]
    assert "16:00:00" in example["scheduled_close"]
    assert "15:55:00" in example["order_cutoff"]
    assert "inferred_close" not in example


def test_missing_liquidation_price_rejects_instead_of_filling_in_the_evening():
    rows = session_rows(missing_cutoff=True, evening=True)
    rows[125] = replace(rows[125], open=D(119), high=D(120), low=D(110), close=D(118))
    with pytest.raises(ValueError, match="No observed liquidation price"):
        replay(rows, parameters(use_eod_flat=True))


def test_explicit_eod_off_and_direct_on_bar_are_causal():
    _, trades, _ = replay(session_rows(), parameters(use_eod_flat=False))
    assert trades[0].exit_reason == "take_profit" and trades[0].net_pnl == 293
    strategy = VwapPullbackRiskSizing(parameters(use_eod_flat=True), execution_config=CONFIG)
    assert strategy.on_bar(bar(1, 8, 0), None) is None
    assert strategy.session_flattening["lookahead"] is False


def test_multiple_sessions_remain_flat_until_next_day_and_reset_normally():
    rows = session_rows()
    rows.append(retime(bar(len(rows) + 1, 23, 1), datetime(2024, 1, 15).date()))
    rows.extend(session_rows(close=(16, 0)))
    rows = [replace(row, bar_number=i) for i, row in enumerate(rows, 1)]
    strategy, trades, events = replay(rows, parameters(use_eod_flat=True))
    assert len(trades) == 2
    assert [t.exit_time_utc.astimezone(CT).strftime("%H:%M") for t in trades] == ["12:00", "16:00"]
    assert [t.net_pnl for t in trades] == [88, 88] and events[-1].equity == 10176
    assert strategy.session_flattening["sessions"] == 2


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow("Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol".split(","))
    for row in rows:
        writer.writerow([row.date, row.time, row.open, row.high, row.low, row.close, row.volume, row.up_vol, row.down_vol])
    return stream.getvalue().encode()


def buffer_rows():
    """Synthetic prices: buffer5 exits120, buffer10 exits117 before costs."""
    rows = session_rows()
    day = rows[0].timestamp_utc.astimezone(CT).date()
    rows[124:124] = [retime(bar(125, 11, 50, "116", "120", "110", "116"), day),
                     retime(bar(126, 11, 51, "117", "120", "110", "116"), day)]
    return [replace(row, bar_number=i) for i, row in enumerate(rows, 1)]


def request_body(dataset_id, **overrides):
    return {"dataset_id": dataset_id, "strategy_id": "vwap_pullback_risk_sizing",
        "strategy_parameters": json.loads(json.dumps(asdict(parameters(use_eod_flat=True, **overrides)), default=json_value)),
        "execution_settings": {"initial_capital": "10000", "slippage_ticks": 1, "commission_per_contract_per_side": "1"}}


def test_api_durable_report_exports_and_selected_range_use_the_new_rule(tmp_path):
    database = tmp_path / "datasets.sqlite3"
    raw = csv_bytes(session_rows())
    with TestClient(create_app(database)) as client:
        saved = client.post("/api/datasets", params={"filename": "synthetic-early-close.csv", "name": "SYNTHETIC early close",
            "symbol": "NQ", "source_timezone": "UTC", "tick_size": "0.25", "point_value": "20"}, content=raw)
        assert saved.status_code == 201, saved.text
        dataset_id = saved.json()["id"]
        body = request_body(dataset_id)
        response = client.post("/api/backtests", json={**body, "from_date": "2024-01-15", "to_date": "2024-01-15"})
        assert response.status_code == 201, response.text
        record = response.json()
        run_id = record["id"]
        assert D(record["summary"]["total_net_pnl"]) == 88
        assert record["execution_assumption"].endswith("csv_session_calendar_v1")
        flatten = record["run_metadata"]["strategy"]["session_flattening"]
        assert flatten["enabled"] and not flatten["lookahead"] and flatten["sessions"] == 1
        assert flatten["order_timing"] == "next_open"
        assert "eod_next_open" in record["execution_assumption"]
        assert flatten["examples"][0]["order_cutoff"].endswith("11:55:00-06:00")
        exports = {kind: client.get(f"/api/backtests/{run_id}/exports/{kind}").content for kind in ("trades", "equity", "report")}
        assert b"eod_flat" in exports["trades"] and b"88.00" in exports["equity"]
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


@pytest.mark.parametrize("failure", ["unknown_coverage", "missing_liquidation"])
def test_calendar_source_failures_return_422_without_a_completed_report(tmp_path, failure):
    rows = session_rows(missing_cutoff=True, evening=True)
    if failure == "unknown_coverage":
        rows = [retime(row, datetime(2027, 1, 4).date()) for row in rows]
        message = "does not cover"
    else:
        rows[125] = replace(rows[125], open=D(119), high=D(120), low=D(110), close=D(118))
        message = "No observed liquidation price"
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        saved = client.post("/api/datasets", params={"filename": "synthetic-invalid-session.csv",
            "name": "SYNTHETIC calendar rejection", "symbol": "NQ", "source_timezone": "UTC", "tick_size": "0.25",
            "point_value": "20"}, content=csv_bytes(rows))
        assert saved.status_code == 201, saved.text
        response = client.post("/api/backtests", json=request_body(saved.json()["id"]))
        assert response.status_code == 422, response.text
        assert message in response.json()["detail"]
        assert client.get("/api/backtests").json()["items"] == []


def test_optimization_workers_prepared_features_and_full_detail_match_calendar_exits(tmp_path):
    from test_optimization import start, wait_job
    database = tmp_path / "datasets.sqlite3"
    with TestClient(create_app(database)) as client:
        saved = client.post("/api/datasets", params={"filename": "synthetic-close.csv", "name": "SYNTHETIC optimization close",
            "symbol": "NQ", "source_timezone": "UTC", "tick_size": "0.25", "point_value": "20"}, content=csv_bytes(session_rows()))
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
            assert [D(row["metrics"]["total_net_pnl"]) for row in rows] == [88, 176, 264]
            results.append(rows)
        for first, second in zip(*results):
            for kind in ("trades", "equity"):
                assert client.get(f"/api/backtests/{first['run_id']}/exports/{kind}").content == client.get(f"/api/backtests/{second['run_id']}/exports/{kind}").content
        compact_id = results[0][0]["run_id"]
        response = client.post(f"/api/backtests/{compact_id}/detailed")
        assert response.status_code == 201, response.text
        assert D(response.json()["summary"]["total_net_pnl"]) == 88
