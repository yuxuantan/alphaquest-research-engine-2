"""Exact exhaustive grids and durable optimization jobs using normal backtests."""

from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
from dataclasses import asdict
from decimal import Decimal, localcontext
from fractions import Fraction
from itertools import product
import json
import logging
import multiprocessing
import os
import sqlite3
from pathlib import Path
from queue import Empty
from tempfile import TemporaryDirectory
import time
from uuid import uuid4

from .optimization_worker import TrialContext, compute_trial, initialize_worker, run_trial
from .prepared_data import prepare_data
from .strategy_features import prepare_features
from .optimization_cache import engine_identity, trial_key, artifacts, digest
from .prop.automatic import profile, publish_backtest

MAX_COMBINATIONS = 10_000
from .worker_limits import MAX_WORKERS,DEFAULT_WORKERS
logger = logging.getLogger(__name__)
BACKTEST_METRICS = (
    "total_net_pnl", "total_gross_pnl", "total_commissions", "total_slippage_cost",
    "final_equity", "trades_taken", "winning_trades", "losing_trades", "breakeven_trades",
    "win_rate_pct", "max_drawdown_amount", "max_drawdown_pct", "max_drawdown_duration_seconds",
)
METRICS = (*BACKTEST_METRICS, "historical_net")


def grid(definition, ranges):
    """Enumerate start + n * step through end, using exact arithmetic."""
    fields = definition.description()["parameters"]
    if set(ranges) != {field["name"] for field in fields}:
        raise ValueError("Supply start, end and step for every strategy parameter, with no extra parameters.")
    axes = {}
    total = 1
    for field in fields:
        name, kind = field["name"], field["type"]
        spec = ranges[name]
        start, end, step = spec.start, spec.end, spec.step
        if kind == "bool":
            if type(start) is not bool or type(end) is not bool:
                raise ValueError(f"{name}: boolean endpoints must be true or false.")
            expected_step = 0 if start == end else 1
            if type(step) is not int or step != expected_step:
                raise ValueError(f"{name}: boolean step must be {expected_step} for these endpoints.")
            axis = [start] if start == end else [start, end]
            count = len(axis)
        else:
            if kind == "int":
                if any(type(value) is not int or abs(value) > 2**53 - 1 for value in (start, end, step)):
                    raise ValueError(f"{name}: endpoints and step must be safe integers.")
                a, b, increment = map(Fraction, (start, end, step))
            elif kind == "Decimal":
                if any(not isinstance(value, str) or len(value) > 128 for value in (start, end, step)):
                    raise ValueError(f"{name}: decimal endpoints and step must be decimal strings (at most 128 characters).")
                try:
                    values = [Decimal(value) for value in (start, end, step)]
                    if any(not value.is_finite() or abs(value.adjusted()) > 100 or value.as_tuple().exponent < -100 for value in values):
                        raise ValueError()
                    a, b, increment = map(Fraction, values)
                except (ValueError, ArithmeticError):
                    raise ValueError(f"{name}: enter finite decimals within 100 decimal places/orders of magnitude.") from None
            else:
                raise ValueError(f"{name}: unsupported optimization parameter type {kind}.")
            if a > b:
                raise ValueError(f"{name}: start must be <= end.")
            if a == b:
                if increment != 0:
                    raise ValueError(f"{name}: step must be 0 when start equals end.")
                count = 1
            else:
                if increment <= 0:
                    raise ValueError(f"{name}: step must be greater than 0 when start and end differ.")
                count = (b - a) // increment + 1
            # Check the product before allocating any potentially large axis.
            if total * count > MAX_COMBINATIONS:
                raise ValueError(f"Exhaustive optimization is limited to {MAX_COMBINATIONS:,} combinations per job.")
            with localcontext() as context:
                context.prec = 512
                values = (a + i * increment for i in range(count))
                axis = [int(value) if kind == "int" else str(Decimal(value.numerator) / Decimal(value.denominator)) for value in values]
        total *= count
        if total > MAX_COMBINATIONS:
            raise ValueError(f"Exhaustive optimization is limited to {MAX_COMBINATIONS:,} combinations per job.")
        axes[name] = axis
    # Strategy validation includes coupled constraints and HHMM validity.
    for values in combinations(axes):
        definition.parameters(values)
    return axes, total


def combinations(axes):
    return (dict(zip(axes, values)) for values in product(*axes.values()))


class OptimizationStore:
    def __init__(self, runs, prop_analyses):
        self.runs = runs
        self.prop_analyses = prop_analyses
        with runs.connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS optimizations (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS optimization_trials (
                    optimization_id TEXT NOT NULL REFERENCES optimizations(id),
                    trial INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(optimization_id, trial)
                );
                CREATE TABLE IF NOT EXISTS optimization_trial_cache (
                    key TEXT PRIMARY KEY, payload TEXT NOT NULL
                );
            """)
            for job_id, payload in conn.execute("SELECT id, payload FROM optimizations").fetchall():
                job = json.loads(payload)
                if job["status"] in ("queued", "running"):
                    job.update(status="interrupted", stage="interrupted", error="Server restarted before completion. Saved trials remain available; this job was not resumed.")
                    conn.execute("UPDATE optimizations SET payload=? WHERE id=?", (json.dumps(job), job_id))
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="optimization")

    def close(self):
        self.executor.shutdown(wait=True)

    def create(self, request, dataset, definition, config, axes, total):
        job = {"id": uuid4().hex, "created_at_utc": datetime.now(timezone.utc).isoformat(),
               "status": "queued", "stage": "queued", "completed_trials": 0, "total_trials": total,
               "bars_processed": 0, "total_bars": 0, "active_trials": [], "results_snapshot_rowid": 0,
               "worker_count": min(request.workers, total), "worker_pids": [], "failed_trials": [], "request": request.model_dump(), "axes": axes,
               "dataset": dataset, "strategy": definition.description(), "report_detail": "compact",
               "engine_identity": engine_identity(), "reused_trials": 0, "default_prop_profile": profile(),
               "prop_unavailable_trials": 0, "prop_error_trials": 0,
               "execution_settings": {key: str(value) if isinstance(value, Decimal) else value for key, value in asdict(config).items()},
               "step_counts": {name: len(values) for name, values in axes.items()}, "metric_columns": list(METRICS)}
        with self.runs.connect() as conn:
            conn.execute("INSERT INTO optimizations VALUES (?, ?, ?)", (job["id"], job["created_at_utc"], json.dumps(job)))
        return job

    def update(self, job_id, **values):
        with self.runs.connect() as conn:
            row = conn.execute("SELECT payload FROM optimizations WHERE id=?", (job_id,)).fetchone()
            job = {**json.loads(row[0]), **values}
            conn.execute("UPDATE optimizations SET payload=? WHERE id=?", (json.dumps(job), job_id))
        return job

    def resume(self, job_id):
        """Atomically claim an incomplete job; successful trial rows stay untouched."""
        with self.runs.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            job = json.loads(conn.execute("SELECT payload FROM optimizations WHERE id=?", (job_id,)).fetchone()[0])
            if job["status"] not in ("failed", "interrupted"):
                raise ValueError("Only failed or interrupted optimizations can be resumed.")
            saved = conn.execute("SELECT COUNT(*) FROM optimization_trials WHERE optimization_id=?", (job_id,)).fetchone()[0]
            if saved != job["completed_trials"]:
                raise ValueError("Saved trial count does not match this job; inspect the catalogue before resuming.")
            attempts = list(job.get("previous_attempts", []))
            attempts.append({key: job.get(key) for key in (
                "status", "error", "failed_trials", "elapsed_seconds", "started_at_utc", "finished_at_utc", "completed_trials")})
            job.update(status="queued", stage="queued", active_trials=[], failed_trials=[], previous_attempts=attempts,
                       worker_count=job.get("worker_count", 1), elapsed_seconds=0)
            for key in ("error", "started_at_utc", "finished_at_utc"):
                job.pop(key, None)
            conn.execute("UPDATE optimizations SET payload=? WHERE id=?", (json.dumps(job), job_id))
        return job

    def get(self, job_id):
        with self.runs.connect() as conn:
            row = conn.execute("SELECT payload FROM optimizations WHERE id=?", (job_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, offset, limit):
        with self.runs.connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM optimizations").fetchone()[0]
            rows = conn.execute("SELECT payload FROM optimizations ORDER BY created_at DESC, id LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        return {"items": [json.loads(row[0]) for row in rows], "total": total, "offset": offset, "limit": limit}

    def page(self, job, sort, direction, offset, limit):
        columns = {"trial": "$.trial", "run_id": "$.run_id",
                   **{f"param.{name}": f"$.parameters.{name}" for name in job["axes"]},
                   **{name: f"$.metrics.{name}" for name in job["metric_columns"]}}
        if sort not in columns or direction not in ("asc", "desc"):
            raise ValueError("Unknown sort column or direction.")
        # Paths are selected from server-owned names; values never become SQL.
        expression = "json_extract(t.payload, ?)"
        order = f"({expression} IS NULL) ASC, CAST({expression} AS TEXT) COLLATE {'BINARY' if sort == 'run_id' else 'EXACT_DECIMAL'} {direction.upper()}, trial ASC"
        with self.runs.connect() as conn:
            conn.create_collation("EXACT_DECIMAL", lambda a, b: (Decimal(a) > Decimal(b)) - (Decimal(a) < Decimal(b)))
            # New jobs snapshot by publication rowid, not trial number: parallel
            # completion can publish trial 7 before trial 1. Legacy serial jobs
            # retain the previous count-based boundary without a migration.
            boundary = "rowid" if "results_snapshot_rowid" in job else "trial"
            snapshot = job.get("results_snapshot_rowid", job["completed_trials"])
            rows = conn.execute(f"SELECT t.payload, EXISTS(SELECT 1 FROM runs r WHERE r.id=json_extract(t.payload,'$.run_id')) FROM optimization_trials t WHERE optimization_id=? AND t.{boundary}<=? ORDER BY {order} LIMIT ? OFFSET ?",
                                (job["id"], snapshot, columns[sort], columns[sort], limit, offset)).fetchall()
        items=[]
        for payload,available in rows:
            row=json.loads(payload)
            if not available:row['backtest_deleted']=True
            items.append(row)
        return {"items": items, "total": job["completed_trials"], "offset": offset, "limit": limit}

    def publish(self, job_id, trial, run_id, context, result):
        """Only the coordinator publishes reports and writes the SQLite catalogue."""
        prop = result.get("prop_analysis")
        publishing = time.perf_counter()
        record = publish_backtest(self.runs, self.prop_analyses, run_id, context.output_root / run_id, result["manifest"],
                                  prop, context.output_root / ("prop-" + prop["id"]) if prop else None)
        if result.get('performance'):
            from .performance import save_performance
            diagnostic=result['performance']
            diagnostic['phases_seconds']['publication']=time.perf_counter()-publishing
            diagnostic['elapsed_seconds']+=diagnostic['phases_seconds']['publication']
            save_performance(self.runs.root/run_id,diagnostic)
        row = {"trial": trial, "run_id": record["id"],
               "parameters": record["run_metadata"]["strategy"]["parameters"],
               "metrics": {name: record["summary"][name] for name in BACKTEST_METRICS},
               "execution": result["execution"]}
        if prop:
            row.update(prop_analysis={key: prop[key] for key in ("id", "status", "historical_net", "reason")})
            row["metrics"]["historical_net"] = prop["historical_net"]
        self._record_trial(job_id, row)
        job = self.get(job_id)
        if job.get("engine_identity") and job["request"].get("reuse_results", True) and (not prop or prop["status"] != "error"):
            key = trial_key(job, row["parameters"])
            cached = {"row": row, "record_hash": digest(record), "artifacts": artifacts(self.runs.root, record),
                      "optimization_id": job_id}
            if prop:
                cached["prop_fingerprint"] = self.prop_analyses.fingerprint(prop["id"])
                if cached["prop_fingerprint"] is None:
                    return job["completed_trials"]
            with self.runs.connect() as conn:
                conn.execute("INSERT OR REPLACE INTO optimization_trial_cache VALUES (?, ?)", (key, json.dumps(cached)))
        return job["completed_trials"]

    def _record_trial(self, job_id, row):
        with self.runs.connect() as conn:
            inserted = conn.execute("INSERT INTO optimization_trials VALUES (?, ?, ?)", (job_id, row["trial"], json.dumps(row)))
            current = json.loads(conn.execute("SELECT payload FROM optimizations WHERE id=?", (job_id,)).fetchone()[0])
            current.update(completed_trials=current["completed_trials"] + 1, results_snapshot_rowid=inserted.lastrowid)
            if row.get("prop_analysis"):
                if row["prop_analysis"]["status"] == "error":
                    current["prop_error_trials"] = current.get("prop_error_trials", 0) + 1
                elif row["metrics"].get("historical_net") is None:
                    current["prop_unavailable_trials"] = current.get("prop_unavailable_trials", 0) + 1
            if row["execution"].get("reused"):
                current["reused_trials"] = current.get("reused_trials", 0) + 1
            elif row["execution"].get("worker_pid"):
                current["worker_pids"] = sorted(set(current["worker_pids"]) | {row["execution"]["worker_pid"]})
            conn.execute("UPDATE optimizations SET payload=? WHERE id=?", (json.dumps(current), job_id))
        return current["completed_trials"]

    def _reuse_trial(self, job, trial, values):
        if not job.get("engine_identity") or not job["request"].get("reuse_results", True):
            return False
        with self.runs.connect() as conn:
            row = conn.execute("SELECT payload FROM optimization_trial_cache WHERE key=?", (trial_key(job, values),)).fetchone()
        if not row:
            return False
        cached = json.loads(row[0])
        record = self.runs.get(cached["row"]["run_id"])
        try:
            if not record or digest(record) != cached["record_hash"] or artifacts(self.runs.root, record) != cached["artifacts"]:
                return False
            if job.get("default_prop_profile"):
                prop=cached["row"].get("prop_analysis")
                if not prop or not cached.get("prop_fingerprint") or self.prop_analyses.fingerprint(prop["id"]) != cached.get("prop_fingerprint"):
                    return False
        except (OSError,ValueError,KeyError):
            return False
        reused = {**cached["row"], "trial": trial, "execution": {
            "reused": True, "source_optimization_id": cached["optimization_id"], "elapsed_seconds": 0,
            "worker_pid": None}}
        self._record_trial(job["id"], reused)
        return True

    def run(self, job, source, definition, config, date_range):
        with self.prop_analyses.runtime.optimization(job['worker_count']):
            return self._run(job,source,definition,config,date_range)

    def _run(self, job, source, definition, config, date_range):
        job_id = job["id"]
        started = time.monotonic()
        failures = []
        active = {}
        last_update = 0

        def progress(trial, stage, processed, total, worker_pid=None):
            nonlocal last_update
            active[trial] = {"trial": trial, "stage": stage, "bars_processed": processed,
                             "total_bars": total, "worker_pid": worker_pid}
            now = time.monotonic()
            if now - last_update >= .25:
                save_progress()
                last_update = now

        def save_progress():
            try:
                self.update(job_id, status="running", stage="finishing_active_trials" if failures else "running_trials",
                            failed_trials=list(failures), active_trials=list(active.values()),
                            bars_processed=sum(item["bars_processed"] for item in active.values()),
                            total_bars=sum(item["total_bars"] for item in active.values()),
                            elapsed_seconds=time.monotonic() - started)
            except sqlite3.OperationalError as exc:
                if getattr(exc, "sqlite_errorcode", 0) & 255 != sqlite3.SQLITE_CANTOPEN:
                    raise
                # Progress is advisory. A missed update must not discard the
                # completed reports of every worker that is still computing.
                logger.exception("Could not save progress for optimization %s; continuing active trials", job_id)

        try:
            if job.get("engine_identity") and engine_identity() != job["engine_identity"]:
                raise ValueError("Engine code changed while this job was queued. Start a new optimization.")
            self.update(job_id, status="running", stage="preparing", started_at_utc=datetime.now(timezone.utc).isoformat())
            with self.runs.connect() as conn:
                saved = {row[0] for row in conn.execute("SELECT trial FROM optimization_trials WHERE optimization_id=?", (job_id,))}
            pending = [(trial, values) for trial, values in enumerate(combinations(job["axes"]), 1)
                       if trial not in saved and not self._reuse_trial(job, trial, values)]
            with TemporaryDirectory(prefix=".optimization-", dir=self.runs.root) as temporary:
                root = Path(temporary)
                snapshot = root / "source.csv"
                prepared, features = None, {}
                preparation_started = time.monotonic()
                if pending:
                    with snapshot.open("wb") as stream:
                        for chunk in source.iter_csv(job["dataset"]["id"]):
                            stream.write(chunk)
                    if job["request"].get("prepare_data", True) and len(pending) > job["worker_count"]:
                        from .optimization_worker import FrozenSource
                        def preparation_progress(stage, processed, total):
                            self.update(job_id, stage=stage, bars_processed=processed, total_bars=total,
                                        elapsed_seconds=time.monotonic() - started)
                        preparation_progress("preparing_data", 0, job["dataset"]["row_count"])
                        prepared = prepare_data(FrozenSource(job["dataset"], snapshot), job["dataset"]["id"], date_range, root / "bars.bin", preparation_progress,cache=self.runs.replay_cache)
                        snapshot.unlink()
                        features = prepare_features(definition, prepared, [values for _, values in pending], root,
                                                    preparation_progress, workers=job["worker_count"],cache=self.runs.replay_cache)
                self.update(job_id, preparation_seconds=time.monotonic() - preparation_started,
                            prepared_data=prepared is not None, cached_feature_series=len(features),
                            temporary_bytes=sum(path.stat().st_size for path in root.iterdir() if path.is_file()))
                context = TrialContext(snapshot, root, job["dataset"], job["strategy"]["id"], config, date_range, prepared, features,
                                       default_prop=bool(job.get("default_prop_profile")),calculation_cache=self.prop_analyses.calculation_snapshot())
                trials = iter(pending)
                workers = job["worker_count"]
                if workers == 1:
                    for trial, values in trials:
                        run_id = uuid4().hex
                        try:
                            result = compute_trial(context, trial, values, run_id,
                                                   lambda stage, processed, total: progress(trial, stage, processed, total, os.getpid()))
                            self.publish(job_id, trial, run_id, context, result)
                            active.pop(trial, None)
                        except Exception as exc:
                            logger.exception("Optimization %s trial %s failed", job_id, trial)
                            failures.append({"trial": trial, "error": str(exc)})
                            break
                elif pending:
                    self._run_parallel(job_id, context, trials, workers, active, progress, save_progress, failures)
            self.update(job_id, status="failed" if failures else "complete", stage="failed" if failures else "done",
                        active_trials=[], failed_trials=failures,
                        **({"error": f"Trial {failures[0]['trial']}: {failures[0]['error']}"} if failures else {}),
                        elapsed_seconds=time.monotonic() - started, finished_at_utc=datetime.now(timezone.utc).isoformat())
        except Exception as exc:
            logger.exception("Optimization %s coordinator failed", job_id)
            self.update(job_id, status="failed", stage="failed", error=str(exc), active_trials=[],
                        failed_trials=failures, elapsed_seconds=time.monotonic() - started)

    def _run_parallel(self, job_id, context, trials, workers, active, progress, save_progress, failures):
        spawn = multiprocessing.get_context("spawn")
        # A manager-owned queue survives a worker dying mid-message; a raw
        # multiprocessing.Queue can leave a partial frame and hang its reader.
        pending = {}
        with spawn.Manager() as manager:
            messages = manager.Queue(maxsize=workers * 16)
            with ProcessPoolExecutor(max_workers=workers, mp_context=spawn, initializer=initialize_worker,
                                     initargs=(context, messages)) as pool:
                def submit_next():
                    try:
                        trial, values = next(trials)
                    except StopIteration:
                        return False
                    run_id = uuid4().hex
                    try:
                        future = pool.submit(run_trial, trial, values, run_id)
                    except Exception as exc:
                        failures.append({"trial": trial, "error": str(exc), "phase": "submission"})
                        return False
                    pending[future] = (trial, run_id)
                    active[trial] = {"trial": trial, "stage": "starting", "bars_processed": 0, "total_bars": 0, "worker_pid": None}
                    return True

                for _ in range(workers):
                    if not submit_next():
                        break
                save_progress()
                while pending:
                    done, _ = wait(pending, timeout=.2, return_when=FIRST_COMPLETED)
                    while True:
                        try:
                            message = messages.get_nowait()
                        except Empty:
                            break
                        if message["trial"] in active:
                            progress(message["trial"], message["stage"], message["bars_processed"],
                                     message["total_bars"], message["worker_pid"])
                    # Completion order is independent of deterministic trial IDs.
                    for future in sorted(done, key=lambda item: pending[item][0]):
                        trial, run_id = pending.pop(future)
                        active.pop(trial, None)
                        if future.cancelled():
                            continue
                        try:
                            self.publish(job_id, trial, run_id, context, future.result())
                        except Exception as exc:
                            logger.exception("Optimization %s trial %s failed", job_id, trial)
                            failures.append({"trial": trial, "error": str(exc)})
                    if failures:
                        # Do not launch more trials. Already running trials finish
                        # and successful reports are published before cleanup.
                        for future in pending:
                            future.cancel()
                    else:
                        while len(pending) < workers and submit_next():
                            pass
                    save_progress()
