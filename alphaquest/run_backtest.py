"""Run a strategy using dataset instrument defaults and optional overrides."""

import argparse
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
from uuid import uuid4

from .backtest_data import DatasetReadError, DateRange
from .backtest_config import RunSettings
from .backtest_api import run_backtest
from .backtest_runs import RunStore
from .prop.store import AnalysisStore
from .datasets import DatasetStore, InvalidDataset
from .reporting import json_value
from .strategies import consecutive_green_hold as sample
from .strategies.registry import get_strategy, STRATEGIES


def _decimal_argument(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation:
        raise argparse.ArgumentTypeError("Use a decimal number, such as 0.25.") from None


def run_saved_dataset(store: DatasetStore, dataset_id: str, output_directory: Path,
                      parameters, settings: RunSettings, *, strategy_id=sample.STRATEGY_ID,
                      from_date=None, to_date=None, report_detail='compact',reuse_results=True,reuse_prepared=True,reuse_calculations=True,sample_split=None,market_benchmark=None) -> dict:
    """Use the normal backtest/prop catalogue; expose one output shortcut."""
    dataset = store.get(dataset_id)
    if dataset is None:
        raise DatasetReadError(f"Dataset {dataset_id!r} was not found.")
    config = settings.execution_config(dataset)
    from .market_benchmark import BenchmarkSettings
    market_benchmark = BenchmarkSettings.model_validate(market_benchmark or {}).model_dump()
    definition = get_strategy(strategy_id)
    from .research import ResearchStore,SplitDeclaration,dates_for,metadata
    if from_date is not None or to_date is not None:
        raise ValueError('Declare an IS/OOS split instead of from_date/to_date.')
    if sample_split is None:raise ValueError('An IS/OOS split is required before running a backtest.')
    output=Path(output_directory).expanduser().absolute()
    if output.exists() or output.is_symlink():raise FileExistsError(f'Output already exists: {output}')
    runs=RunStore(store.path.parent)
    research=ResearchStore(runs,recover_interrupted=False)
    declaration=SplitDeclaration.model_validate(sample_split)
    plan=research.resolve(store,dataset,strategy_id,declaration)
    research.claim(plan)
    date_range=dates_for(plan)
    analyses=AnalysisStore(store.path.parent,recover_interrupted=False)
    run_id=uuid4().hex
    output.parent.mkdir(parents=True,exist_ok=True)
    destination=runs.root/run_id
    try:
        # Reserve the requested path without copying report files or creating a
        # second result store. A failed run removes only its own shortcut.
        output.symlink_to(destination,target_is_directory=True)
        record=run_backtest(store,runs,run_id,dataset,definition,parameters,config,date_range,lambda *args:None,
                            prop_analyses=analyses, report_detail=report_detail,reuse_results=reuse_results,reuse_prepared=reuse_prepared,reuse_calculations=reuse_calculations,research=metadata(plan),market_benchmark=market_benchmark)
        if record['id']!=run_id:
            output.unlink();output.symlink_to(runs.root/record['id'],target_is_directory=True)
        return record
    except BaseException:
        if output.is_symlink() and output.readlink()==destination:output.unlink()
        raise
    finally:
        analyses.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path(os.environ.get("ALPHAQUEST_DATA_DIR", "data")) / "datasets.sqlite3")
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--output", type=Path, required=True, help="New directory for report.json, trades.csv, equity.csv")
    parser.add_argument("--from-date", help="Inclusive YYYY-MM-DD in the saved source timezone")
    parser.add_argument("--to-date", help="Inclusive YYYY-MM-DD in the saved source timezone")
    parser.add_argument('--is-percent',type=float,help='IS percentage of chronological whole trading dates; the remainder is reserved for OOS.')
    for name in ('is-start','is-end','oos-start','oos-end'):
        parser.add_argument('--'+name,help='Inclusive YYYY-MM-DD in the saved source timezone')
    parser.add_argument('--report-detail',choices=('compact','full'),default='compact',help='Compact retains all trades and trade-close equity; full also writes per-bar JSON.')
    parser.add_argument("--fresh",action="store_true",help="Force a fresh backtest and prop calculation; bypass prepared data reuse.")
    parser.add_argument("--green-bar-count", type=int, default=3)
    parser.add_argument("--hold-minutes", type=int, default=20)
    parser.add_argument("--contracts", type=int, default=1)
    parser.add_argument('--benchmark-contracts', type=int, default=1, help='Fixed long holding comparison quantity, frozen before replay (default 1).')
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
        split=dict(mode='percentage',is_percent=args.is_percent) if args.is_percent is not None else dict(mode='dates',is_start=args.is_start,is_end=args.is_end,oos_start=args.oos_start,oos_end=args.oos_end)
        if args.is_percent is not None and any((args.is_start,args.is_end,args.oos_start,args.oos_end)):
            raise ValueError('Choose --is-percent or all four explicit dates, not both.')
        manifest = run_saved_dataset(DatasetStore(args.database), args.dataset_id, args.output, parameters, settings,
                                     strategy_id=args.strategy_id, from_date=args.from_date, to_date=args.to_date, report_detail=args.report_detail,reuse_results=not args.fresh,reuse_prepared=not args.fresh,reuse_calculations=not args.fresh,sample_split=split,market_benchmark={'contracts':args.benchmark_contracts})
    except (ValueError, OSError, InvalidOperation, InvalidDataset) as exc:
        parser.error(str(exc))
    print(json.dumps({"output_directory": str(args.output), "summary": manifest["summary"],
                      "backtest_id": manifest['id'],
                      "default_prop_analysis_id": manifest['run_metadata']['automatic_prop_analysis']['id'],
                      "companion_prop_analysis_ids": [item['id'] for item in manifest['run_metadata']['automatic_prop_analysis'].get('companions',[])],
                      "reconciliation": manifest["reconciliation"]}, default=json_value, indent=2))
    if manifest["summary"]["win_rate_pct"] is None:
        print("Win rate: N/A (no completed trades)")


if __name__ == "__main__":
    main()
