"""Runnable execution review with predetermined TEST-ONLY intents, not signals.

Run from the repository: .venv/bin/python tests/review_execution.py
Only intent ordinals, quantities, reasons, and deadline metadata come from the
reviewed schedule. Expected prices, costs, P&L and equity never drive execution.
This does not qualify a production strategy's signal or holding-period logic.
"""

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from alphaquest.backtest_data import read_bars
from alphaquest.datasets import DatasetStore, validate_csv
from alphaquest.execution import EquityPoint, Trade, execute
from alphaquest.strategy import CloseIntent, EntryIntent, ExecutionConfig


FIXTURES = Path(__file__).parent / "fixtures/backtest_contract"


def fixtures():
    return json.loads((FIXTURES / "expected.json").read_text())["fixtures"]


def configuration(case):
    return ExecutionConfig(**{
        name: value if name == "slippage_ticks" else Decimal(value)
        for name, value in case["execution_settings"].items()
    })


class ScheduledStrategy:
    """Test double: act at specified ordinals, without inspecting market signals."""

    def __init__(self, entries=None, closes=None, finish=None):
        self.entries = entries or {}
        self.closes = closes or {}
        self.finish = finish

    def on_bar(self, bar, position):
        return self.entries.get(bar.bar_number) or self.closes.get(bar.bar_number)

    def on_finish(self, last_bar, position):
        return self.finish

    @classmethod
    def from_fixture(cls, case):
        entries, closes, finish = {}, {}, None
        for trade in case["expected_trades"]:
            entries[trade["entry_bar_number"]] = EntryIntent(
                trade["contracts"], trade["entry_reason"], datetime.fromisoformat(trade["exit_deadline_utc"]),
            )
            close = CloseIntent(trade["exit_reason"])
            if trade["exit_reason"] == "end_of_data":
                finish = close
            else:
                closes[trade["exit_bar_number"]] = close
        return cls(entries, closes, finish)


def _typed_expected(expected, actual):
    result = {}
    for key, value in expected.items():
        sample = actual[key]
        if isinstance(sample, Decimal):
            value = Decimal(value)
        elif isinstance(sample, datetime):
            value = datetime.fromisoformat(value)
        result[key] = value
    return result


def compare(actual, expected, label):
    assert len(actual) == len(expected), f"{label}: event count differs"
    rows = []
    for observed, wanted in zip(actual, expected, strict=True):
        record = asdict(observed)
        typed = _typed_expected(wanted, record)
        assert record == typed, f"{label}: actual {record!r} != expected {typed!r}"
        rows.append({"actual": record, "expected": typed, "match": True})
    return rows


def review_fixture(case, directory):
    store = DatasetStore(Path(directory) / f"{case['id']}.sqlite3")
    raw = (FIXTURES / case["csv"]).read_bytes()
    saved = store.save(raw, validate_csv(raw, case["csv"], case["source_timezone"]), case["id"], "SYNTHETIC")
    strategy = ScheduledStrategy.from_fixture(case)
    with read_bars(store, saved["id"]) as bars:
        # These fixtures are deliberately tiny. Production consumers should write
        # or process each event as it arrives rather than collecting this list.
        events = list(execute(bars, strategy, configuration(case)))
    trades = [event for event in events if isinstance(event, Trade)]
    equity = [event for event in events if isinstance(event, EquityPoint)]
    expected_equity = [dict(point, realized_net_pnl=str(
        Decimal(point["cash_balance"]) - Decimal(case["execution_settings"]["initial_capital"])
    )) for point in case["expected_equity"]]
    return {
        "fixture": case["id"], "timestamp_convention": "bar_close",
        "intent_source": "Predetermined test-only schedule from reviewed fixture; no production strategy.",
        "trades": compare(trades, case["expected_trades"], case["id"] + " trades"),
        "equity": compare(equity, expected_equity, case["id"] + " equity"),
    }


def json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    raise TypeError(type(value).__name__)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write complete actual-versus-expected trade/equity JSON")
    args = parser.parse_args()
    with TemporaryDirectory(prefix="alphaquest-execution-review-") as directory:
        reviews = [review_fixture(case, directory) for case in fixtures()]
    print("fixture                    trades  actual net / expected net   actual final / expected final")
    for review in reviews:
        actual_net = sum((row["actual"]["net_pnl"] for row in review["trades"]), Decimal(0))
        expected_net = sum((row["expected"]["net_pnl"] for row in review["trades"]), Decimal(0))
        final = review["equity"][-1]
        print(f"{review['fixture']:26} {len(review['trades']):>2}     {actual_net:>7} / {expected_net:<7}"
              f"       {final['actual']['equity']} / {final['expected']['equity']}  PASS")
    arithmetic = reviews[0]
    print("\nArithmetic trade: actual / expected")
    for name, value in arithmetic["trades"][0]["actual"].items():
        print(f"  {name}: {value} / {arithmetic['trades'][0]['expected'][name]}")
    print("\nArithmetic equity: bar  cash actual/expected  unrealized actual/expected  equity actual/expected")
    for row in arithmetic["equity"]:
        a, e = row["actual"], row["expected"]
        print(f"  {a['bar_number']}:  {a['cash_balance']}/{e['cash_balance']}  "
              f"{a['unrealized_pnl']}/{e['unrealized_pnl']}  {a['equity']}/{e['equity']}")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(reviews, default=json_value, indent=2) + "\n")
        print(f"\nFull comparison: {args.output}")


if __name__ == "__main__":
    main()
