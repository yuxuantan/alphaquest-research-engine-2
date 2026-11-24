"""Manual chronological OOS assessment of the complete frozen Narrow family."""
import csv
import io
import json
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from .backtest_requests import ExecutionSettings, OptimizationRequest
from .campaign_broad import invoke
from .campaign_narrow import branches
from .oos_criteria import POLICY, evaluate, verified_oos
from .optimization import can_resume
from .optimization_cache import artifacts, digest, engine_identity
from .research import SplitDeclaration, dates_for, metadata
from .strategies.registry import get_strategy
from .worker_limits import DEFAULT_WORKERS, MAX_WORKERS


class RunOOS(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    workers: StrictInt = Field(default=DEFAULT_WORKERS, ge=1, le=MAX_WORKERS)


def phase_status(store, workflow_id):
    with store.runs.connect() as db:
        row = db.execute('SELECT o.payload FROM optimizations o JOIN campaign_oos_state s ON s.job_id=o.id WHERE s.workflow_id=?', (workflow_id,)).fetchone()
        if not row:return 'ready'
        job = json.loads(row[0])
        if job['status'] != 'complete':return job['status']
        passed = db.execute("SELECT COUNT(*) FROM optimization_trials WHERE optimization_id=? AND json_extract(payload,'$.oos_admission.qualifies')=1", (job['id'],)).fetchone()[0]
        return 'passed' if passed else 'not_qualified'


def frozen_family(store, workflow_id):
    saved = store.raw(workflow_id)
    states = branches(store, workflow_id)
    if not states or not all(s['confirmed_at_utc'] for s in states):
        raise ValueError('Confirm every IS Narrow branch before OOS.')
    family = [dict(item) for state in states for item in state['selection']]
    if not 1 <= len(family) <= 4:
        raise ValueError('OOS requires one to four confirmed Narrow candidates.')
    identity = digest([saved['declaration'], store.broad_state(workflow_id)['selection'],
                       [(s['broad_trial'],s['confirmed_at_utc'],s['selection']) for s in states]])
    return saved, family, identity


def context(request, workflow_id, job_id=None):
    store = request.app.state.campaign_workflows
    saved, family, identity = frozen_family(store, workflow_id)
    with store.runs.connect() as db:
        if job_id:
            row = db.execute('SELECT job_id FROM campaign_oos_jobs WHERE workflow_id=? AND job_id=?', (workflow_id,job_id)).fetchone()
            if not row:raise KeyError('This OOS job does not belong to the workflow.')
        else:
            row = db.execute('SELECT job_id FROM campaign_oos_state WHERE workflow_id=?', (workflow_id,)).fetchone()
        history = [json.loads(r[0]) for r in db.execute('SELECT o.payload FROM optimizations o JOIN campaign_oos_jobs c ON c.job_id=o.id WHERE c.workflow_id=? ORDER BY o.created_at DESC', (workflow_id,))]
    job = request.app.state.optimizations.get(row[0]) if row else None
    if job and (job['research']['frozen_identity'] != identity or job['research']['oos_policy'] != POLICY):
        raise ValueError('Saved OOS assessment differs from the frozen IS family or supported policy.')
    if job and (job['research']['plan'] != saved['declaration']['plan']
                or job['execution_settings'] != saved['declaration']['execution_settings']
                or any(job['dataset'].get(k) != saved['declaration']['dataset'].get(k) for k in ('id','sha256','row_count','source_timezone','instrument_settings'))):
        raise ValueError('Saved OOS dates, execution settings or dataset differ from the frozen declaration.')
    if job and ([{k:c[k] for k in ('run_id','parameters','broad_trial','trial','report_identity')} for c in job['research']['frozen_candidates']]
                != [{k:c[k] for k in ('run_id','parameters','broad_trial','trial','report_identity')} for c in family]
                or job.get('candidate_parameters') != [c['parameters'] for c in family]):
        raise ValueError('Saved OOS membership differs from the confirmed Narrow family.')
    return saved, family, identity, job, history


def launch(request, workflow_id, body):
    store = request.app.state.campaign_workflows
    store.phase(workflow_id, 'oos')  # Full authoritative IS evidence validation before any access.
    saved, family, identity = frozen_family(store, workflow_id)
    declaration = saved['declaration']
    dataset = request.app.state.store.get(declaration['dataset']['id'])
    if not dataset or any(dataset.get(k) != declaration['dataset'].get(k) for k in ('sha256','row_count','source_timezone','instrument_settings')):
        raise ValueError('Frozen dataset or instrument settings are unavailable or changed.')
    definition = get_strategy(declaration['strategy_id'])
    if definition.description()['source_sha256'] != declaration['strategy_source_sha256']:
        raise ValueError('OOS requires the same selected strategy implementation.')
    plan = declaration['plan']
    split = dict(mode='dates', **{k:plan[k] for k in ('is_start','is_end','oos_start','oos_end')})
    if request.app.state.research.resolve(request.app.state.store,dataset,declaration['strategy_id'],SplitDeclaration.model_validate(split)) != plan:
        raise ValueError('Frozen source coverage or research dates changed.')
    # Freeze comparisons and source proofs before executing any OOS prices.
    candidates = []
    for item in family:
        report = store.runs.get(item['run_id'])
        from .market_benchmark import VERSION as BENCHMARK_VERSION
        if report.get('market_benchmark',{}).get('version') != BENCHMARK_VERSION:
            raise ValueError('The frozen benchmark model is incompatible with current OOS execution.')
        capture = report['is_screening']
        from .workflow_criteria import verified_screening
        _, stress = verified_screening(store.runs, report)
        definition.validate_source(definition.parameters(item['parameters']), dataset)
        candidates.append(dict(item, is_reference={k:capture[k] for k in ('metrics','closed_trades','total_net_pnl')},
                               parent_identity=digest([report,artifacts(store.runs.root,report),stress,artifacts(store.runs.root,stress)])))
    prior = request.app.state.research.status(dataset, declaration['strategy_id'])
    access = request.app.state.research_access.assessment_history(dataset, dates_for(plan,'oos'))
    with store.runs.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        previous = db.execute('SELECT job_id,workflow_id FROM campaign_oos_jobs WHERE request_id=?', (body.request_id.hex,)).fetchone()
        if previous:
            if previous[1] != workflow_id:raise ValueError('OOS request ID belongs to another workflow.')
            return json.loads(db.execute('SELECT payload FROM optimizations WHERE id=?',(previous[0],)).fetchone()[0]), False
        active = db.execute("SELECT 1 FROM optimizations o JOIN campaign_oos_jobs c ON c.job_id=o.id WHERE c.workflow_id=? AND json_extract(o.payload,'$.status') IN ('queued','running')", (workflow_id,)).fetchone()
        if active:raise ValueError('This workflow already has a queued or running OOS assessment.')
        for item in candidates:
            attempt, _ = request.app.state.research.reserve(plan,item['run_id'],str(uuid4()),connection=db)
            item.update(attempt_id=attempt['id'],oos_run_id=attempt['run_id'])
        axes = {name:list(dict.fromkeys(c['parameters'][name] for c in candidates)) for name in candidates[0]['parameters']}
        ranges = {name:dict(start=values[0],end=values[0],step='0' if type(values[0]) is str else 0) for name,values in axes.items()}
        body_request = OptimizationRequest(dataset_id=dataset['id'],strategy_id=declaration['strategy_id'],method='exhaustive',
            parameter_ranges=ranges,workers=body.workers,automatic_prop=False,reuse_results=False,sample_split=split,
            execution_settings=ExecutionSettings.model_validate(declaration['execution_settings']),market_benchmark=declaration['market_benchmark'])
        config = body_request.execution_settings.execution_config(dataset)
        research = metadata(plan,'oos',workflow_id=workflow_id,workflow_phase='oos',oos_policy=POLICY,
                            frozen_identity=identity,frozen_candidates=candidates,
                            prior_oos_attempts=prior['used'],prior_access=access)
        job = request.app.state.optimizations.create(body_request,dataset,definition,config,axes,len(candidates),research,
            connection=db,candidates=[c['parameters'] for c in candidates])
        db.execute('INSERT INTO campaign_oos_jobs VALUES (?,?,?)',(job['id'],workflow_id,body.request_id.hex))
        db.execute('INSERT INTO campaign_oos_state VALUES (?,?) ON CONFLICT(workflow_id) DO UPDATE SET job_id=excluded.job_id',(workflow_id,job['id']))
    return job, True


def results(request, workflow_id, job_id=None):
    saved, family, identity, job, _ = context(request, workflow_id, job_id)
    if not job:return dict(items=[],total=0,passed=0)
    with request.app.state.runs.connect() as db:
        rows = [json.loads(r[0]) for r in db.execute('SELECT payload FROM optimization_trials WHERE optimization_id=? ORDER BY trial',(job['id'],))]
    items = []
    for index, frozen in enumerate(job['research']['frozen_candidates'],1):
        row = next((r for r in rows if r['trial']==index),None)
        item = dict(trial=index,broad_trial=frozen['broad_trial'],narrow_trial=frozen['trial'],parameters=frozen['parameters'],
                    is_run_id=frozen['run_id'],is_reference=frozen['is_reference'],status='pending',qualifies=False)
        if row:
            try:
                report = request.app.state.runs.get(row['run_id'])
                if not report or report['id'] != frozen['oos_run_id']:raise ValueError('The frozen OOS report is missing or mismatched.')
                captured, stress = verified_oos(request.app.state.runs, report)
                parent = request.app.state.runs.get(frozen['run_id'])
                from .workflow_criteria import verified_screening
                _, parent_stress = verified_screening(request.app.state.runs,parent)
                if digest([parent,artifacts(request.app.state.runs.root,parent),parent_stress,artifacts(request.app.state.runs.root,parent_stress)]) != frozen['parent_identity']:
                    raise ValueError('The frozen IS comparison changed.')
                if frozen['is_reference'] != {k:parent['is_screening'][k] for k in ('metrics','closed_trades','total_net_pnl')}:
                    raise ValueError('Frozen comparison metrics differ from the original IS measurements.')
                if (report['run_metadata']['strategy']['parameters'] != frozen['parameters']
                        or report['run_metadata']['research']['parent_run_id'] != frozen['run_id']
                        or report['run_metadata']['research']['frozen_identity'] != identity
                        or digest([report,artifacts(request.app.state.runs.root,report),stress,artifacts(request.app.state.runs.root,stress)]) != row['oos_evidence_identity']):
                    raise ValueError('OOS source, parameters or measured evidence changed.')
                admission = evaluate(captured, frozen['is_reference'])
                if admission != row['oos_admission']:raise ValueError('Saved OOS verdict differs from its native evidence.')
                item.update(status=admission['status'],qualifies=admission['qualifies'],admission=admission,metrics=dict(row['metrics']),
                            run_id=report['id'],cost_stress_run_id=stress['id'],measurements=captured)
            except (ValueError,KeyError,OSError,TypeError,ArithmeticError) as exc:
                item.update(status='unavailable',error=str(exc))
        items.append(item)
    return dict(items=items,total=len(items),passed=sum(i['qualifies'] for i in items),job_id=job['id'])


router = APIRouter()


@router.get('/api/campaign-workflows/{workflow_id}/oos')
async def detail(workflow_id: UUID, request: Request, job: UUID | None = None):
    saved,family,identity,current,history = await invoke(context,request,workflow_id.hex,job.hex if job else None)
    public = []
    for item in family:
        record = await invoke(request.app.state.runs.get,item['run_id'])
        if not record or not record.get('is_screening'):raise HTTPException(409,'Frozen IS report unavailable.')
        public.append(dict(item,is_reference={k:record['is_screening'][k] for k in ('metrics','closed_trades','total_net_pnl')}))
    return dict(candidates=public,identity=identity,job=current,policy=POLICY,plan=saved['declaration']['plan'],
                history=[{k:j.get(k) for k in ('id','created_at_utc','status','completed_trials','total_trials')} for j in history],
                default_workers=DEFAULT_WORKERS,max_workers=MAX_WORKERS)


@router.post('/api/campaign-workflows/{workflow_id}/oos/run',status_code=202)
async def run(workflow_id: UUID, body: RunOOS, request: Request):
    job,fresh = await invoke(launch,request,workflow_id.hex,body)
    if fresh:
        config = ExecutionSettings.model_validate(job['execution_settings']).execution_config(job['dataset'])
        request.app.state.optimizations.executor.submit(request.app.state.optimizations.run,job,request.app.state.store,
            get_strategy(job['strategy']['id']),config,dates_for(job['research']['plan'],'oos'))
    return job


@router.get('/api/campaign-workflows/{workflow_id}/oos/results')
async def page(workflow_id: UUID, request: Request, job: UUID | None = None):
    return await invoke(results,request,workflow_id.hex,job.hex if job else None)


@router.post('/api/campaign-workflows/{workflow_id}/oos/jobs/{job_id}/resume')
async def resume(workflow_id: UUID, job_id: UUID, request: Request):
    def prepare():
        request.app.state.campaign_workflows.phase(workflow_id.hex,'oos')
        _,_,_,job,_ = context(request,workflow_id.hex,job_id.hex)
        if not can_resume(job):raise ValueError('Only interrupted, failed or stopped OOS jobs can resume.')
        if engine_identity() != job['engine_identity']:raise ValueError('Calculation code changed. Start another manual OOS assessment; saved history is retained.')
        dataset = request.app.state.store.get(job['dataset']['id'])
        if not dataset or any(dataset.get(k) != job['dataset'].get(k) for k in ('sha256','row_count','source_timezone','instrument_settings')):raise ValueError('Frozen OOS source changed.')
        with request.app.state.runs.connect() as db:
            completed = {r[0] for r in db.execute('SELECT trial FROM optimization_trials WHERE optimization_id=?',(job['id'],))}
        for index,c in enumerate(job['research']['frozen_candidates'],1):
            if index not in completed and request.app.state.runs.get(c['oos_run_id']):
                raise ValueError('A native report was saved before trial publication; retain it and start another assessment.')
        return request.app.state.optimizations.resume(job['id'])
    job = await invoke(prepare)
    config = ExecutionSettings.model_validate(job['execution_settings']).execution_config(job['dataset'])
    request.app.state.optimizations.executor.submit(request.app.state.optimizations.run,job,request.app.state.store,
        get_strategy(job['strategy']['id']),config,dates_for(job['research']['plan'],'oos'))
    return job


@router.get('/api/campaign-workflows/{workflow_id}/oos/download')
async def download(workflow_id: UUID, request: Request, job: UUID | None = None, format: str = Query('json',pattern='^(json|csv)$')):
    data = await invoke(results,request,workflow_id.hex,job.hex if job else None)
    _,_,identity,current,_ = await invoke(context,request,workflow_id.hex,job.hex if job else None)
    if format == 'json':
        payload = json.dumps(dict(policy=POLICY,frozen_identity=identity,job=current,results=data),indent=2)
    else:
        out=io.StringIO();writer=csv.writer(out);writer.writerow(['Candidate','Broad trial','Narrow trial','Parameters','Status','OOS net','OOS annual net','OOS MTM drawdown','Annual retention %','Profit/trade retention %','Checks'])
        for item in data['items']:
            m,a=item.get('metrics',{}),item.get('admission',{})
            writer.writerow([item['trial'],item['broad_trial'],item['narrow_trial'],json.dumps(item['parameters']),item['status'],m.get('total_net_pnl'),m.get('oos_annual_net_profit'),m.get('oos_mtm_max_drawdown'),a.get('annual_profit_retention_pct'),a.get('profit_per_trade_retention_pct'),json.dumps(a.get('checks',[]))])
        payload=out.getvalue()
    return Response(payload,media_type='application/json' if format=='json' else 'text/csv',headers={'Content-Disposition':f'attachment; filename="oos-{workflow_id.hex}.{format}"'})
