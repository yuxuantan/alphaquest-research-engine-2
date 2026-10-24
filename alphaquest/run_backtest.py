"""Run a strategy using dataset instrument defaults and optional overrides."""

import argparse
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path

from .backtest_data import DatasetReadError, DateRange, read_selected_bars
from .backtest_config import RunSettings, instrument_overrides
from .datasets import DatasetStore, InvalidDataset
from .execution import execute
from .reporting import generate_report, json_value
from .strategies import consecutive_green_hold as sample
from .strategies.registry import get_strategy, STRATEGIES


def _decimal_argument(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation:
        raise argparse.ArgumentTypeError("Use a decimal number, such as 0.25.") from None


def run_saved_dataset(store: DatasetStore, dataset_id: str, output_directory: Path,
                      parameters, settings: RunSettings, *, strategy_id=sample.STRATEGY_ID,
                      from_date=None, to_date=None) -> dict:
    """The runner wires components together; the reporter remains strategy agnostic."""
    dataset = store.get(dataset_id)
    if dataset is None:
        raise DatasetReadError(f"Dataset {dataset_id!r} was not found.")
    config = settings.execution_config(dataset)
    definition = get_strategy(strategy_id)
    metadata = {
        "dataset": {name: dataset[name] for name in ("id", "name", "sha256", "source_timezone", "row_count", "instrument_settings")},
        "strategy": definition.provenance(parameters),
        "instrument_overrides": instrument_overrides(dataset, config),
    }
    date_range = DateRange.parse(from_date, to_date)
    with read_selected_bars(store, dataset_id, date_range) as selected:
        metadata["selection"] = selected.metadata
        return generate_report(execute(selected.bars, definition.create(parameters, config), config),
                               output_directory, config, metadata=metadata, expected_bar_count=selected.row_count,
                               execution_assumption=definition.execution_assumption)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path(os.environ.get("ALPHAQUEST_DATA_DIR", "data")) / "datasets.sqlite3")
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--output", type=Path, required=True, help="New directory for report.json, trades.csv, equity.csv")
    parser.add_argument("--from-date", help="Inclusive YYYY-MM-DD in the saved source timezone")
    parser.add_argument("--to-date", help="Inclusive YYYY-MM-DD in the saved source timezone")
    parser.add_argument("--green-bar-count", type=int, default=3)
    parser.add_argument("--hold-minutes", type=int, default=20)
    parser.add_argument("--contracts", type=int, default=1)
    parser.add_argument("--strategy-id", choices=STRATEGIES, default=sample.STRATEGY_ID)
    parser.add_argument("--strategy-parameters", help="JSON object with all strategy parameters; decimals as strings")
    for name in ("initial-capital", "commission-per-contract-per-side"):
        parser.add_argument(f"--{name}", required=True, type=_decimal_argument)
    parser.add_argument("--slippage-ticks", type=int, required=True)
    parser.add_argument("--tick-size", help="Override the saved dataset tick size for this run only")
    parser.add_argument("--point-value", help="Override the saved monetary point value for this run only")
    args = parser.parse_args()
    try:
        if args.strategy_parameters is not None:
            values = json.loads(args.strategy_parameters)
            if not isinstance(values, dict):
                raise ValueError("--strategy-parameters must be a JSON object.")
            parameters = get_strategy(args.strategy_id).parameters(values)
        elif args.strategy_id == sample.STRATEGY_ID:
            parameters = sample.Parameters(args.green_bar_count, args.hold_minutes, args.contracts)
        else:
            parameters = get_strategy(args.strategy_id).module.Parameters()
        settings = RunSettings(args.initial_capital, args.slippage_ticks, args.commission_per_contract_per_side,
                               args.tick_size, args.point_value)
        if not args.database.is_file():
            raise DatasetReadError(f"Dataset database does not exist: {args.database}")
        manifest = run_saved_dataset(DatasetStore(args.database), args.dataset_id, args.output, parameters, settings,
                                     strategy_id=args.strategy_id, from_date=args.from_date, to_date=args.to_date)
    except (ValueError, OSError, InvalidOperation, InvalidDataset) as exc:
        parser.error(str(exc))
    print(json.dumps({"output_directory": str(args.output), "summary": manifest["summary"],
                      "reconciliation": manifest["reconciliation"]}, default=json_value, indent=2))
    if manifest["summary"]["win_rate_pct"] is None:
        print("Win rate: N/A (no completed trades)")


if __name__ == "__main__":
    main()
