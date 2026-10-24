"""Run the sample strategy by saved dataset ID and write reconciled artifacts."""

import argparse
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path

from .backtest_data import DatasetReadError, read_bars
from .datasets import DatasetStore, InvalidDataset
from .execution import execute
from .reporting import generate_report, json_value
from .strategies import consecutive_green_hold as sample
from .strategy import ExecutionConfig


def _decimal_argument(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation:
        raise argparse.ArgumentTypeError("Use a decimal number, such as 0.25.") from None


def run_saved_dataset(store: DatasetStore, dataset_id: str, output_directory: Path,
                      parameters: sample.Parameters, config: ExecutionConfig) -> dict:
    """The runner wires components together; the reporter remains strategy agnostic."""
    dataset = store.get(dataset_id)
    if dataset is None:
        raise DatasetReadError(f"Dataset {dataset_id!r} was not found.")
    metadata = {
        "dataset": {name: dataset[name] for name in ("id", "name", "sha256", "source_timezone", "row_count")},
        "strategy": {
            "id": sample.STRATEGY_ID, "description": sample.DESCRIPTION,
            "source_sha256": hashlib.sha256(Path(sample.__file__).read_bytes()).hexdigest(),
            "parameters": asdict(parameters),
        },
    }
    with read_bars(store, dataset_id) as bars:
        return generate_report(execute(bars, sample.ConsecutiveGreenHold(parameters), config),
                               output_directory, config, metadata=metadata, expected_bar_count=dataset["row_count"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path(os.environ.get("ALPHAQUEST_DATA_DIR", "data")) / "datasets.sqlite3")
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--output", type=Path, required=True, help="New directory for report.json, trades.csv, equity.csv")
    parser.add_argument("--green-bar-count", type=int, default=3)
    parser.add_argument("--hold-minutes", type=int, default=20)
    parser.add_argument("--contracts", type=int, default=1)
    for name in ("initial-capital", "tick-size", "point-value", "commission-per-contract-per-side"):
        parser.add_argument(f"--{name}", required=True, type=_decimal_argument)
    parser.add_argument("--slippage-ticks", type=int, required=True)
    args = parser.parse_args()
    try:
        parameters = sample.Parameters(args.green_bar_count, args.hold_minutes, args.contracts)
        config = ExecutionConfig(args.initial_capital, args.tick_size, args.point_value,
                                 args.slippage_ticks, args.commission_per_contract_per_side)
        if not args.database.is_file():
            raise DatasetReadError(f"Dataset database does not exist: {args.database}")
        manifest = run_saved_dataset(DatasetStore(args.database), args.dataset_id, args.output, parameters, config)
    except (ValueError, OSError, InvalidOperation, InvalidDataset) as exc:
        parser.error(str(exc))
    print(json.dumps({"output_directory": str(args.output), "summary": manifest["summary"],
                      "reconciliation": manifest["reconciliation"]}, default=json_value, indent=2))
    if manifest["summary"]["win_rate_pct"] is None:
        print("Win rate: N/A (no completed trades)")


if __name__ == "__main__":
    main()
