"""Durable campaign phase navigation and human mechanics review over native runs.

Workflow declarations and attestations live in the existing backtest catalogue.
Reports, summary values and trades remain owned by RunStore and the local engine.
"""
from datetime import datetime, timezone
import asyncio
from decimal import Decimal
import json
import logging
from threading import Event
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr
from starlette.concurrency import run_in_threadpool

from .backtest_requests import ExecutionSettings
from .datasets import COLUMNS
from .market_benchmark import BenchmarkSettings
from .market_benchmark import file_hash
from .optimization_cache import digest, engine_identity
from .research import SplitDeclaration, dates_for, metadata
from .strategies.registry import get_strategy

PHASES = ("mechanic_validation", "is_broad", "is_narrow", "oos")
PHASE_LABELS = ("Mechanic validation", "IS Broad", "IS Narrow", "OOS")
VERSION = "campaign-mechanics-v1"
EXCLUDED_PARITY_METRICS = frozenset({
    'initial_capital', 'final_equity', 'ending_position_contracts',
    'max_drawdown_pct', 'max_drawdown_duration_seconds',
})


def now():
    return datetime.now(timezone.utc).isoformat()


def sample_trades(trades):
    """Stable extrema over net-after-costs results; collect all reasons per trade."""
    trades = sorted(trades, key=lambda t: t['trade_number'])
    if not trades:
        return []
    winners = [t for t in trades if Decimal(t['net_pnl']) > 0]
    losers = [t for t in trades if Decimal(t['net_pnl']) < 0]
    choices = [("First trade", trades[0]), ("Last trade", trades[-1])]
    if winners:
        choices.append(("Biggest win", max(winners, key=lambda t: Decimal(t['net_pnl']))))
    if losers:
        choices.append(("Biggest loss", min(losers, key=lambda t: Decimal(t['net_pnl']))))
    choices.append(("Shortest duration", min(trades, key=lambda t: Decimal(t['actual_holding_minutes']))))
    selected = {}
    for reason, trade in choices:
        key = str(trade['trade_number'])
        selected.setdefault(key, dict(id=key, reasons=[], trade=trade))['reasons'].append(reason)
    return list(selected.values())


def review_rows(runs, record):
    metrics = [dict(id=key, label=key.replace('_', ' ').capitalize(), value=value)
               for key, value in record['summary'].items() if key not in EXCLUDED_PARITY_METRICS]
    with runs.connect() as db:
        trades = [json.loads(row[0]) for row in db.execute(
            'SELECT payload FROM run_trades WHERE run_id=? ORDER BY ordinal', (record['id'],))]
    if len(trades) != record['summary']['trades_taken']:
        raise ValueError('Saved trade count differs from the report; mechanics review is blocked.')
    directory = runs.root / record['id']
    report_name = record['artifacts']['report']
    if report_name not in ('report.json', 'report.json.gz'):
        raise ValueError('Unsupported saved report artifact.')
    report_file = directory / report_name
    if any(path.is_symlink() or not path.is_file() for path in (report_file, directory / 'trades.csv')):
        raise ValueError('Saved validation files are missing or changed; mechanics review is blocked.')
    identity = digest([record, trades, file_hash(directory / 'trades.csv'), file_hash(report_file)])
    return metrics, sample_trades(trades), identity


class CampaignWorkflowStore:
    def __init__(self, runs):
        self.runs = runs
        with runs.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS campaign_workflows (
                    id TEXT PRIMARY KEY, identity TEXT UNIQUE NOT NULL,
                    strategy_id TEXT NOT NULL, dataset_id TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS campaign_workflow_runs (
                    workflow_id TEXT PRIMARY KEY REFERENCES campaign_workflows(id),
                    run_id TEXT UNIQUE NOT NULL REFERENCES runs(id));
                CREATE INDEX IF NOT EXISTS workflow_strategy ON campaign_workflows(strategy_id);
                CREATE TABLE IF NOT EXISTS mechanic_job_attempts (
                    id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL REFERENCES campaign_workflows(id),
                    recorded_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
                    status TEXT NOT NULL, error TEXT, total_bars INTEGER);
                CREATE INDEX IF NOT EXISTS mechanic_jobs_recorded ON mechanic_job_attempts(recorded_at DESC);
                CREATE INDEX IF NOT EXISTS mechanic_runs_by_workflow ON runs
                    (json_extract(manifest,'$.run_metadata.research.workflow_id'));
                CREATE TABLE IF NOT EXISTS campaign_broad_jobs (
                    job_id TEXT PRIMARY KEY REFERENCES optimizations(id),
                    workflow_id TEXT NOT NULL REFERENCES campaign_workflows(id));
                CREATE TABLE IF NOT EXISTS campaign_broad_state (
                    workflow_id TEXT PRIMARY KEY REFERENCES campaign_workflows(id),payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS campaign_narrow_jobs (
                    job_id TEXT PRIMARY KEY REFERENCES optimizations(id),
                    workflow_id TEXT NOT NULL REFERENCES campaign_workflows(id), broad_trial INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS campaign_narrow_state (
                    workflow_id TEXT NOT NULL REFERENCES campaign_workflows(id),
                    broad_trial INTEGER NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(workflow_id,broad_trial));
            ''')
            # Earlier workflows recorded only their latest execution. Import only
            # known timestamps; report creation is not an inferred start time.
            for workflow_id, raw in db.execute('SELECT id,payload FROM campaign_workflows').fetchall():
                saved = json.loads(raw)
                for run_id, created in db.execute("SELECT id,created_at FROM runs WHERE json_extract(manifest,'$.run_metadata.research.workflow_id')=? AND COALESCE(json_extract(manifest,'$.run_metadata.research.workflow_phase'),'mechanic_validation')='mechanic_validation'", (workflow_id,)).fetchall():
                    db.execute("INSERT OR IGNORE INTO mechanic_job_attempts VALUES (?,?,?,NULL,NULL,'complete',NULL,NULL)", (run_id,workflow_id,created))
                if saved.get('run_id'):
                    state = 'complete' if saved.get('review') else saved['status']
                    db.execute('INSERT OR IGNORE INTO mechanic_job_attempts VALUES (?,?,?,NULL,NULL,?,?,NULL)',
                               (saved['run_id'],workflow_id,saved['updated_at_utc'],state,saved.get('error')))
            pending = [json.loads(row[0]) for row in db.execute(
                "SELECT payload FROM campaign_workflows WHERE json_extract(payload,'$.status')='running'")]
        for saved in pending:
            record = runs.get(saved['run_id'])
            if record:
                self.finish(saved['id'], record)
            else:
                self.fail(saved['id'], 'Application restarted before the validation completed. Run validation again.', interrupted=True)

    def raw(self, workflow_id, db=None):
        if db is None:
            with self.runs.connect() as db:
                return self.raw(workflow_id, db)
        row = db.execute('SELECT payload FROM campaign_workflows WHERE id=?', (workflow_id,)).fetchone()
        if not row:
            raise KeyError('Campaign dataset workflow not found.')
        return json.loads(row[0])

    def write(self, db, saved):
        saved['updated_at_utc'] = now()
        db.execute('UPDATE campaign_workflows SET payload=? WHERE id=?', (json.dumps(saved), saved['id']))

    def create(self, declaration):
        identity = digest(declaration)
        saved = dict(id=uuid4().hex, identity=identity, declaration=declaration,
                     status='not_run', run_id=None, review=None, error=None, created_at_utc=now())
        saved['updated_at_utc'] = saved['created_at_utc']
        with self.runs.connect() as db:
            db.execute('INSERT OR IGNORE INTO campaign_workflows VALUES (?,?,?,?,?)',
                       (saved['id'], identity, declaration['strategy_id'], declaration['dataset']['id'], json.dumps(saved)))
            return json.loads(db.execute('SELECT payload FROM campaign_workflows WHERE identity=?', (identity,)).fetchone()[0])

    def list(self, strategy_id):
        with self.runs.connect() as db:
            return [self.public(json.loads(row[0]), include_results=False) for row in db.execute(
                'SELECT payload FROM campaign_workflows WHERE strategy_id=? ORDER BY rowid DESC', (strategy_id,))]

    def reserve(self, workflow_id):
        with self.runs.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            saved = self.raw(workflow_id, db)
            if saved['status'] in ('running', 'review_required', 'passed'):
                return saved, False
            saved.update(status='running', run_id=uuid4().hex, error=None)
            saved.pop('stop_requested_at_utc', None)
            self.write(db, saved)
            timestamp = now()
            db.execute("INSERT INTO mechanic_job_attempts VALUES (?,?,?,?,NULL,'running',NULL,NULL)",
                       (saved['run_id'], workflow_id, timestamp, timestamp))
            return saved, True

    def request_stop(self, workflow_id, run_id):
        with self.runs.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            saved = self.raw(workflow_id, db)
            if saved['status'] != 'running' or saved['run_id'] != run_id:
                raise ValueError('Only the current running mechanic validation can be stopped.')
            if not saved.get('stop_requested_at_utc'):
                saved['stop_requested_at_utc'] = now()
                db.execute("UPDATE mechanic_job_attempts SET error='Stop requested; waiting for a backtest checkpoint.' WHERE id=?", (run_id,))
                self.write(db, saved)
        return saved

    def stop_finished(self, workflow_id, run_id):
        with self.runs.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            saved = self.raw(workflow_id, db)
            if saved['status'] != 'running' or saved['run_id'] != run_id:
                return
            reason = 'Stopped by user; no mechanic validation report was saved.'
            db.execute("UPDATE mechanic_job_attempts SET status='cancelled',finished_at=?,error=? WHERE id=?",
                       (now(), reason, run_id))
            saved.update(status='cancelled', error=reason)
            self.write(db, saved)

    def finish(self, workflow_id, record):
        saved = self.raw(workflow_id)
        provenance = record['run_metadata']
        declaration = saved['declaration']
        if (record['id'] != saved['run_id'] or provenance.get('research', {}).get('workflow_id') != workflow_id
                or provenance['strategy']['parameters'] != declaration['default_parameters']
                or provenance['strategy']['source_sha256'] != declaration['strategy_source_sha256']
                or record['execution_settings'] != declaration['execution_settings']
                or provenance['research']['plan'] != declaration['plan']
                or any(provenance['dataset'][key] != declaration['dataset'][key]
                       for key in ('id', 'sha256', 'source_timezone'))):
            raise ValueError('Validation result does not match its frozen workflow declaration.')
        metrics, samples, identity = review_rows(self.runs, record)
        review = dict(revision=0, result_identity=identity,
                      metric_checks={row['id']: False for row in metrics},
                      trade_parity={row['id']: False for row in samples},
                      trade_correctness={row['id']: False for row in samples}, confirmed_at_utc=None,
                      attestation='User confirms MultiCharts parity and execution correctness; no automated MC comparison.')
        with self.runs.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = self.raw(workflow_id, db)
            db.execute("UPDATE mechanic_job_attempts SET status='complete',finished_at=CASE WHEN started_at IS NOT NULL THEN COALESCE(finished_at,?) ELSE finished_at END,error=NULL,total_bars=? WHERE id=?",
                       (now(), record['run_metadata']['selection']['row_count'], record['id']))
            if current['run_id'] == record['id'] and current['status'] in ('review_required', 'passed'):
                return  # A reload can recover the saved result before the request returns.
            if current['status'] != 'running' or current['run_id'] != record['id']:
                raise ValueError('Validation execution is no longer current.')
            db.execute('INSERT INTO campaign_workflow_runs VALUES (?,?)', (workflow_id, record['id']))
            current.update(status='review_required', review=review, error=None)
            current.pop('stop_requested_at_utc', None)
            self.write(db, current)

    def fail(self, workflow_id, error, interrupted=False):
        with self.runs.connect() as db:
            saved = self.raw(workflow_id, db)
            if saved['status'] == 'running':
                db.execute('UPDATE mechanic_job_attempts SET status=?,finished_at=?,error=? WHERE id=?',
                           ('interrupted' if interrupted else 'failed', now(), error, saved['run_id']))
                saved.update(status='failed', error=error)
                saved.pop('stop_requested_at_utc', None)
                self.write(db, saved)

    def results(self, saved):
        record = self.runs.get(saved['run_id'])
        if not record:
            raise ValueError('The validation report is unavailable; no phase can advance.')
        metrics, samples, identity = review_rows(self.runs, record)
        if identity != saved['review']['result_identity']:
            raise ValueError('Saved validation results changed; the review cannot be reused.')
        return dict(metrics=metrics, trade_samples=samples, report=record,
                    missing_samples=[reason for reason in ('Biggest win', 'Biggest loss')
                                     if not any(reason in sample['reasons'] for sample in samples)])

    def public(self, saved, include_results=True):
        result = dict(saved)
        if saved['review'] and saved['status'] == 'review_required':
            # Project pending legacy checklists without rewriting saved reviews
            # on reads. Confirmed historical attestations remain intact.
            result['review'] = dict(saved['review'], metric_checks={
                key: value for key, value in saved['review']['metric_checks'].items()
                if key not in EXCLUDED_PARITY_METRICS})
        passed = saved['status'] == 'passed'
        broad = self.broad_state(saved['id'])
        broad_passed = bool(broad.get('confirmed_at_utc'))
        from .campaign_narrow import branches
        narrow = branches(self, saved['id']) if broad_passed else []
        narrow_passed = bool(narrow) and all(branch['confirmed_at_utc'] for branch in narrow)
        narrow_status = ('passed' if narrow_passed else
                         'running' if any(branch['status'] in ('queued','running') for branch in narrow) else
                         'review_required' if any(branch['status']=='review_required' for branch in narrow) else
                         'ready')
        statuses = [saved['status'], broad['status'] if passed else 'locked',
                    narrow_status if passed and broad_passed else 'locked',
                    'ready' if narrow_passed else 'locked']
        result['broad'] = broad
        result['narrow'] = narrow
        result['phases'] = [dict(id=phase, label=label, status=statuses[i], implemented=i <= 2)
                           for i, (phase, label) in enumerate(zip(PHASES, PHASE_LABELS))]
        result['latest_phase'] = 'oos' if narrow_passed else 'is_narrow' if passed and broad_passed else 'is_broad' if passed else 'mechanic_validation'
        if include_results and saved['review']:
            result.update(self.results(saved))
        return result

    def broad_state(self, workflow_id, db=None):
        if db is None:
            with self.runs.connect() as db:
                return self.broad_state(workflow_id, db)
        row = db.execute('SELECT payload FROM campaign_broad_state WHERE workflow_id=?',(workflow_id,)).fetchone()
        state = json.loads(row[0]) if row else dict(job_id=None,revision=0,selected_trials=[],selection=[],confirmed_at_utc=None)
        raw = db.execute('SELECT payload FROM optimizations WHERE id=?',(state['job_id'],)).fetchone() if state['job_id'] else None
        job_status = json.loads(raw[0])['status'] if raw else 'ready'
        state['status'] = ('passed' if state['confirmed_at_utc'] else
                           'review_required' if job_status == 'complete' else job_status)
        return state

    def get(self, workflow_id):
        saved = self.raw(workflow_id)
        if saved['status'] == 'running':
            record = self.runs.get(saved['run_id'])
            if record:
                self.finish(workflow_id, record)
                saved = self.raw(workflow_id)
        return self.public(saved)

    def save_review(self, workflow_id, body, confirm=False):
        with self.runs.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            saved = self.raw(workflow_id, db)
            if saved['status'] != 'review_required':
                raise ValueError('A completed, unconfirmed mechanic validation is required.')
            # Check the exact report before accepting checks or a final attestation.
            self.results(saved)
            review = saved['review']
            if review['revision'] != body.revision:
                raise ValueError('Review changed in another tab. Reload before confirming these results.')
            review['metric_checks'] = {key: value for key, value in review['metric_checks'].items()
                                       if key not in EXCLUDED_PARITY_METRICS}
            if confirm:
                groups = [review[key] for key in ('metric_checks', 'trade_parity', 'trade_correctness')]
                if not all(groups) or not all(all(group.values()) for group in groups):
                    raise ValueError('Review every metric and each sampled trade for MC parity and execution correctness. Zero-trade runs cannot pass mechanics.')
                saved['status'] = 'passed'
                review['confirmed_at_utc'] = now()
            else:
                for key in ('metric_checks', 'trade_parity', 'trade_correctness'):
                    incoming = getattr(body, key)
                    if incoming.keys() != review[key].keys():
                        raise ValueError('Review rows must exactly match this validation report.')
                    review[key] = incoming
            review['revision'] += 1
            self.write(db, saved)
        return self.get(workflow_id)

    def phase(self, workflow_id, phase):
        if phase not in PHASES:
            raise KeyError('Unknown campaign phase.')
        saved = self.get(workflow_id)
        index = PHASES.index(phase)
        if any(p['status'] != 'passed' for p in saved['phases'][:index]):
            raise ValueError('Previous phases must all pass in order before opening this phase.')
        if index >= 2:
            from .campaign_broad import validate_frozen
            validate_frozen(self, saved['id'], saved['broad'])
        if index >= 3:
            from .campaign_narrow import validate_frozen as validate_narrow
            validate_narrow(self, saved['id'], saved['narrow'])
        return saved, saved['phases'][index]


class CreateWorkflow(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dataset_id: StrictStr = Field(min_length=1, max_length=128)
    strategy_id: StrictStr = Field(min_length=1, max_length=128)
    execution_settings: ExecutionSettings
    sample_split: SplitDeclaration
    market_benchmark: BenchmarkSettings = Field(default_factory=BenchmarkSettings)


class ReviewRevision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: StrictInt = Field(ge=0)


class ReviewChecks(ReviewRevision):
    metric_checks: dict[str, StrictBool]
    trade_parity: dict[str, StrictBool]
    trade_correctness: dict[str, StrictBool]


router = APIRouter()


async def call(request, method, *args):
    try:
        return await run_in_threadpool(getattr(request.app.state.campaign_workflows, method), *args)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(409, 'Saved validation files are unavailable; no review was accepted.') from exc


@router.get('/api/campaign-workflows')
async def listing(request: Request, strategy_id: str):
    return dict(items=await call(request, 'list', strategy_id))


@router.post('/api/campaign-workflows', status_code=201)
async def create(body: CreateWorkflow, request: Request):
    def prepare():
        dataset = request.app.state.store.get(body.dataset_id)
        if not dataset:
            raise HTTPException(404, 'Dataset not found.')
        if dataset['columns'] != COLUMNS:
            raise ValueError('Mechanic validation requires a native OHLCV dataset.')
        definition = get_strategy(body.strategy_id)
        description = definition.description()
        parameters = {p['name']: p['default'] for p in description['parameters']}
        definition.validate_source(definition.parameters(parameters), dataset)
        config = body.execution_settings.execution_config(dataset)
        plan = request.app.state.research.resolve(request.app.state.store, dataset, body.strategy_id, body.sample_split)
        from dataclasses import asdict
        snapshot = {key: dataset.get(key) for key in ('id', 'name', 'sha256', 'bytes', 'row_count',
                    'source_timezone', 'instrument_settings', 'symbol', 'start', 'end')}
        declaration = dict(version=VERSION, strategy_id=body.strategy_id, dataset=snapshot,
                           default_parameters=parameters, strategy_source_sha256=description['source_sha256'],
                           engine_identity=engine_identity(), execution_settings=json.loads(json.dumps(asdict(config), default=str)),
                           plan=plan, market_benchmark=body.market_benchmark.model_dump())
        return request.app.state.campaign_workflows.create(declaration)
    try:
        saved = await run_in_threadpool(prepare)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return await call(request, 'get', saved['id'])


@router.get('/api/campaign-workflows/{workflow_id}')
async def get(workflow_id: UUID, request: Request):
    return await call(request, 'get', workflow_id.hex)


@router.post('/api/campaign-workflows/{workflow_id}/run')
async def run(workflow_id: UUID, request: Request, background: bool = False):
    from .backtest_api import BacktestStopped, execute_backtest
    saved = await call(request, 'raw', workflow_id.hex)
    if saved['status'] in ('review_required', 'passed', 'running'):
        return await call(request, 'get', workflow_id.hex)
    declaration = saved['declaration']
    dataset = await run_in_threadpool(request.app.state.store.get, declaration['dataset']['id'])
    if not dataset:
        raise HTTPException(409, 'Source dataset is unavailable. Saved results can still be inspected.')
    if any(dataset[k] != declaration['dataset'][k] for k in ('sha256', 'source_timezone', 'instrument_settings')):
        raise HTTPException(409, 'Source identity or instrument defaults changed; create a new workflow.')
    definition = get_strategy(declaration['strategy_id'])
    if await run_in_threadpool(engine_identity) != declaration['engine_identity']:
        raise HTTPException(409, 'Calculation code changed; create a new workflow. Earlier results remain available.')
    parameters = definition.parameters(declaration['default_parameters'])
    config = ExecutionSettings.model_validate(declaration['execution_settings']).execution_config(dataset)
    saved, fresh = await call(request, 'reserve', workflow_id.hex)
    if not fresh:
        return await call(request, 'get', workflow_id.hex)
    stop_event = Event()
    request.app.state.mechanic_stops[saved['run_id']] = stop_event
    async def execute_validation():
        try:
            plan = declaration['plan']
            if stop_event.is_set():
                raise BacktestStopped('Stopped before validation began.')
            await run_in_threadpool(request.app.state.research.claim, plan)
            record = await execute_backtest(request, dataset, definition, parameters, config, dates_for(plan), UUID(saved['run_id']),
                reuse_results=False, research=metadata(plan, workflow_id=workflow_id.hex, workflow_phase='mechanic_validation'),
                run_id_override=saved['run_id'], market_benchmark=declaration['market_benchmark'], automatic_prop=False,
                stop_event=stop_event)
            await call(request, 'finish', workflow_id.hex, record)
        except BacktestStopped:
            await call(request, 'stop_finished', workflow_id.hex, saved['run_id'])
        except Exception as exc:
            await call(request, 'fail', workflow_id.hex, str(getattr(exc, 'detail', exc)))
            if not background:
                raise
        finally:
            request.app.state.mechanic_stops.pop(saved['run_id'], None)
    if background:
        task = asyncio.create_task(execute_validation())
        request.app.state.mechanic_tasks.add(task)
        def finished(completed):
            request.app.state.mechanic_tasks.discard(completed)
            if not completed.cancelled() and (error := completed.exception()):
                logging.getLogger(__name__).error('Mechanic job bookkeeping failed', exc_info=error)
        task.add_done_callback(finished)
        return JSONResponse(request.app.state.campaign_workflows.public(saved), status_code=202)
    await execute_validation()
    return await call(request, 'get', workflow_id.hex)


@router.post('/api/campaign-workflows/{workflow_id}/runs/{run_id}/stop')
async def stop_validation(workflow_id: UUID, run_id: UUID, request: Request):
    event = request.app.state.mechanic_stops.get(run_id.hex)
    if event is None:
        raise HTTPException(409, 'This mechanic validation is no longer running on this server. Reload its job status.')
    saved = await call(request, 'request_stop', workflow_id.hex, run_id.hex)
    event.set()
    return request.app.state.campaign_workflows.public(saved)


@router.patch('/api/campaign-workflows/{workflow_id}/review')
async def review(workflow_id: UUID, body: ReviewChecks, request: Request):
    return await call(request, 'save_review', workflow_id.hex, body)


@router.post('/api/campaign-workflows/{workflow_id}/confirm')
async def confirm(workflow_id: UUID, body: ReviewRevision, request: Request):
    return await call(request, 'save_review', workflow_id.hex, body, True)


@router.get('/api/campaign-workflows/{workflow_id}/phases/{phase}')
async def phase_view(workflow_id: UUID, phase: str, request: Request):
    saved, phase = await call(request, 'phase', workflow_id.hex, phase)
    return dict(workflow_id=saved['id'], phase=phase)


@router.post('/api/campaign-workflows/{workflow_id}/phases/{phase}/run')
async def phase_run(workflow_id: UUID, phase: str, request: Request):
    await call(request, 'phase', workflow_id.hex, phase)
    if phase == 'is_broad':
        raise HTTPException(409, 'Calculate a parameter grid using /broad/preview, then submit it through /broad/run.')
    raise HTTPException(409, 'This phase is navigation only; its execution is not implemented in this increment.')


@router.get('/api/campaign-workflows/{workflow_id}/download')
async def download(workflow_id: UUID, request: Request):
    result = await call(request, 'get', workflow_id.hex)
    return Response(json.dumps(result, indent=2), media_type='application/json',
                    headers={'Content-Disposition': f'attachment; filename="mechanics-{workflow_id.hex}.json"'})
