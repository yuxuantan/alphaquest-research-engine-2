"""IS Broad orchestration and immutable manual selection over ordinary optimizer jobs."""
from decimal import Decimal, InvalidOperation
import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr
from starlette.concurrency import run_in_threadpool

from .backtest_requests import ExecutionSettings, OptimizationRequest, ParameterRange
from .campaign_workflow import now
from .datasets import COLUMNS
from .optimization import grid, combinations
from .optimization_cache import artifacts, digest, engine_identity
from .research import SplitDeclaration, dates_for, metadata
from .strategies.registry import get_strategy
from .worker_limits import MAX_WORKERS
from .workflow_criteria import PREVIOUS_VERSION, policy, stage_criteria, verified_screening

CRITERION = 'All five IS Broad criteria must pass; insufficient evidence cannot qualify.'


class BroadGrid(BaseModel):
    model_config = ConfigDict(extra='forbid')
    parameter_ranges: dict[str, ParameterRange]
    workers: StrictInt = Field(default=1,ge=1,le=MAX_WORKERS)


class BroadLaunch(BroadGrid):
    revision: StrictInt = Field(ge=0)
    preview_token: StrictStr


class Selection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    job_id: UUID
    revision: StrictInt = Field(ge=0)
    trials: list[StrictInt] = Field(max_length=2)


class ConfirmSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    job_id: UUID
    revision: StrictInt = Field(ge=0)


def eligible(row, target_policy=None):
    try:
        from .workflow_criteria import evaluate
        measured = row['screening']
        if measured['policy'] not in (policy(PREVIOUS_VERSION),policy()):
            return False
        original = evaluate(measured['metrics'], measured['closed_trades'], measured['total_net_pnl'], measured['policy'])
        if any(measured[key] != original[key] for key in original):
            return False
        admission = evaluate(measured['metrics'], measured['closed_trades'], measured['total_net_pnl'], target_policy or policy())
        return admission['qualifies'] and not row.get('backtest_deleted',False)
    except (KeyError,InvalidOperation,ValueError,TypeError):
        return False


def prepare(request, workflow_id, body):
    store = request.app.state.campaign_workflows
    saved, _ = store.phase(workflow_id,'is_broad')
    if saved['broad']['confirmed_at_utc']:
        raise ValueError('IS Broad selection is confirmed and cannot be changed or rerun.')
    declared = saved['declaration']
    dataset = request.app.state.store.get(declared['dataset']['id'])
    if not dataset or dataset.get('columns') != COLUMNS:
        raise ValueError('The native source dataset is unavailable.')
    if any(dataset.get(key) != declared['dataset'].get(key) for key in ('sha256','source_timezone','row_count','instrument_settings')):
        raise ValueError('The source dataset or instrument settings changed; configure and validate a new workflow.')
    definition = get_strategy(declared['strategy_id'])
    if definition.description()['source_sha256'] != declared['strategy_source_sha256']:
        raise ValueError('Strategy source changed since mechanic validation; validate a new workflow.')
    axes,total = grid(definition,body.parameter_ranges)
    for values in combinations(axes):
        definition.validate_source(definition.parameters(values),dataset)
    plan = declared['plan']
    split = dict(mode='dates',**{k:plan[k] for k in ('is_start','is_end','oos_start','oos_end')})
    resolved = request.app.state.research.resolve(request.app.state.store,dataset,declared['strategy_id'],
        SplitDeclaration.model_validate(split))
    if resolved != plan:
        raise ValueError('The saved research window no longer matches the source.')
    body_request = OptimizationRequest(dataset_id=dataset['id'],strategy_id=declared['strategy_id'],method='exhaustive',
        parameter_ranges=body.parameter_ranges,workers=body.workers,automatic_prop=False,reuse_results=True,
        execution_settings=ExecutionSettings.model_validate(declared['execution_settings']),sample_split=split,
        market_benchmark=declared['market_benchmark'])
    config = body_request.execution_settings.execution_config(dataset)
    token = digest(dict(workflow_identity=saved['identity'],mechanics=saved['review']['result_identity'],
                        request=body_request.model_dump(),engine=engine_identity(),screening_policy=policy()))
    return saved,dataset,definition,config,axes,total,body_request,token


def preview(request, workflow_id, body):
    saved,_,_,_,axes,total,_,token = prepare(request,workflow_id,body)
    return dict(total_trials=total,step_counts={k:len(v) for k,v in axes.items()},preview_token=token,
                revision=saved['broad']['revision'],criterion=CRITERION)


def launch(request, workflow_id, body):
    store = request.app.state.campaign_workflows
    saved,dataset,definition,config,axes,total,request_body,token = prepare(request,workflow_id,body)
    if token != body.preview_token:
        raise ValueError('The preview is stale. Calculate the grid again before running.')
    request.app.state.research.claim(saved['declaration']['plan'])
    optimizer = request.app.state.optimizations
    with store.runs.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        state = store.broad_state(workflow_id,db)
        if state['confirmed_at_utc']:
            raise ValueError('IS Broad selection is already confirmed.')
        if state['job_id']:
            current = json.loads(db.execute('SELECT payload FROM optimizations WHERE id=?',(state['job_id'],)).fetchone()[0])
            # Repeated submissions/retries of a lost response never launch a second job.
            if state.get('preview_token') == token and current['status'] in ('queued','running','complete'):
                return current,False,None
            if current['status'] in ('queued','running'):
                raise ValueError('An IS Broad job is already running for this workflow.')
        if state['revision'] != body.revision:
            raise ValueError('IS Broad changed in another tab. Reload before starting another grid.')
        job = optimizer.create(request_body,dataset,definition,config,axes,total,
            metadata(saved['declaration']['plan'],workflow_id=workflow_id,workflow_phase='is_broad',screening_policy=policy()),connection=db)
        state = dict(job_id=job['id'],revision=state['revision']+1,selected_trials=[],selection=[],
                     confirmed_at_utc=None,preview_token=token,criterion=CRITERION,screening_policy=policy())
        db.execute('INSERT INTO campaign_broad_jobs VALUES (?,?)',(job['id'],workflow_id))
        db.execute('INSERT INTO campaign_broad_state VALUES (?,?) ON CONFLICT(workflow_id) DO UPDATE SET payload=excluded.payload',
                   (workflow_id,json.dumps(state)))
    return job,True,(definition,config,dates_for(saved['declaration']['plan']))


def state_and_job(request, workflow_id, job_id=None):
    saved,_ = request.app.state.campaign_workflows.phase(workflow_id,'is_broad')
    state = saved['broad']
    if job_id and job_id != state['job_id']:
        with request.app.state.runs.connect() as db:
            member = db.execute('SELECT 1 FROM campaign_broad_jobs WHERE workflow_id=? AND job_id=?',(workflow_id,job_id)).fetchone()
        if not member:
            raise KeyError('This IS Broad run does not belong to the campaign workflow.')
        job = request.app.state.optimizations.get(job_id)
        if not job:
            raise KeyError('Saved IS Broad run is unavailable.')
        state = dict(job_id=job_id,revision=0,selected_trials=[],selection=[],confirmed_at_utc=None,
                     screening_policy=(job.get('research') or {}).get('screening_policy'),
                     status=job['status'],archived=True)
    else:
        job = request.app.state.optimizations.get(state['job_id']) if state['job_id'] else None
    return saved,state,job


def candidate(store, workflow_id, job_id, trial, db, legacy=False, target_policy=None):
    found = db.execute('SELECT payload FROM optimization_trials WHERE optimization_id=? AND trial=?',(job_id,trial)).fetchone()
    if not found:
        raise ValueError('Selected configuration is not a member of this IS Broad job.')
    row = json.loads(found[0])
    raw = db.execute('SELECT manifest FROM runs WHERE id=?',(row['run_id'],)).fetchone()
    if not raw:
        raise ValueError('Selected backtest report is unavailable.')
    report = json.loads(raw[0]); meta=report['run_metadata'];declared=store.raw(workflow_id,db)['declaration']
    stress = None
    if not legacy:
        measured, stress = verified_screening(store.runs, report)
        if measured != row.get('screening') or not eligible(row,target_policy):
            raise ValueError('Only configurations passing the saved IS Broad selection criteria may be selected.')
    if (Decimal(str(report['summary']['total_net_pnl'])) <= 0 or
        Decimal(str(report['summary']['total_net_pnl'])) != Decimal(str(row['metrics']['total_net_pnl']))):
        raise ValueError('The selected report must have matching, positive net IS profit.')
    if (meta['strategy']['parameters'] != row['parameters'] or meta['strategy']['id'] != declared['strategy_id']
        or meta['strategy']['source_sha256'] != declared['strategy_source_sha256']
        or meta.get('research',{}).get('workflow_id') != workflow_id or meta['research'].get('workflow_phase') != 'is_broad'
        or meta['research'].get('phase') != 'is' or meta['research'].get('plan') != declared['plan']
        or report['execution_settings'] != declared['execution_settings']
        or any(meta['dataset'][k] != declared['dataset'][k] for k in ('id','sha256','source_timezone'))):
        raise ValueError('Selected report does not match the saved IS source, parameters, costs and research window.')
    evidence = [report,artifacts(store.runs.root,report)]
    if stress:
        evidence.extend([stress,artifacts(store.runs.root,stress)])
    identity = digest(evidence)
    if not legacy and identity != row.get('screening_evidence_identity'):
        raise ValueError('Native IS screening artifacts changed after publication; selection is blocked.')
    return dict(trial=trial,run_id=row['run_id'],parameters=row['parameters'],total_net_pnl=row['metrics']['total_net_pnl'],report_identity=identity)


def validate_frozen(store, workflow_id, state):
    with store.runs.connect() as db:
        if not state['confirmed_at_utc'] or not 1 <= len(state['selection']) <= 2:
            raise ValueError('Confirm one or two eligible IS Broad configurations first.')
        for frozen in state['selection']:
            if candidate(store,workflow_id,state['job_id'],frozen['trial'],db,legacy=not state.get('screening_policy'),
                         target_policy=state.get('selection_policy') or state.get('screening_policy')) != frozen:
                raise ValueError('A frozen IS Broad report changed; the selection cannot advance.')


def save_selection(request, workflow_id, body, confirm=False):
    store=request.app.state.campaign_workflows
    store.phase(workflow_id,'is_broad')
    with store.runs.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        state=store.broad_state(workflow_id,db)
        if state['confirmed_at_utc']:
            raise ValueError('Confirmed IS Broad configurations cannot be unselected or replaced.')
        if state['revision']!=body.revision or state['job_id']!=body.job_id.hex:
            raise ValueError('IS Broad selection changed. Reload before saving.')
        job=json.loads(db.execute('SELECT payload FROM optimizations WHERE id=?',(state['job_id'],)).fetchone()[0])
        count=db.execute('SELECT COUNT(*) FROM optimization_trials WHERE optimization_id=?',(job['id'],)).fetchone()[0]
        if job['status']!='complete' or count!=job['total_trials'] or count!=job['completed_trials']:
            raise ValueError('Wait for the entire IS Broad grid to complete before selecting configurations.')
        if state.get('screening_policy') not in (policy(PREVIOUS_VERSION),policy()):
            raise ValueError('This pending grid lacks measured IS Broad screening evidence. Run a new grid.')
        if (job.get('research') or {}).get('screening_policy') != state['screening_policy']:
            raise ValueError('Saved IS Broad policy differs from its optimizer job.')
        if state['screening_policy']==policy() and job['engine_identity']!=engine_identity():
            raise ValueError('Calculation code changed since this grid; run a new grid before confirming choices.')
        trials=state['selected_trials'] if confirm else body.trials
        if len(trials)!=len(set(trials)) or len(trials)>2 or (confirm and not trials):
            raise ValueError('Select one or two distinct configurations passing all five IS Broad criteria.')
        chosen=[candidate(store,workflow_id,job['id'],trial,db,target_policy=policy()) for trial in trials]
        if len({digest(c['parameters']) for c in chosen})!=len(chosen):
            raise ValueError('Selected parameter configurations must be distinct.')
        state.update(selected_trials=trials,revision=state['revision']+1,selection_policy=policy())
        if confirm:
            state.update(confirmed_at_utc=now(),selection=chosen,engine_identity=job['engine_identity'])
        db.execute('UPDATE campaign_broad_state SET payload=? WHERE workflow_id=?',(json.dumps(state),workflow_id))
    return store.get(workflow_id)['broad']


router=APIRouter()


@router.get('/api/campaign-workflow-criteria')
async def criteria():
    return dict(stages=stage_criteria())


async def invoke(function,*args,**kwargs):
    try:
        return await run_in_threadpool(function,*args,**kwargs)
    except KeyError as exc:
        raise HTTPException(404,str(exc)) from exc
    except (ValueError,TypeError,OSError) as exc:
        raise HTTPException(409,str(exc)) from exc


@router.get('/api/campaign-workflows/{workflow_id}/broad')
async def detail(workflow_id:UUID,request:Request,job_id:UUID|None=None):
    saved,state,job=await invoke(state_and_job,request,workflow_id.hex,job_id.hex if job_id else None)
    definition=get_strategy(saved['declaration']['strategy_id']).description()
    return dict(state=state,job=job,strategy=definition,max_workers=MAX_WORKERS,criterion=CRITERION,
                criteria=stage_criteria(),legacy=bool(job and not state.get('screening_policy')),
                reassessed=bool(job and state.get('screening_policy')==policy(PREVIOUS_VERSION)
                                and not state.get('archived') and
                                (not state.get('confirmed_at_utc') or state.get('selection_policy')==policy())))


@router.post('/api/campaign-workflows/{workflow_id}/broad/preview')
async def preview_grid(workflow_id:UUID,body:BroadGrid,request:Request):
    return await invoke(preview,request,workflow_id.hex,body)


@router.post('/api/campaign-workflows/{workflow_id}/broad/run',status_code=202)
async def run_grid(workflow_id:UUID,body:BroadLaunch,request:Request):
    job,fresh,context=await invoke(launch,request,workflow_id.hex,body)
    if fresh:
        definition,config,dates=context
        request.app.state.optimizations.executor.submit(request.app.state.optimizations.run,job,request.app.state.store,definition,config,dates)
    return job


@router.get('/api/campaign-workflows/{workflow_id}/broad/results')
async def results(workflow_id:UUID,request:Request,sort:str='trial',direction:str='asc',offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=1000),job_id:UUID|None=None):
    _,state,job=await invoke(state_and_job,request,workflow_id.hex,job_id.hex if job_id else None)
    if not job:
        return dict(items=[],total=0,offset=offset,limit=limit)
    page=await invoke(request.app.state.optimizations.page,job,sort,direction,offset,limit,0)
    if state.get('archived'):
        selection_policy = state.get('screening_policy')
    elif state.get('confirmed_at_utc'):
        selection_policy = state.get('selection_policy') or state.get('screening_policy')
    else:
        selection_policy = policy()
    for row in page['items']:
        row['qualifies']=eligible(row,selection_policy)
        if row.get('screening') and state.get('screening_policy')==policy(PREVIOUS_VERSION) and selection_policy==policy():
            from .workflow_criteria import evaluate
            measured=row['screening']
            row['admission']=evaluate(measured['metrics'],measured['closed_trades'],measured['total_net_pnl'],policy())
        if state['confirmed_at_utc'] and not state.get('screening_policy'):
            row['legacy_screening'] = True
            row['qualifies'] = Decimal(str(row['metrics']['total_net_pnl'])) > 0 and not row.get('backtest_deleted')
        row['selected']=row['trial'] in state['selected_trials']
        row['selectable']=row['qualifies'] and job['status']=='complete' and not state['confirmed_at_utc'] and not state.get('archived')
    return page


@router.patch('/api/campaign-workflows/{workflow_id}/broad/selection')
async def select(workflow_id:UUID,body:Selection,request:Request):
    return await invoke(save_selection,request,workflow_id.hex,body)


@router.post('/api/campaign-workflows/{workflow_id}/broad/confirm')
async def confirm(workflow_id:UUID,body:ConfirmSelection,request:Request):
    return await invoke(save_selection,request,workflow_id.hex,body,True)


@router.get('/api/campaign-workflows/{workflow_id}/broad/download')
async def download(workflow_id:UUID,request:Request,job_id:UUID|None=None):
    saved,state,job=await invoke(state_and_job,request,workflow_id.hex,job_id.hex if job_id else None)
    if state['confirmed_at_utc']:
        await invoke(validate_frozen,request.app.state.campaign_workflows,workflow_id.hex,state)
    return Response(json.dumps(dict(workflow_id=workflow_id.hex,declaration=saved['declaration'],state=state,job=job),indent=2),
                    media_type='application/json',headers={'Content-Disposition':f'attachment; filename="is-broad-{workflow_id.hex}{"-"+job_id.hex if job_id else ""}.json"'})
