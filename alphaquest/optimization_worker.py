"""Spawn-safe, database-free backtest computation for optimization workers."""

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
from queue import Full
import time

from .backtest_api import prepare_backtest_report
from .backtest_data import DateRange, DatasetReadError
from .strategies.registry import get_strategy
from .strategy import ExecutionConfig
from .prop.automatic import descriptor, compute_default
from .performance import Performance


@dataclass(frozen=True)
class TrialContext:
    snapshot: Path
    output_root: Path
    dataset: dict
    strategy_id: str
    config: ExecutionConfig
    date_range: DateRange
    prepared: object = None
    feature_paths: dict | None = None
    default_prop: bool = True


class FrozenSource:
    def __init__(self, dataset, path):
        self.dataset, self.path = dataset, path

    def get(self, dataset_id):
        return self.dataset if dataset_id == self.dataset["id"] else None

    def iter_csv(self, dataset_id):
        if self.get(dataset_id) is None:
            raise DatasetReadError("Unknown optimization source.")
        with self.path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                yield chunk

    def open_snapshot(self, dataset_id):
        if self.get(dataset_id) is None:
            raise DatasetReadError("Unknown optimization source.")
        return self.path.open("rb")


def compute_trial(context, trial, values, run_id, progress):
    """Retain compact reports; only small metadata crosses process boundaries."""
    started = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()
    definition = get_strategy(context.strategy_id)
    automatic = descriptor() if context.default_prop else None
    timings = Performance()
    manifest, processed, total = prepare_backtest_report(
        FrozenSource(context.dataset, context.snapshot), context.output_root / run_id,
        context.dataset, definition, definition.parameters(values), context.config,
        context.date_range, progress, report_detail="compact", prepared=context.prepared,
        feature_paths=context.feature_paths, automatic_prop=automatic, timings=timings)
    with timings.span('prop_analysis'):
        prop_result = compute_default(context.output_root, run_id, manifest, context.output_root / ("prop-" + automatic["id"]), automatic,
                                      lambda message: progress("prop_simulation: " + message, processed, total)) if automatic else None
    if prop_result:timings.details['prop_backend']=prop_result.get('native_kernel',{}).get('name','source incompatible')
    return {"manifest": manifest, "processed": processed, "total": total, "prop_analysis": prop_result, 'performance': timings.snapshot(),
            "execution": {"worker_pid": os.getpid(), "started_at_utc": started_at,
                          "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                          "elapsed_seconds": time.monotonic() - started,
                          "prepared_data": context.prepared is not None,
                          "cached_features": len(context.feature_paths or {}), "reused": False}}


_context = None
_progress_queue = None


def initialize_worker(context, progress_queue):
    global _context, _progress_queue
    _context, _progress_queue = context, progress_queue


def run_trial(trial, values, run_id):
    last_update = 0
    previous_stage = None

    def progress(stage, processed, total):
        nonlocal last_update, previous_stage
        now = time.monotonic()
        if stage != previous_stage or now - last_update >= .25:
            try:
                _progress_queue.put_nowait({"trial": trial, "worker_pid": os.getpid(),
                                           "stage": stage, "bars_processed": processed, "total_bars": total})
            except Full:
                pass
            previous_stage, last_update = stage, now

    return compute_trial(_context, trial, values, run_id, progress)
