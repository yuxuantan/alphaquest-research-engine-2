"""Generate actual sample-strategy reports and check all independent fixtures."""

import argparse
import csv
from decimal import Decimal
import json
from pathlib import Path

from alphaquest.datasets import DatasetStore, validate_csv
from alphaquest.run_backtest import run_saved_dataset
from alphaquest.backtest_config import RunSettings
from alphaquest.strategies.consecutive_green_hold import Parameters
from review_execution import FIXTURES, fixtures


def _equal_record(actual, expected):
    assert actual.keys() == expected.keys(), (actual.keys(), expected.keys())
    for key, wanted in expected.items():
        observed = actual[key]
        # Expected numeric strings are finite decimals; timestamps/reasons stay text.
        if isinstance(wanted, str):
            try:
                numeric = Decimal(wanted)
            except ArithmeticError:
                assert observed == wanted, (key, observed, wanted)
            else:
                assert isinstance(observed, str), (key, "Monetary values must be strings")
                assert Decimal(observed) == numeric, (key, observed, wanted)
        else:
            assert observed == wanted, (key, observed, wanted)


def review_fixture(case, directory):
    fixture_dir = Path(directory) / case["id"]
    store = DatasetStore(fixture_dir / "datasets.sqlite3")
    from research_fixtures import reserved_source
    raw,split = reserved_source((FIXTURES / case["csv"]).read_bytes())
    saved = store.save(raw, validate_csv(raw, case["csv"], case["source_timezone"]), case["id"], "SYNTHETIC")
    saved = store.set_instrument_settings(saved["id"], **{k: case["execution_settings"][k] for k in ("tick_size", "point_value")})
    settings = case["execution_settings"]
    output = fixture_dir / "report"
    run_saved_dataset(store, saved["id"], output, Parameters(**case["strategy_parameters"]), RunSettings(Decimal(settings["initial_capital"]), settings["slippage_ticks"], Decimal(settings["commission_per_contract_per_side"])),report_detail='full',sample_split=split)
    report = json.loads((output / "report.json").read_text())
    _equal_record(report["summary"], case["expected_summary"])
    assert len(report["trades"]) == len(case["expected_trades"])
    for actual, expected in zip(report["trades"], case["expected_trades"], strict=True):
        _equal_record(actual, expected)
    expected_equity = [dict(point, realized_net_pnl=str(
        Decimal(point["cash_balance"]) - Decimal(case["execution_settings"]["initial_capital"])
    )) for point in case["expected_equity"]]
    assert len(report["equity"]) == len(expected_equity)
    for actual, expected in zip(report["equity"], expected_equity, strict=True):
        _equal_record(actual, expected)
    with (output / "trades.csv").open(newline="") as source:
        csv_rows = list(csv.DictReader(source))
    expected_rows = [{key: "" if value is None else str(value) for key, value in row.items()} for row in report["trades"]]
    assert csv_rows == expected_rows, f"{case['id']} trades CSV differs from JSON"
    expected_trade_equity = [{
        "trade_number": "0", "exit_time_utc": "", "net_pnl": "0",
        "equity": case["execution_settings"]["initial_capital"],
    }] + [{
        "trade_number": str(trade["trade_number"]), "exit_time_utc": trade["exit_time_utc"],
        "net_pnl": trade["net_pnl"],
        "equity": case["expected_equity"][trade["exit_bar_number"]]["equity"],
    } for trade in case["expected_trades"]]
    with (output / "equity.csv").open(newline="") as source:
        reader = csv.DictReader(source)
        csv_rows = list(reader)
        assert reader.fieldnames == ["trade_number", "exit_time_utc", "net_pnl", "equity"]
    assert len(csv_rows) == len(expected_trade_equity)
    for actual, expected in zip(csv_rows, expected_trade_equity, strict=True):
        _equal_record(actual, expected)
    checks = report["reconciliation"]
    assert all(value is True for key, value in checks.items() if key not in ("observed_bar_count", "expected_bar_count"))
    assert checks["observed_bar_count"] == checks["expected_bar_count"] == case["bar_count"]
    assert store.get(saved["id"]) == saved
    assert store.get(saved["id"], download=True) == raw
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New directory for saved fixtures and generated reports")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    print("fixture                    trades    gross     fees      net   final equity   expected")
    for case in fixtures():
        report = review_fixture(case, args.output)
        s = report["summary"]
        print(f"{case['id']:26} {s['trades_taken']:>2}   {s['total_gross_pnl']:>7}  {s['total_commissions']:>7}"
              f"  {s['total_net_pnl']:>7}  {s['final_equity']:>12}   PASS")
    print(f"All summary fields, full trades, equity points, CSV exports and reconciliation checks matched.\nReports: {args.output}")


if __name__ == "__main__":
    main()
