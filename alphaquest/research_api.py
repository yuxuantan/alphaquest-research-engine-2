"""Shared split declaration and explicit, selected-parameter holdout execution."""
from uuid import UUID
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, StrictStr
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from .backtest_requests import ExecutionSettings
from .research import SplitDeclaration,ResearchConflict,dates_for,metadata
from .strategies.registry import get_strategy
from .datasets import COLUMNS

router=APIRouter()


class PreviewRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    dataset_id:StrictStr
    strategy_id:StrictStr
    sample_split:SplitDeclaration


class OOSRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id:UUID


def source(request,dataset_id,strategy_id):
    try:get_strategy(strategy_id)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    dataset=request.app.state.store.get(dataset_id)
    if not dataset:raise HTTPException(404,'Dataset not found.')
    if dataset.get('columns')!=COLUMNS:raise HTTPException(422,'Unsupported dataset schema.')
    return dataset


@router.get('/api/backtests/research-plan')
def status(request:Request,dataset_id:str,strategy_id:str):
    return request.app.state.research.status(source(request,dataset_id,strategy_id),strategy_id)


@router.post('/api/backtests/research-plan/preview')
def preview(body:PreviewRequest,request:Request):
    dataset=source(request,body.dataset_id,body.strategy_id)
    try:plan=request.app.state.research.resolve(request.app.state.store,dataset,body.strategy_id,body.sample_split)
    except ResearchConflict as exc:raise HTTPException(409,str(exc)) from None
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    return dict(**request.app.state.research.status(dataset,body.strategy_id),proposed_plan=plan)


def selected(request,run_id):
    record=request.app.state.runs.get(run_id.hex)
    if not record:raise HTTPException(404,'Completed backtest not found.')
    research=record['run_metadata'].get('research')
    if not research or research['phase']!='is':
        raise HTTPException(409,'Select a declared IS backtest or an individual IS optimisation trial. Legacy and OOS reports cannot launch OOS tests.')
    return record,research['plan']


@router.get('/api/backtests/{run_id}/oos')
def selected_status(run_id:UUID,request:Request):
    record=request.app.state.runs.get(run_id.hex)
    if not record:raise HTTPException(404,'Completed backtest not found.')
    research=record['run_metadata'].get('research')
    if not research:raise HTTPException(409,'This legacy report has no IS/OOS declaration.')
    plan=research['plan']
    return dict(request.app.state.research.status(dict(sha256=plan['source_sha256']),plan['strategy_id']),
                plan=plan,selected_run_id=record['id'],parameters=record['run_metadata']['strategy']['parameters'])


@router.post('/api/backtests/{run_id}/oos',status_code=201)
async def run_oos(run_id:UUID,body:OOSRequest,request:Request,progress_id:UUID|None=None):
    from .backtest_api import execute_backtest
    record,plan=await run_in_threadpool(selected,request,run_id)
    saved=record['run_metadata']
    dataset=await run_in_threadpool(source,request,saved['dataset']['id'],plan['strategy_id'])
    try:
        if any(dataset[k]!=saved['dataset'][k] for k in ('sha256','source_timezone','row_count')):
            raise ValueError('The dataset no longer matches the selected IS report.')
        definition=get_strategy(plan['strategy_id'])
        if definition.description()['source_sha256']!=saved['strategy']['source_sha256']:
            raise ValueError('Strategy source changed. OOS requires the original selected strategy implementation.')
        parameters=definition.parameters(saved['strategy']['parameters'])
        config=ExecutionSettings.model_validate(record['execution_settings']).execution_config(dataset)
        attempt,fresh=await run_in_threadpool(request.app.state.research.reserve,plan,record['id'],str(body.request_id))
    except ResearchConflict as exc:raise HTTPException(409,str(exc)) from None
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    if not fresh:
        existing=await run_in_threadpool(request.app.state.runs.get,attempt['run_id'])
        if existing:return JSONResponse(existing,status_code=200)
        return JSONResponse(dict(attempt=attempt,**request.app.state.research.status(dataset,plan['strategy_id'])),status_code=202 if attempt['status']=='running' else 409)
    try:
        result=await execute_backtest(request,dataset,definition,parameters,config,dates_for(plan,'oos'),progress_id,
                                      reuse_results=False,reuse_calculations=False,
                                      research=metadata(plan,'oos',parent_run_id=record['id'],attempt_id=attempt['id'],attempt_number=attempt['number']),
                                      run_id_override=attempt['run_id'])
        await run_in_threadpool(request.app.state.research.finish,attempt['id'],'complete')
        return result
    except BaseException as exc:
        await run_in_threadpool(request.app.state.research.finish,attempt['id'],'failed',str(exc))
        raise
