"""Durable campaign phase navigation and human mechanics review over native runs.

Workflow declarations and attestations live in the existing backtest catalogue.
Reports, summary values and trades remain owned by RunStore and the local engine.
"""
from datetime import datetime, timezone
from decimal import Decimal
import json
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
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
               for key, value in record['summary'].items()]
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
            ''')
            pending = [json.loads(row[0]) for row in db.execute(
                "SELECT payload FROM campaign_workflows WHERE json_extract(payload,'$.status')='running'")]
        for saved in pending:
            record = runs.get(saved['run_id'])
            if record:
                self.finish(saved['id'], record)
            else:
                self.fail(saved['id'], 'Application restarted before the validation completed. Run validation again.')

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
            self.write(db, saved)
            return saved, True

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
            if current['run_id'] == record['id'] and current['status'] in ('review_required', 'passed'):
                return  # A reload can recover the saved result before the request returns.
            if current['status'] != 'running' or current['run_id'] != record['id']:
                raise ValueError('Validation execution is no longer current.')
            db.execute('INSERT INTO campaign_workflow_runs VALUES (?,?)', (workflow_id, record['id']))
            current.update(status='review_required', review=review, error=None)
            self.write(db, current)

    def fail(self, workflow_id, error):
        with self.runs.connect() as db:
            saved = self.raw(workflow_id, db)
            if saved['status'] == 'running':
                saved.update(status='failed', error=error)
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
        passed = saved['status'] == 'passed'
        result['phases'] = [dict(id=phase, label=label, status=(saved['status'] if i == 0 else
                           'ready' if i == 1 and passed else 'locked'), implemented=i == 0)
                           for i, (phase, label) in enumerate(zip(PHASES, PHASE_LABELS))]
        result['latest_phase'] = 'is_broad' if passed else 'mechanic_validation'
        if include_results and saved['review']:
            result.update(self.results(saved))
        return result

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
async def run(workflow_id: UUID, request: Request):
    from .backtest_api import execute_backtest
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
    try:
        plan = declaration['plan']
        await run_in_threadpool(request.app.state.research.claim, plan)
        record = await execute_backtest(request, dataset, definition, parameters, config, dates_for(plan), None,
            reuse_results=False, research=metadata(plan, workflow_id=workflow_id.hex, workflow_phase='mechanic_validation'),
            run_id_override=saved['run_id'], market_benchmark=declaration['market_benchmark'], automatic_prop=False)
        await call(request, 'finish', workflow_id.hex, record)
    except Exception as exc:
        await call(request, 'fail', workflow_id.hex, str(getattr(exc, 'detail', exc)))
        raise
    return await call(request, 'get', workflow_id.hex)


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
    raise HTTPException(409, 'This phase is navigation only; its execution is not implemented in this increment.')


@router.get('/api/campaign-workflows/{workflow_id}/download')
async def download(workflow_id: UUID, request: Request):
    result = await call(request, 'get', workflow_id.hex)
    return Response(json.dumps(result, indent=2), media_type='application/json',
                    headers={'Content-Disposition': f'attachment; filename="mechanics-{workflow_id.hex}.json"'})
