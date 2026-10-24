"""Replay the actual sample strategy against independent reviewed fixtures.

Run: .venv/bin/python tests/review_strategy.py --output artifacts/strategy_review.json
The output option writes full comparisons as JSON and an entry/exit table as
Markdown beside it. No performance metrics or portal controls are implemented.
"""

import argparse
from dataclasses import asdict
from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from alphaquest.backtest_data import read_bars
from alphaquest.datasets import DatasetStore, validate_csv
from alphaquest.execution import EquityPoint, TIMESTAMP_CONVENTION, Trade, execute
from alphaquest.strategies.consecutive_green_hold import DESCRIPTION, STRATEGY_ID, ConsecutiveGreenHold, Parameters
from review_execution import FIXTURES, compare, configuration, fixtures, json_value


def review_fixture(case, directory):
    store = DatasetStore(Path(directory) / f"{case['id']}.sqlite3")
    raw = (FIXTURES / case["csv"]).read_bytes()
    saved = store.save(raw, validate_csv(raw, case["csv"], case["source_timezone"]), case["id"], "SYNTHETIC")
    parameters = Parameters(**case["strategy_parameters"])
    strategy = ConsecutiveGreenHold(parameters)
    with read_bars(store, saved["id"]) as bars:
        # These fixtures are small review artifacts, not a production result sink.
        events = list(execute(bars, strategy, configuration(case)))
    trades = [event for event in events if isinstance(event, Trade)]
    equity = [event for event in events if isinstance(event, EquityPoint)]
    expected_equity = [dict(point, realized_net_pnl=str(
        Decimal(point["cash_balance"]) - Decimal(case["execution_settings"]["initial_capital"])
    )) for point in case["expected_equity"]]
    # Expected decisions are used only after actual strategy execution has ended.
    review = {
        "fixture": case["id"], "strategy_id": STRATEGY_ID, "description": DESCRIPTION,
        "parameters": asdict(parameters), "source_timezone": case["source_timezone"],
        "timestamp_convention": TIMESTAMP_CONVENTION,
        "trades": compare(trades, case["expected_trades"], case["id"] + " trades"),
        "equity": compare(equity, expected_equity, case["id"] + " equity"),
    }
    assert store.get(saved["id"]) == saved, "Replay changed saved metadata"
    assert store.get(saved["id"], download=True) == raw, "Replay changed saved CSV"
    return review


def entry_exit_table(reviews):
    lines = [
        "All timestamps below are UTC on January 5, 2026. Prices are simulated fills.",
        f"All {len(reviews)} fixtures matched every expected trade field and equity point.",
        "",
        "| Fixture / trade | Action | Bar | UTC time | Contracts | Fill | Reason |",
        "| --- | --- | ---: | --- | ---: | ---: | --- |",
    ]
    for review in reviews:
        for row in review["trades"]:
            trade = row["actual"]
            for side, action in (("entry", "Entry"), ("exit", "Exit")):
                stamp = trade[f"{side}_time_utc"].strftime("%H:%M")
                lines.append(
                    f"| {review['fixture']} / {trade['trade_number']} | {action} "
                    f"| {trade[f'{side}_bar_number']} | {stamp} | {trade['contracts']} "
                    f"| {trade[f'{side}_fill_price']} | {trade[f'{side}_reason']} |"
                )
    lines.extend(["", "`no_trades` produced no entries or exits.", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write comparison JSON and a sibling .md entry/exit table")
    args = parser.parse_args()
    if args.output is not None and args.output.suffix.lower() != ".json":
        parser.error("--output must have a .json extension")
    with TemporaryDirectory(prefix="alphaquest-strategy-review-") as directory:
        reviews = [review_fixture(case, directory) for case in fixtures()]
    table = entry_exit_table(reviews)
    print(table)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(reviews, default=json_value, indent=2) + "\n")
        args.output.with_suffix(".md").write_text(table)
        print(f"Comparisons: {args.output}\nEntry/exit table: {args.output.with_suffix('.md')}")


if __name__ == "__main__":
    main()
