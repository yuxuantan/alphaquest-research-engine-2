"""Exact exhaustive grids and durable optimization jobs using normal backtests."""

from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, wait, FIRST_COMPLETED
from contextlib import nullcontext
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
from .backtest_api import BacktestStopped
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
METRICS = (*BACKTEST_METRICS, "historical_net", "lucid_historical_net")


def can_resume(job):
    return job['status'] in ('failed', 'interrupted') or (
        job['status'] == 'cancelled' and bool(job.get('stop_requested_at_utc')))


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
        from .optimization_prop import initialize
        initialize(runs, prop_analyses)

    def close(self):
        self.executor.shutdown(wait=True)

    def create(self, request, dataset, definition, config, axes, total, research=None, *, connection=None):
        job = {"id": uuid4().hex, "created_at_utc": datetime.now(timezone.utc).isoformat(),
               "status": "queued", "stage": "queued", "completed_trials": 0, "total_trials": total,
               "bars_processed": 0, "total_bars": 0, "active_trials": [], "results_snapshot_rowid": 0,
               "worker_count": min(request.workers, total), "worker_pids": [], "failed_trials": [], "request": request.model_dump(), "axes": axes,
               "dataset": dataset, "strategy": definition.description(), "report_detail": "compact", "research": research,
               "engine_identity": engine_identity(), "reused_trials": 0, "default_prop_profile": profile() if request.automatic_prop else None,
               "prop_unavailable_trials": 0, "prop_error_trials": 0,
               "execution_settings": {key: str(value) if isinstance(value, Decimal) else value for key, value in asdict(config).items()},
               "step_counts": {name: len(values) for name, values in axes.items()},
               "metric_columns": list(METRICS if request.automatic_prop else BACKTEST_METRICS)}
        if research and research.get('screening_policy'):
            from .workflow_criteria import METRICS as SCREENING_METRICS
            job['metric_columns'].extend(SCREENING_METRICS)
        with (self.runs.connect() if connection is None else nullcontext(connection)) as conn:
            conn.execute("INSERT INTO optimizations VALUES (?, ?, ?)", (job["id"], job["created_at_utc"], json.dumps(job)))
        return job

    def update(self, job_id, **values):
        with self.runs.connect() as conn:
            row = conn.execute("SELECT payload FROM optimizations WHERE id=?", (job_id,)).fetchone()
            job = {**json.loads(row[0]), **values}
            if job.get('stop_requested_at_utc') and job['status'] == 'running':
                job['stage'] = 'stopping'
            conn.execute("UPDATE optimizations SET payload=? WHERE id=?", (json.dumps(job), job_id))
        return job

    def stop_requested(self, job_id):
        with self.runs.connect() as conn:
            row = conn.execute("SELECT json_extract(payload,'$.stop_requested_at_utc') FROM optimizations WHERE id=?", (job_id,)).fetchone()
        return bool(row and row[0])

    def request_stop(self, job_id):
        """Request a checkpoint stop without discarding completed trial reports."""
        with self.runs.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT payload FROM optimizations WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError("Backtest activity not found.")
            job = json.loads(row[0])
            if job['status'] == 'queued':
                now = datetime.now(timezone.utc).isoformat()
                job.update(status='cancelled', stage='cancelled', cancelled_at_utc=now,
                           finished_at_utc=now, cancellation_reason='Cancelled before execution; saved reports retained.',
                           active_trials=[], worker_pids=[])
            elif job['status'] == 'running':
                if job.get('stop_requested_at_utc'):
                    return job
                job.update(stop_requested_at_utc=datetime.now(timezone.utc).isoformat(), stage='stopping')
            elif job['status'] == 'cancelled':
                return job
            else:
                raise ValueError(f"Only queued or running activities can be stopped; this activity is {job['status']}.")
            conn.execute("UPDATE optimizations SET payload=? WHERE id=?", (json.dumps(job), job_id))
        return job

    def finish_execution(self, job_id, failures, elapsed):
        """Set the terminal state under the same lock used by stop requests."""
        with self.runs.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            job = json.loads(conn.execute('SELECT payload FROM optimizations WHERE id=?', (job_id,)).fetchone()[0])
            stopped = bool(job.get('stop_requested_at_utc')) and not failures and job['completed_trials'] < job['total_trials']
            status = 'failed' if failures else 'cancelled' if stopped else 'complete'
            job.update(status=status, stage='failed' if failures else 'cancelled' if stopped else 'done',
                       active_trials=[], failed_trials=failures,
                       elapsed_seconds=elapsed, finished_at_utc=datetime.now(timezone.utc).isoformat())
            if failures:
                job['error'] = f"Trial {failures[0]['trial']}: {failures[0]['error']}"
            if stopped:
                job.update(cancelled_at_utc=job['finished_at_utc'],
                           cancellation_reason='Stopped during execution; completed trials and reports retained.')
            conn.execute('UPDATE optimizations SET payload=? WHERE id=?', (json.dumps(job), job_id))
        return job

    def cancel_queued(self, job_id):
        """Cancel only before the coordinator claims execution; retain all results."""
        with self.runs.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT payload FROM optimizations WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError("Backtest activity not found.")
            job = json.loads(row[0])
            if job["status"] == "cancelled":
                return job
            if job["status"] != "queued":
                raise ValueError(f"Only queued activities can be cancelled; this activity is {job['status']}. Refresh to see its current state.")
            now = datetime.now(timezone.utc).isoformat()
            job.update(status="cancelled", stage="cancelled", cancelled_at_utc=now,
                       finished_at_utc=now, cancellation_reason="Cancelled before execution; saved reports retained.",
                       active_trials=[], worker_pids=[])
            conn.execute("UPDATE optimizations SET payload=? WHERE id=?", (json.dumps(job), job_id))
        return job

    def _claim_queued(self, job_id):
        # The same write lock as cancellation makes the boundary unambiguous.
        # A cancelled/deleted queued callback must do nothing, including no
        # runtime admission, source access, cache reuse or report publication.
        with self.runs.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT payload FROM optimizations WHERE id=?", (job_id,)).fetchone()
            if row is None:
                return None
            job = json.loads(row[0])
            if job["status"] != "queued":
                return None
            job.update(status="running", stage="preparing", started_at_utc=datetime.now(timezone.utc).isoformat())
            conn.execute("UPDATE optimizations SET payload=? WHERE id=?", (json.dumps(job), job_id))
        return job

    def resume(self, job_id):
        """Atomically claim an incomplete job; successful trial rows stay untouched."""
        with self.runs.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT payload FROM optimizations WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise ValueError('This backtest activity has been deleted.')
            job = json.loads(row[0])
            if not can_resume(job):
                raise ValueError("Only failed, interrupted or stopped running optimizations can be resumed.")
            saved = conn.execute("SELECT COUNT(*) FROM optimization_trials WHERE optimization_id=?", (job_id,)).fetchone()[0]
            if saved != job["completed_trials"]:
                raise ValueError("Saved trial count does not match this job; inspect the catalogue before resuming.")
            attempts = list(job.get("previous_attempts", []))
            attempts.append({key: job.get(key) for key in (
                "status", "error", "failed_trials", "elapsed_seconds", "started_at_utc", "finished_at_utc", "completed_trials",
                "cancelled_at_utc", "cancellation_reason", "stop_requested_at_utc")})
            job.update(status="queued", stage="queued", active_trials=[], failed_trials=[], previous_attempts=attempts,
                       worker_count=job.get("worker_count", 1), elapsed_seconds=0)
            for key in ("error", "started_at_utc", "finished_at_utc", "cancelled_at_utc", "cancellation_reason", "stop_requested_at_utc"):
                job.pop(key, None)
            conn.execute("UPDATE optimizations SET payload=? WHERE id=?", (json.dumps(job), job_id))
        return job

    def delete(self, job_id):
        """Delete an inactive activity and its exclusively referenced reports.

        Keep a durable cleanup state until files and activity rows are gone, so
        an interrupted post-commit cleanup can be retried after a restart.
        """
        with self.prop_analyses.lock:
            with self.prop_analyses.connect() as campaign_db:
                if campaign_db.execute('SELECT 1 FROM campaign_jobs WHERE optimization_id=?', (job_id,)).fetchone():
                    raise ValueError('This optimization job is referenced by an immutable research campaign and cannot be deleted.')
            with self.runs.deletion(
                'Backtest reports removed from the library, but file cleanup failed. '
                'Retry Delete activity and reports to finish cleanup.'
            ) as (conn, stage):
                if conn.execute("SELECT 1 FROM sqlite_master WHERE name='campaign_broad_jobs'").fetchone():
                    if conn.execute('SELECT 1 FROM campaign_broad_jobs WHERE job_id=?',(job_id,)).fetchone():
                        raise ValueError('This IS Broad job is retained by a campaign workflow and cannot be deleted.')
                if conn.execute("SELECT 1 FROM sqlite_master WHERE name='campaign_narrow_jobs'").fetchone():
                    if conn.execute('SELECT 1 FROM campaign_narrow_jobs WHERE job_id=?',(job_id,)).fetchone():
                        raise ValueError('This IS Narrow job is retained by a campaign workflow and cannot be deleted.')
                row = conn.execute('SELECT payload FROM optimizations WHERE id=?', (job_id,)).fetchone()
                if row is None:
                    return None
                job = json.loads(row[0])
                if job['status'] in ('queued', 'running'):
                    raise ValueError('This backtest activity is queued or running. Wait for it to finish before deleting.')
                deletion = job.get('deletion')
                if deletion is None:
                    ids = {row[0] for row in conn.execute(
                        "SELECT json_extract(payload,'$.run_id') FROM optimization_trials WHERE optimization_id=?", (job_id,))}
                    shared = {row[0] for row in conn.execute(
                        """SELECT DISTINCT r.id FROM optimization_trials t
                           JOIN runs r ON r.id=json_extract(t.payload,'$.run_id')
                           WHERE t.optimization_id<>? AND r.id IN
                           (SELECT json_extract(payload,'$.run_id') FROM optimization_trials WHERE optimization_id=?)""",
                        (job_id, job_id))}
                    ids -= shared
                    busy = self.prop_analyses.active_sources()
                    if ids & busy:
                        raise ValueError('This activity contains a backtest referenced by a research campaign or running prop analysis; it cannot be deleted.')
                    # Check all reports before moving any files.
                    if ids & self.runs.detail_active:
                        raise ValueError('Full detail is being generated for a backtest in this activity. Wait for it to finish before deleting.')
                    deletion = dict(run_ids=sorted(ids), deleted_reports=0, shared_reports_kept=len(shared))
                    for run_id in deletion['run_ids']:
                        if stage(run_id):deletion['deleted_reports'] += 1
                    job.update(status='deleting', stage='deleting', deletion=deletion)
                    conn.execute('UPDATE optimizations SET payload=? WHERE id=?', (json.dumps(job), job_id))
                else:
                    for run_id in deletion['run_ids']:stage(run_id)
            # Retain the activity and retry IDs if cleanup or this commit fails.
            with self.runs.connect() as conn:
                conn.execute('BEGIN IMMEDIATE')
                conn.execute('DELETE FROM optimization_trials WHERE optimization_id=?', (job_id,))
                conn.execute('DELETE FROM optimizations WHERE id=?', (job_id,))
        return {key: deletion[key] for key in ('deleted_reports', 'shared_reports_kept')}

    def get(self, job_id):
        with self.runs.connect() as conn:
            row = conn.execute("SELECT payload FROM optimizations WHERE id=?", (job_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, offset, limit):
        with self.runs.connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM optimizations").fetchone()[0]
            rows = conn.execute("SELECT payload FROM optimizations ORDER BY created_at DESC, id LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        return {"items": [json.loads(row[0]) for row in rows], "total": total, "offset": offset, "limit": limit}

    def page(self, job, sort, direction, offset, limit, prop_revision=None):
        from .optimization_prop import revision
        from .optimization_display import trading_day_duration
        durations = {}
        def trading_days(run_id, manifest):
            if run_id not in durations:
                try:
                    durations[run_id] = trading_day_duration(self.runs.root / run_id, json.loads(manifest)) if manifest else None
                except (OSError, ValueError, TypeError, KeyError, ArithmeticError):
                    durations[run_id] = None
            return durations[run_id]
        current_revision=revision(self.runs, job['id'])
        prop_revision = current_revision if prop_revision is None else min(prop_revision,current_revision)
        columns = {"trial": "$.trial", "run_id": "$.run_id",
                   **{f"param.{name}": f"$.parameters.{name}" for name in job["axes"]},
                   **{name: f"$.metrics.{name}" for name in job["metric_columns"]}}
        if 'max_drawdown_duration_seconds' in job['metric_columns']:
            columns['max_drawdown_duration_trading_days'] = '$.run_id'
        if sort not in columns or direction not in ("asc", "desc"):
            raise ValueError("Unknown sort column or direction.")
        # Paths are selected from server-owned names; values never become SQL.
        expression = "json_extract(t.payload, ?)"
        if sort == 'lucid_historical_net':
            expression = "CASE WHEN l.id IS NOT NULL THEN json_extract(l.payload,'$.historical_net') ELSE json_extract(t.payload, ?) END"
        elif sort == 'historical_net':
            expression = "CASE WHEN a.id IS NOT NULL THEN json_extract(a.payload,'$.historical_net') ELSE json_extract(t.payload, ?) END"
        elif sort == 'max_drawdown_duration_trading_days':
            expression = 'aq_trading_days(json_extract(t.payload, ?), r.manifest)'
        order = f"({expression} IS NULL) ASC, CAST({expression} AS TEXT) COLLATE {'BINARY' if sort == 'run_id' else 'EXACT_DECIMAL'} {direction.upper()}, t.trial ASC"
        with self.runs.connect() as conn:
            conn.create_function('aq_trading_days', 2, trading_days)
            conn.create_collation("EXACT_DECIMAL", lambda a, b: (Decimal(a) > Decimal(b)) - (Decimal(a) < Decimal(b)))
            # New jobs snapshot by publication rowid, not trial number: parallel
            # completion can publish trial 7 before trial 1. Legacy serial jobs
            # retain the previous count-based boundary without a migration.
            boundary = "rowid" if "results_snapshot_rowid" in job else "trial"
            snapshot = job.get("results_snapshot_rowid", job["completed_trials"])
            rows = conn.execute(f"""SELECT t.payload, r.id IS NOT NULL,l.payload,a.payload,r.manifest
                FROM optimization_trials t LEFT JOIN optimization_prop_links l ON l.id=
                (SELECT MAX(id) FROM optimization_prop_links WHERE optimization_id=t.optimization_id AND trial=t.trial AND account='lucid' AND id<=?)
                LEFT JOIN optimization_prop_links a ON a.id=
                (SELECT MAX(id) FROM optimization_prop_links WHERE optimization_id=t.optimization_id AND trial=t.trial AND account='apex' AND id<=?)
                LEFT JOIN runs r ON r.id=json_extract(t.payload,'$.run_id')
                WHERE t.optimization_id=? AND t.{boundary}<=? ORDER BY {order} LIMIT ? OFFSET ?""",
                (prop_revision,prop_revision, job["id"], snapshot, columns[sort], columns[sort], limit, offset)).fetchall()
        items=[]
        for payload,available,refresh_payload,apex_payload,manifest in rows:
            row=json.loads(payload)
            row['display_metrics'] = dict(max_drawdown_duration_trading_days=trading_days(row['run_id'], manifest))
            if refresh_payload:
                refreshed=json.loads(refresh_payload)
                row['original_prop_companions']=row.get('prop_companions',[])
                row['original_lucid_historical_net']=row['metrics'].get('lucid_historical_net')
                row['prop_companions']=[refreshed,*row.get('prop_companions',[])[1:]]
                row['metrics']['lucid_historical_net']=refreshed.get('historical_net')
                row['lucid_refresh']=dict(original_analysis_id=refreshed.get('original_analysis_id'),model_version=refreshed['model_version'])
            if apex_payload:
                refreshed=json.loads(apex_payload)
                row['original_prop_analysis']=row.get('prop_analysis')
                row['original_historical_net']=row['metrics'].get('historical_net')
                row['prop_analysis']=refreshed
                row['metrics']['historical_net']=refreshed.get('historical_net')
                row['apex_refresh']=dict(original_analysis_id=refreshed.get('original_analysis_id'),model_version=refreshed['model_version'])
            if not available:row['backtest_deleted']=True
            primary=row.get('prop_analysis')
            if primary:
                primary.setdefault('model_version',(job.get('default_prop_profile') or {}).get('model_version'))
                if primary.get('id'):
                    analysis=self.prop_analyses.get(primary['id'])
                    if analysis is None:row['prop_report_deleted']=True
                    elif primary['status'] in ('queued','running'):primary['progress']=analysis['progress']
            profiles=(job.get('default_prop_profile') or {}).get('companions',[])
            for index,item in enumerate(row.get('prop_companions',[])):
                if index<len(profiles):item.setdefault('model_version',profiles[index].get('model_version'))
                if item.get('id'):
                    analysis=self.prop_analyses.get(item['id'])
                    if analysis is None:item['status']='deleted'
                    elif item['status'] in ('queued','running'):
                        item['progress']=analysis['progress']
            items.append(row)
        return {"items": items, "total": job["completed_trials"], "offset": offset, "limit": limit, "prop_revision":prop_revision}

    def publish(self, job_id, trial, run_id, context, result):
        """Only the coordinator publishes reports and writes the SQLite catalogue."""
        prop = result.get("prop_analysis")
        publishing = time.perf_counter()
        if result.get('cost_stress'):
            stress = result['cost_stress']
            self.runs.complete(stress['run_id'], context.output_root / stress['run_id'], stress['manifest'])
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
        if record.get('is_screening'):
            row['screening'] = record['is_screening']
            row['metrics'].update(record['is_screening']['metrics'])
            stress = self.runs.get(record['is_screening']['cost_stress']['run_id'])
            row['screening_evidence_identity'] = digest([record, artifacts(self.runs.root, record), stress, artifacts(self.runs.root, stress)])
        if prop:
            row.update(prop_analysis={key: prop[key] for key in ("id", "status", "historical_net", "reason")})
            row['prop_companions']=[{key:item[key] for key in ('id','status','historical_net','reason')} for item in prop.get('companions',[])]
            row["metrics"]["historical_net"] = prop["historical_net"]
            row['metrics']['lucid_historical_net']=next((p['historical_net'] for p in prop.get('companions',[])),None)
        self._record_trial(job_id, row)
        job = self.get(job_id)
        if job.get("engine_identity") and job["request"].get("reuse_results", True) and (not prop or prop["status"] != "error"):
            key = trial_key(job, row["parameters"])
            cached = {"row": row, "record_hash": digest(record), "artifacts": artifacts(self.runs.root, record),
                      "optimization_id": job_id}
            if record.get('is_screening'):
                stress = self.runs.get(record['is_screening']['cost_stress']['run_id'])
                cached['stress_identity'] = digest([stress,artifacts(self.runs.root,stress)])
            if prop:
                cached["prop_fingerprint"] = self.prop_analyses.fingerprint(prop["id"])
                cached['companion_fingerprints']={item['id']:self.prop_analyses.fingerprint(item['id']) for item in prop.get('companions',[])}
                if any(value is None for value in cached['companion_fingerprints'].values()):return job['completed_trials']
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
                if any(item['status']=='error' for item in [row['prop_analysis'],*row.get('prop_companions',[])]):
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
        # Reference publication and deletion must agree on whether this report
        # is shared with another activity before any files can be removed.
        with self.runs.detail_lock:
            return self._reuse_trial_locked(job, trial, values)

    def _reuse_trial_locked(self, job, trial, values):
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
            if record.get('is_screening'):
                from .workflow_criteria import verified_screening
                _, stress = verified_screening(self.runs, record)
                if digest([stress,artifacts(self.runs.root,stress)]) != cached.get('stress_identity'):
                    return False
            if job.get("default_prop_profile"):
                prop=cached["row"].get("prop_analysis")
                if not prop or not cached.get("prop_fingerprint") or self.prop_analyses.fingerprint(prop["id"]) != cached.get("prop_fingerprint"):
                    return False
                for item in cached['row'].get('prop_companions',[]):
                    fingerprint=self.prop_analyses.fingerprint(item['id'])
                    if item['status']=='error' or fingerprint is None or fingerprint!=cached.get('companion_fingerprints',{}).get(item['id']):return False
        except (OSError,ValueError,KeyError):
            return False
        reused = {**cached["row"], "trial": trial, "execution": {
            "reused": True, "source_optimization_id": cached["optimization_id"], "elapsed_seconds": 0,
            "worker_pid": None}}
        self._record_trial(job["id"], reused)
        return True

    def run(self, job, source, definition, config, date_range):
        job = self._claim_queued(job['id'])
        if job is None:
            return
        with self.prop_analyses.runtime.optimization(job['worker_count']):
            return self._run(job,source,definition,config,date_range)

    def _run(self, job, source, definition, config, date_range):
        job_id = job["id"]
        started = time.monotonic()
        failures = []
        active = {}
        last_update = 0

        def check_stop():
            if self.stop_requested(job_id):
                raise BacktestStopped('Stopped by user at a backtest checkpoint.')

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
            check_stop()
            from .research_access import guard_read
            guard_read(source,job["dataset"]["id"],date_range,kind='strategy_execution',origin='optimization:'+job_id)
            if job.get("engine_identity") and engine_identity() != job["engine_identity"]:
                raise ValueError("Engine code changed while this job was queued. Start a new optimization.")
            with self.runs.connect() as conn:
                saved = {row[0] for row in conn.execute("SELECT trial FROM optimization_trials WHERE optimization_id=?", (job_id,))}
            pending = []
            for trial, values in enumerate(combinations(job['axes']), 1):
                check_stop()
                if trial not in saved and not self._reuse_trial(job, trial, values):
                    pending.append((trial, values))
            with TemporaryDirectory(prefix=".optimization-", dir=self.runs.root) as temporary:
                root = Path(temporary)
                snapshot = root / "source.csv"
                prepared, features = None, {}
                preparation_started = time.monotonic()
                if pending:
                    with snapshot.open("wb") as stream:
                        for chunk in source.iter_csv(job["dataset"]["id"]):
                            check_stop()
                            stream.write(chunk)
                    if job["request"].get("prepare_data", True) and len(pending) > job["worker_count"]:
                        from .optimization_worker import FrozenSource
                        def preparation_progress(stage, processed, total):
                            check_stop()
                            self.update(job_id, stage=stage, bars_processed=processed, total_bars=total,
                                        elapsed_seconds=time.monotonic() - started)
                        preparation_progress("preparing_data", 0, job["dataset"]["row_count"])
                        prepared = prepare_data(FrozenSource(job["dataset"], snapshot), job["dataset"]["id"], date_range, root / "bars.bin", preparation_progress,cache=self.runs.replay_cache)
                        snapshot.unlink()
                        features = prepare_features(definition, prepared, [values for _, values in pending], root,
                                                    preparation_progress, workers=job["worker_count"],cache=self.runs.replay_cache)
                check_stop()
                self.update(job_id, preparation_seconds=time.monotonic() - preparation_started,
                            prepared_data=prepared is not None, cached_feature_series=len(features),
                            temporary_bytes=sum(path.stat().st_size for path in root.iterdir() if path.is_file()))
                context = TrialContext(snapshot, root, job["dataset"], job["strategy"]["id"], config, date_range, prepared, features,
                                       default_prop=bool(job.get("default_prop_profile")),
                                       calculation_cache=self.prop_analyses.calculation_snapshot() if job.get("default_prop_profile") else None,
                                       research=job.get('research'),market_benchmark=job['request'].get('market_benchmark'))
                trials = iter(pending)
                workers = job["worker_count"]
                if workers == 1:
                    for trial, values in trials:
                        check_stop()
                        run_id = uuid4().hex
                        try:
                            def serial_progress(stage, processed, total):
                                check_stop()
                                progress(trial, stage, processed, total, os.getpid())
                            result = compute_trial(context, trial, values, run_id,
                                                   serial_progress)
                            self.publish(job_id, trial, run_id, context, result)
                            active.pop(trial, None)
                        except BacktestStopped:
                            raise
                        except Exception as exc:
                            logger.exception("Optimization %s trial %s failed", job_id, trial)
                            failures.append({"trial": trial, "error": str(exc)})
                            break
                elif pending:
                    self._run_parallel(job_id, context, trials, workers, active, progress, save_progress, failures)
            self.finish_execution(job_id, failures, time.monotonic() - started)
        except BacktestStopped:
            self.finish_execution(job_id, [], time.monotonic() - started)
        except Exception as exc:
            logger.exception("Optimization %s coordinator failed", job_id)
            self.update(job_id, status="failed", stage="failed", error=str(exc), active_trials=[],
                        failed_trials=failures, elapsed_seconds=time.monotonic() - started,
                        finished_at_utc=datetime.now(timezone.utc).isoformat())

    def _run_parallel(self, job_id, context, trials, workers, active, progress, save_progress, failures):
        spawn = multiprocessing.get_context("spawn")
        # A manager-owned queue survives a worker dying mid-message; a raw
        # multiprocessing.Queue can leave a partial frame and hang its reader.
        pending = {}
        with spawn.Manager() as manager:
            messages = manager.Queue(maxsize=workers * 16)
            stop_event = manager.Event()
            if self.stop_requested(job_id):
                stop_event.set()
            with ProcessPoolExecutor(max_workers=workers, mp_context=spawn, initializer=initialize_worker,
                                     initargs=(context, messages, stop_event)) as pool:
                def submit_next():
                    if stop_event.is_set():
                        return False
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
                    if self.stop_requested(job_id):
                        stop_event.set()
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
                        except BacktestStopped:
                            continue
                        except Exception as exc:
                            logger.exception("Optimization %s trial %s failed", job_id, trial)
                            failures.append({"trial": trial, "error": str(exc)})
                    if failures or stop_event.is_set():
                        # Do not launch more trials. Already running trials finish
                        # and successful reports are published before cleanup.
                        for future in pending:
                            future.cancel()
                    else:
                        while len(pending) < workers and submit_next():
                            pass
                    save_progress()
