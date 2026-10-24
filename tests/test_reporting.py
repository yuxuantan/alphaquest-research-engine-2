import csv
from dataclasses import asdict, replace
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import json
from pathlib import Path
import subprocess
import sys
import tracemalloc

import pytest

from alphaquest.execution import EquityPoint, ExecutionError, Trade, execute
from alphaquest.reporting import ReportError, generate_report, json_value
from alphaquest.strategy import CloseIntent, EntryIntent, ExecutionConfig
from review_execution import ScheduledStrategy, fixtures
from review_reports import review_fixture
from test_execution import bar


D = Decimal
CONFIG = ExecutionConfig(D("10000"), D("0.25"), D("10"), 1, D("1"))


def events(prices=("100", "100.50", "102"), config=CONFIG, *, quantity=2, reason="test entry"):
    strategy = ScheduledStrategy({1: EntryIntent(quantity, reason)}, {len(prices): CloseIntent("test exit")})
    return execute((bar(i, p) for i, p in enumerate(prices, 1)), strategy, config)


def read_report(path):
    return json.loads((path / "report.json").read_text())


@pytest.mark.parametrize("case", fixtures(), ids=lambda case: case["id"])
def test_all_independent_fixture_summaries_trades_equity_and_csv(case, tmp_path):
    review_fixture(case, tmp_path)


def test_exact_sums_and_final_equity_reconcile_and_open_position_marks_are_preserved(tmp_path):
    output = tmp_path / "report"
    stream = list(events())
    manifest = generate_report(iter(stream), output, CONFIG, expected_bar_count=3)
    report = read_report(output)
    summary = report["summary"]
    assert summary["total_net_pnl"] == "26.00"
    assert sum(D(trade["net_pnl"]) for trade in report["trades"]) == D(summary["total_net_pnl"])
    assert D(summary["final_equity"]) == D(summary["initial_capital"]) + D(summary["total_net_pnl"])
    assert [D(point["equity"]) for point in report["equity"]] == [D("10000"), D("9993"), D("10003"), D("10026")]
    assert [D(point["unrealized_pnl"]) for point in report["equity"]] == [D(0), D(-5), D(5), D(0)]
    assert [D(point["realized_net_pnl"]) for point in report["equity"]] == [D(0), D(-2), D(-2), D(26)]
    # All source fields, including fills, commissions and current unrealized P&L,
    # must survive serialization unchanged rather than be recalculated.
    for key, kind in (("trades", Trade), ("equity", EquityPoint)):
        wanted = json.loads(json.dumps([asdict(e) for e in stream if isinstance(e, kind)], default=json_value))
        assert report[key] == wanted
    assert "trades" not in manifest and "equity" not in manifest
    assert manifest["summary"]["total_net_pnl"] == D("26")


def test_win_rate_includes_breakeven_and_classifies_by_net_not_gross(tmp_path):
    # Net results are +20, 0, -10. The zero-net trade remains in the denominator.
    config = replace(CONFIG, slippage_ticks=0, commission_per_contract_per_side=D(0))
    strategy = ScheduledStrategy({i: EntryIntent(1, "entry") for i in (1, 3, 5)},
                                 {i: CloseIntent("exit") for i in (2, 4, 6)})
    prices = ["100", "102", "100", "100", "100", "99"]
    stream = execute((bar(i, p) for i, p in enumerate(prices, 1)), strategy, config)
    summary = generate_report(stream, tmp_path / "report", config)["summary"]
    assert (summary["trades_taken"], summary["winning_trades"], summary["losing_trades"], summary["breakeven_trades"]) == (3, 1, 1, 1)
    assert summary["win_rate_pct"] == D("33.33333333333333333333333333")


def test_equity_csv_contains_only_starting_equity_and_post_trade_equity_after_costs(tmp_path):
    output = tmp_path / "report"
    generate_report(events(), output, CONFIG)
    with (output / "equity.csv").open(newline="") as source:
        rows = list(csv.DictReader(source))
    assert rows == [
        {"trade_number": "0", "exit_time_utc": "", "net_pnl": "0", "equity": "10000"},
        {"trade_number": "1", "exit_time_utc": "2026-01-05T10:02:00Z", "net_pnl": "26.00", "equity": "10026.00"},
    ]
    # Entry/intermediate marks remain in the engine's JSON curve, and never
    # become extra CSV rows between the starting balance and completed trade.
    assert len(read_report(output)["equity"]) == 4


def test_many_digits_in_trade_totals_and_initial_capital_survive_low_context_precision(tmp_path):
    initial = D("100000000000000000000000000000.123456789123456789")
    config = replace(CONFIG, initial_capital=initial)
    prices = ["100000000000000000000000000000.123456789123456789", "100000000000000000000000000002.123456789123456789"]
    with localcontext() as context:
        context.prec = 2
        manifest = generate_report(events(prices, config), tmp_path / "report", config)
        assert context.prec == 2
    report = read_report(tmp_path / "report")
    assert report["summary"]["initial_capital"] == str(initial)
    assert D(report["summary"]["final_equity"]) == D("100000000000000000000000000026.123456789123456789")
    assert manifest["summary"]["total_net_pnl"] == D(26)
    assert report["trades"][0]["entry_fill_price"] == "100000000000000000000000000000.373456789123456789"
    with (tmp_path / "report/trades.csv").open(newline="") as source:
        row = next(csv.DictReader(source))
    assert row["entry_fill_price"] == report["trades"][0]["entry_fill_price"]
    with (tmp_path / "report/equity.csv").open(newline="") as source:
        equity_rows = list(csv.DictReader(source))
    assert equity_rows[0]["equity"] == str(initial)
    assert equity_rows[1]["equity"] == report["summary"]["final_equity"]
    assert equity_rows[1]["net_pnl"] == report["trades"][0]["net_pnl"]


def test_aggregating_more_than_28_significant_digits_does_not_round(tmp_path):
    # Two gross results with very different magnitudes must retain the small one.
    config = replace(CONFIG, slippage_ticks=0, commission_per_contract_per_side=D(0))
    prices = ["0", "100000000000000000000000000000", "0", "0.000000000000000000000000001"]
    strategy = ScheduledStrategy({1: EntryIntent(1, "entry"), 3: EntryIntent(1, "entry")},
                                 {2: CloseIntent("exit"), 4: CloseIntent("exit")})
    with localcontext() as context:
        context.prec = 2
        summary = generate_report(execute((bar(i, p) for i, p in enumerate(prices, 1)), strategy, config), tmp_path / "report", config)["summary"]
    assert summary["total_gross_pnl"] == summary["total_net_pnl"] == D("1000000000000000000000000000000.000000000000000000000000010")


def test_csv_quotes_reason_text_and_preserves_optional_deadline_and_initial_timestamp(tmp_path):
    reason = 'entry, observed close\n"quoted"'
    output = tmp_path / "report"
    generate_report(events(reason=reason), output, CONFIG)
    with (output / "trades.csv").open(newline="") as source:
        rows = list(csv.DictReader(source))
    assert rows[0]["entry_reason"] == reason
    assert rows[0]["exit_deadline_utc"] == ""
    assert read_report(output)["trades"][0]["exit_deadline_utc"] is None
    with (output / "equity.csv").open(newline="") as source:
        assert next(csv.DictReader(source))["exit_time_utc"] == ""


def test_empty_input_and_initial_only_are_not_complete_reports(tmp_path):
    for i, stream in enumerate(([], [EquityPoint(0, None, D(10000), D(0), D(0), D(10000), 0)])):
        output = tmp_path / str(i)
        with pytest.raises(ReportError, match="at least one"):
            generate_report(stream, output, CONFIG)
        assert not output.exists()


@pytest.mark.parametrize("corruption", ["missing_trade", "missing_final_point", "wrong_equity", "open_final", "non_decimal", "bad_trade_number", "wrong_bar", "bad_net", "wrong_commissions", "unknown_event", "initial_capital", "missing_initial"])
def test_inconsistent_outputs_are_rejected_without_publishing(corruption, tmp_path):
    stream = list(events())
    if corruption == "missing_trade":
        stream = [event for event in stream if not isinstance(event, Trade)]
    elif corruption == "missing_final_point":
        stream.pop()
    elif corruption == "wrong_equity":
        stream[-1] = replace(stream[-1], equity=D(0))
    elif corruption == "open_final":
        stream[-1] = replace(stream[-1], position_contracts=2)
    elif corruption == "non_decimal":
        stream[-1] = replace(stream[-1], equity=10026.0)
    elif corruption == "bad_trade_number":
        stream[-2] = replace(stream[-2], trade_number=2)
    elif corruption == "wrong_bar":
        stream[-1] = replace(stream[-1], bar_number=5)
    elif corruption == "bad_net":
        stream[-2] = replace(stream[-2], net_pnl=D(30))
    elif corruption == "wrong_commissions":
        stream[-2] = replace(stream[-2], entry_commission=D(0))
    elif corruption == "unknown_event":
        stream.append({"equity": "10026"})
    elif corruption == "initial_capital":
        stream[0] = replace(stream[0], equity=D(99), cash_balance=D(99), realized_net_pnl=D(-9901))
    elif corruption == "missing_initial":
        stream.pop(0)
    output = tmp_path / "report"
    with pytest.raises(ReportError):
        generate_report(stream, output, CONFIG)
    assert not output.exists()
    assert list(tmp_path.iterdir()) == []


def test_saved_bar_count_detects_flat_but_truncated_stream(tmp_path):
    with pytest.raises(ReportError, match="bar count"):
        generate_report(events(), tmp_path / "report", CONFIG, expected_bar_count=4)
    assert not (tmp_path / "report").exists()


def test_engine_error_never_publishes_partial_artifacts(tmp_path):
    strategy = ScheduledStrategy({1: EntryIntent(1, "left open")})
    stream = execute([bar(1), bar(2)], strategy, CONFIG)
    with pytest.raises(ExecutionError, match="open position"):
        generate_report(stream, tmp_path / "report", CONFIG)
    assert list(tmp_path.iterdir()) == []


def test_existing_output_is_preserved_and_source_is_not_consumed(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    (output / "report.json").write_text("original")

    def source():
        pytest.fail("Existing output should be rejected before consuming the source")
        yield

    with pytest.raises(FileExistsError):
        generate_report(source(), output, CONFIG)
    assert (output / "report.json").read_text() == "original"


def test_reporter_streams_many_trades_and_equity_points_to_disk(tmp_path):
    class Alternating(ScheduledStrategy):
        def on_bar(self, current, position):
            return CloseIntent("exit") if position else EntryIntent(1, "entry")

    stream = execute((bar(i) for i in range(1, 10_001)), Alternating(), CONFIG)
    tracemalloc.start()
    try:
        manifest = generate_report(stream, tmp_path / "report", CONFIG, expected_bar_count=10_000)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert manifest["summary"]["trades_taken"] == 5_000
    assert peak < 6 * 1024 * 1024
    with (tmp_path / "report/equity.csv").open() as source:
        assert sum(1 for _ in source) == 5_002  # header, initial equity, 5,000 completed trades


def test_cli_runs_by_saved_id_with_provenance_and_clear_invalid_decimal_error(tmp_path):
    case = fixtures()[0]
    fixture_report = review_fixture(case, tmp_path)
    dataset_id = fixture_report["run_metadata"]["dataset"]["id"]
    output = tmp_path / "cli-report"
    command = [sys.executable, "-m", "alphaquest.run_backtest", "--database", str(tmp_path / case["id"] / "datasets.sqlite3"),
               "--dataset-id", dataset_id, "--output", str(output), "--initial-capital", "10000", "--slippage-ticks", "1", "--commission-per-contract-per-side", "1", "--contracts", "2"]
    completed = subprocess.run(command, text=True, capture_output=True, check=True)
    assert json.loads(completed.stdout)["summary"]["total_net_pnl"] == "26.00"
    report = read_report(output)
    strategy = report["run_metadata"]["strategy"]
    assert strategy["id"] == "consecutive_green_hold" and len(strategy["source_sha256"]) == 64
    assert report["run_metadata"]["dataset"]["id"] == dataset_id
    assert report["timestamp_convention"] == "bar_close" and report["status"] == "complete"
    invalid = command.copy()
    invalid[invalid.index("--initial-capital") + 1] = "invalid"
    failed = subprocess.run(invalid, text=True, capture_output=True)
    assert failed.returncode == 2 and "decimal number" in failed.stderr and "Traceback" not in failed.stderr
