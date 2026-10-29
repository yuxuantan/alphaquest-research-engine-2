"""Synthetic, hand-priced port checks; these do not establish MC export parity."""

from dataclasses import asdict, fields, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
import csv
import io
import json
from pathlib import Path
import re
import subprocess
import sys
from zoneinfo import ZoneInfo

from research_fixtures import ResearchClient as TestClient
import pytest

from alphaquest.app import create_app
from alphaquest.datasets import DatasetStore, validate_csv
from alphaquest.execution import EquityPoint, Trade, execute
from alphaquest.reporting import generate_report, json_value
from alphaquest.strategies.registry import get_strategy
from alphaquest.strategies.vwap_pullback_risk_sizing import Parameters, VwapPullbackRiskSizing, _ADX
from alphaquest.strategy import Bar, BracketIntent, CloseIntent, EntryIntent, ExecutionConfig


D = Decimal
CT = ZoneInfo("America/Chicago")
CONFIG = ExecutionConfig(D("10000"), D("0.25"), D("20"), 1, D("1"))


def bar(number, hour, minute, o="100", h="105", l="95", c="100", volume="1", *, month=1):
    stamp = datetime(2026, month, 5, hour, minute, tzinfo=CT).astimezone(timezone.utc)
    cells = (stamp.strftime("%m/%d/%Y"), stamp.strftime("%H:%M"), o, h, l, c, volume, "0", "0")
    return Bar(number, stamp, cells[0], cells[1], *map(D, cells[2:]), cells)


def parameters(**overrides):
    # Source-mechanics fixtures intentionally end at09:03. Keep their EOF and
    # pivot assertions separate from the new last-bar inference tests.
    base = replace(Parameters(), stop_swing_len=1, target_swing_len=1, use_adx_elev=False,
                   use_adx_decay=False, plot_trade_levels=False, use_eod_flat=False)
    return replace(base, **overrides)


def scenario(*, short=False, month=1, ending="target"):
    """Target pivot 130/70 at 08:00; stop pivot 90/110 at 08:10.

    OR 08:31..09:00 is [95,105]. The 09:01 break/reclaim is 108/92.
    Entry gaps to 115/85 on 09:02. Both levels trade on entry bar,
    before brackets exist. 09:03 exits at the frozen target or stop.
    """
    result = []
    start = datetime(2026, month, 5, 7, 0)
    for index in range(124):
        current = start + timedelta(minutes=index)
        hour, minute = current.hour, current.minute
        prices = ("100", "105", "95", "100")
        if (hour, minute) == (8, 0):
            prices = ("100", "130", "95", "100")
        if (hour, minute) == (8, 10):
            prices = ("100", "105", "90", "100")
        if (hour, minute) == (9, 1):
            prices = ("100", "109", "99", "108")
        if (hour, minute) == (9, 2):
            prices = ("115", "140", "80", "116")
        if (hour, minute) == (9, 3):
            prices = (("116", "131", "110", "120") if ending == "target"
                      else ("116", "131", "89", "120"))
        if short:
            o, h, l, c = map(D, prices)
            prices = tuple(str(value) for value in (200-o, 200-l, 200-h, 200-c))
        result.append(bar(index + 1, hour, minute, *prices, month=month))
    return result


def replay(bars, p=None, config=CONFIG):
    strategy = VwapPullbackRiskSizing(p or parameters(), execution_config=config)
    events = list(execute(bars, strategy, config))
    return strategy, [e for e in events if type(e) is Trade], events


@pytest.mark.parametrize("short", [False, True])
@pytest.mark.parametrize("month,utc_hour", [(1, 15), (7, 14)])
def test_orb_vwap_pivots_next_open_bracket_and_dst(short, month, utc_hour, tmp_path):
    p = parameters(trade_longs=not short, trade_shorts=short)
    strategy, trades, events = replay(scenario(short=short, month=month), p)
    assert len(trades) == 1
    trade = trades[0]
    assert trade.side == ("short" if short else "long")
    assert (trade.entry_bar_number, trade.exit_bar_number) == (123, 124)
    assert trade.entry_time_utc.hour == utc_hour
    assert (trade.entry_time_utc.minute, trade.exit_time_utc.minute) == (2, 3)
    assert trade.entry_reference_price == D("85" if short else "115")
    assert trade.entry_fill_price == D("84.75" if short else "115.25")
    assert trade.exit_fill_price == trade.exit_reference_price == D("70" if short else "130")
    assert trade.exit_reason == "take_profit"
    assert trade.gross_pnl == D("295")
    assert trade.total_commissions == 2
    assert trade.net_pnl == 293
    assert strategy.trades_today == 1
    assert (strategy.active_stop, strategy.active_target) == ((D(110), D(70)) if short else (D(90), D(130)))
    manifest = generate_report(events, tmp_path / "report", CONFIG,
                               execution_assumption=get_strategy("vwap_pullback_risk_sizing").execution_assumption)
    assert manifest["summary"]["final_equity"] == 10293
    assert manifest["execution_assumption"] == get_strategy("vwap_pullback_risk_sizing").execution_assumption


def test_ambiguous_bar_stop_first_and_actual_costs():
    _, trades, _ = replay(scenario(ending="both"))
    trade = trades[0]
    assert (trade.exit_reason, trade.exit_reference_price, trade.exit_fill_price) == ("stop_loss", D(90), D("89.75"))
    assert (trade.gross_pnl, trade.net_pnl) == (D(-510), D(-512))


def test_final_signal_does_not_fill_without_next_bar_and_final_entry_liquidates():
    _, trades, _ = replay(scenario()[:122])
    assert trades == []
    _, trades, _ = replay(scenario()[:123])
    assert len(trades) == 1
    assert trades[0].entry_bar_number == trades[0].exit_bar_number == 123
    assert trades[0].exit_reason == "end_of_data"
    assert (trades[0].entry_fill_price, trades[0].exit_fill_price) == (D("115.25"), D("115.75"))


def test_pullback_stop_buffer_rr_and_risk_sizing_use_signal_close_and_instrument():
    p = parameters(stop_mode=2, buffer_mode=1, buffer_amount=D(2), use_vol_sizing=True,
                   mm_capital_usd=D(10000), mm_risk_pct=D(2), max_contracts=10)
    # Signal: Close108, low99; stop98.5; padded risk=(9.5+.5)*20=200.
    strategy, trades, _ = replay(scenario(), p)
    assert strategy.active_stop == D("98.5")
    assert trades[0].contracts == 1
    _, trades, _ = replay(scenario(), replace(p, mm_capital_usd=D(9999)))
    assert trades == []  # Budget cannot fund one NQ contract.
    _, trades, _ = replay(scenario(), p, replace(CONFIG, point_value=D(2)))
    assert trades[0].contracts == 10  # Identical signal with MNQ point value.
    for selection in (replace(p, max_stop_points=D(9)), replace(p, min_rr=D(3))):
        _, trades, _ = replay(scenario(), selection)
        assert trades == []
    _, trades, _ = replay(scenario(), parameters(position_size=4, max_contracts=1))
    assert trades[0].contracts == 4  # Source cap applies only to risk sizing.


def test_touch_can_signal_on_break_bar_but_close_through_needs_prior_close():
    _, trades, _ = replay(scenario(), parameters(retest_mode=2))
    assert trades == []
    bars = scenario()
    # Break at09:01 without touch; close below VWAP09:02, reclaim09:03.
    bars[121] = bar(122, 9, 1, "108", "109", "107", "108")
    bars[122] = bar(123, 9, 2, "99", "110", "96", "98")
    bars[123] = bar(124, 9, 3, "104", "112", "103", "108")
    bars.append(bar(125, 9, 4, "110", "111", "109", "110"))
    _, trades, _ = replay(bars, parameters(retest_mode=2))
    assert len(trades) == 1 and trades[0].entry_bar_number == 125


def test_adx_gate_delays_reclaim_without_erasing_latches(monkeypatch):
    # Isolate gate sequencing; independent arithmetic is checked below.
    strategy = VwapPullbackRiskSizing(replace(parameters(), use_adx_elev=True, use_adx_decay=True), execution_config=CONFIG)
    values = iter([D(10)] * 79 + [D(30), D(25), D(24)])
    monkeypatch.setattr(strategy._adx, "update", lambda history: next(values))
    bars = scenario()
    bars[122] = bar(123, 9, 2, "108", "110", "107", "109")
    bars[123] = bar(124, 9, 3, "111", "112", "110", "111")
    trades = [e for e in execute(bars, strategy, CONFIG) if type(e) is Trade]
    #09:01 ADX30 fails decay against10; 09:02 ADX25 passes against30.
    assert len(trades) == 1 and trades[0].entry_bar_number == 124


def test_adx_initialization_cumulative_mean_wilder_and_tied_dm():
    adx = _ADX(2)
    rows = [bar(1, 8, 0, "10", "11", "9", "10"),
            bar(2, 8, 1, "11", "13", "10", "12"),
            bar(3, 8, 2, "10", "12", "8", "9")]
    assert adx.update(rows) == 0  # +DM2 and -DM2 seed equal means.
    rows.append(bar(4, 8, 3, "11", "14", "9", "12"))
    assert adx.update(rows) == 25  # smoothed +1.5,-.5; DX50; mean(0,50).
    rows.append(bar(5, 8, 4, "12", "14", "9", "12"))
    assert adx.update(rows) == D("37.5")  # DX50; Wilder(25,50).
    assert _ADX.movement(bar(2, 8, 1, "10", "12", "8", "10"),
                         bar(1, 8, 0, "10", "11", "9", "10"))[:2] == (0, 0)


def test_strict_pivots_no_future_confirmation_and_equal_high_rejection():
    strategy = VwapPullbackRiskSizing(parameters(), execution_config=CONFIG)
    rows = scenario()
    for row in rows[:61]:  #08:00 candidate has not yet seen its right bar.
        strategy.on_bar(row, None)
    assert strategy.last_target_high is None
    strategy.on_bar(rows[61], None)
    assert strategy.last_target_high == 130
    rows[61] = replace(rows[61], high=D(130))
    strategy, trades, _ = replay(rows)
    assert trades == []  # Equal highs invalidate both adjacent candidates.


def test_exact_session_edges_weighted_vwap_zero_volume_and_no_midnight_reset():
    strategy = VwapPullbackRiskSizing(parameters(), execution_config=CONFIG)
    for row in scenario()[:91]:  #Through08:30, outside OR/VWAP.
        strategy.on_bar(row, None)
    assert strategy._cum_vol == 0 and not strategy.orb_ready
    strategy.on_bar(bar(92, 8, 31, "100", "103", "97", "103", "0"), None)
    assert strategy.ny_vwap == 101 and strategy._cum_vol == 1
    strategy.on_bar(bar(93, 8, 32, "100", "103", "97", "100", "3"), None)
    assert strategy.ny_vwap == D("100.25")
    strategy.trades_today = 1
    strategy.on_bar(bar(94, 23, 0), None)
    assert strategy.trades_today == 1
    strategy.on_bar(bar(95, 23, 1), None)
    assert strategy.trades_today == 0 and not strategy.orb_ready
    strategy.trades_today = 1
    midnight = replace(bar(96, 0, 0), timestamp_utc=bar(96, 0, 0).timestamp_utc + timedelta(days=1))
    strategy.on_bar(midnight, None)
    assert strategy.trades_today == 1  # Preserve source crossing rule, not date rollover.


def test_eod_flat_fills_cutoff_close_without_waiting_for_next_bar():
    rows = scenario()[:123]
    rows.append(bar(124, 15, 55, "116", "120", "100", "118"))
    rows.append(bar(125, 15, 56, "117", "150", "50", "120"))
    rows.append(bar(126, 16, 0, "120", "120", "120", "120"))
    _, trades, _ = replay(rows, parameters(use_eod_flat=True))
    assert trades[0].exit_reason == "eod_flat"
    assert trades[0].exit_reference_price == 118
    assert trades[0].exit_fill_price == D("117.75")


@pytest.mark.parametrize("name,value", [("position_size", True), ("use_adx_elev", 1),
    ("retest_mode", 3), ("stop_mode", 0), ("or_start_time", 860), ("mm_risk_pct", 2.0),
    ("min_rr", D("NaN")), ("buffer_amount", D(-1)), ("max_bars_back", 10)])
def test_parameter_validation(name, value):
    with pytest.raises(ValueError):
        replace(Parameters(), **{name: value})


def test_prefix_is_causal_and_indicator_context_is_independent():
    def intents(rows):
        strategy = VwapPullbackRiskSizing(parameters(), execution_config=CONFIG)
        return [strategy.on_bar(row, None) for row in rows]
    rows = scenario()
    assert intents(rows[:122]) == intents(rows)[:122]
    expected = replay(rows)[1]
    with localcontext() as context:
        context.prec = 6
        assert replay(rows)[1] == expected


def test_registry_api_saved_report_and_invalid_decimal(tmp_path):
    definition = get_strategy("vwap_pullback_risk_sizing")
    values = json.loads(json.dumps(asdict(parameters()), default=json_value))
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        listing = next(s for s in client.get("/api/strategies").json() if s["id"] == definition.module.STRATEGY_ID)
        assert {p["name"]: p["default"] for p in listing["parameters"]} == json.loads(json.dumps(asdict(Parameters()), default=json_value))
        source = io.StringIO()
        writer = csv.writer(source)
        writer.writerow("Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol".split(","))
        writer.writerows(row.source_fields for row in scenario(short=True))
        response = client.post("/api/datasets", params={"filename": "port.csv", "name": "synthetic", "source_timezone": "UTC", "tick_size": "0.25", "point_value": "20"}, content=source.getvalue().encode())
        assert response.status_code == 201, response.text
        values.update(trade_longs=False, trade_shorts=True)
        body = {"dataset_id": response.json()["id"], "strategy_id": definition.module.STRATEGY_ID,
                "strategy_parameters": values, "execution_settings": json.loads(json.dumps({k: v for k, v in asdict(CONFIG).items() if k not in ("tick_size", "point_value")}, default=json_value))}
        response = client.post("/api/backtests", json=body)
        assert response.status_code == 201, response.text
        record = response.json()
        assert record["summary"]["total_net_pnl"] == "293.00"
        assert record["run_metadata"]["strategy"]["parameters"] == values
        assert record["execution_assumption"] == definition.execution_assumption
        trade = client.get(f"/api/backtests/{record['id']}/trades").json()["items"][0]
        assert trade["side"] == "short" and D(trade["net_pnl"]) == 293
        for value in ("nonsense", "NaN", 2.0):
            body["strategy_parameters"]["mm_risk_pct"] = value
            response = client.post("/api/backtests", json=body)
            assert response.status_code == 422, response.text


def test_every_default_matches_retained_powerlanguage_inputs():
    source = (Path(__file__).parents[1] / "docs/strategies/vwap_pullback_risk_sizing.pl").read_text()
    source = source.split("Inputs:", 1)[1].split("Vars:", 1)[0]
    inputs = re.findall(r"^\s*(\w+)\(([^)]+)\)", source, re.MULTILINE)
    definitions = fields(Parameters)
    assert len(inputs) == len(definitions) - 1 == 31
    for (source_name, literal), item in zip(inputs, definitions):
        if item.type is bool:
            expected = literal == "true"
        elif item.type is int:
            expected = int(literal)
        else:
            expected = D(literal)
        assert item.default == expected, (source_name, item.name)
    assert definitions[-1].name == "max_bars_back" and definitions[-1].default == 42


def test_cli_writes_real_report_with_selected_strategy_parameters(tmp_path):
    source = io.StringIO()
    writer = csv.writer(source)
    writer.writerow("Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol".split(","))
    writer.writerows(row.source_fields for row in scenario())
    from research_fixtures import reserved_source,cli_split
    raw,split = reserved_source(source.getvalue().encode())
    database = tmp_path / "datasets.sqlite3"
    store = DatasetStore(database)
    saved = store.save(raw, validate_csv(raw, "synthetic.csv", "UTC"), "synthetic", "NQ")
    store.set_instrument_settings(saved["id"], "0.25", "20")
    output = tmp_path / "report"
    result = subprocess.run([
        sys.executable, "-m", "alphaquest.run_backtest", "--database", str(database),
        "--dataset-id", saved["id"], "--output", str(output),
        '--report-detail','full',
        *cli_split(split),
        "--strategy-id", "vwap_pullback_risk_sizing",
        "--strategy-parameters", json.dumps(asdict(parameters()), default=json_value),
        "--initial-capital", "10000",
        "--slippage-ticks", "1", "--commission-per-contract-per-side", "1",
    ], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    report = json.loads((output / "report.json").read_text())
    assert report["run_metadata"]["strategy"]["id"] == "vwap_pullback_risk_sizing"
    assert D(report["summary"]["total_net_pnl"]) == 293
    assert report["trades"][0]["exit_reason"] == "take_profit"
    assert {p.name for p in output.iterdir()} == {"report.json", "trades.csv", "equity.csv", "intratrade_risk.csv", 'performance.json', 'market_benchmark.json', 'market_equity.csv'}
