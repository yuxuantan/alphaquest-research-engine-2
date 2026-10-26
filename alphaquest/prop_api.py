"""Existing portal workflow, executed by licensed The Bridge Funded Lab."""
import json
from typing import Literal
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, StrictStr
from starlette.concurrency import run_in_threadpool
from .prop.bridge import DEFAULTS, MODEL_VERSION, prepare
from .prop.adapter import source_record
from .prop.bridge_source import matching_exports

router = APIRouter(prefix='/api/prop-analyses', tags=['Prop analysis'])

class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_backtest_id: StrictStr = Field(pattern=r'^[0-9a-f]{32}$')
    trade_file: StrictStr | None = Field(default=None, max_length=4096)
    export_timezone: Literal['America/Chicago', 'America/New_York', 'UTC'] = 'America/Chicago'
    settings: dict = Field(default_factory=dict)

@router.get('/defaults')
def defaults():
    return dict(defaults=DEFAULTS,model_version=MODEL_VERSION,engine='The Bridge Funded Lab; running Windows VM and active license required')

@router.get('/sources/{source_id}')
async def source(source_id: str, request: Request):
    try:
        record=source_record(request.app.state.runs,source_id)
        matches=await run_in_threadpool(matching_exports,request.app.state.runs,source_id)
        return dict(source=record,matched_exports=matches,analyses=request.app.state.prop_analyses.list(source_id))
    except ValueError as exc:
        raise HTTPException(404,str(exc)) from exc

@router.post('/check')
async def check(body: AnalysisRequest, request: Request):
    try:
        snapshot,rows,settings=await run_in_threadpool(prepare,request.app.state.runs,body.source_backtest_id,body.trade_file,body.settings,body.export_timezone)
        return dict(status='compatible',source=snapshot,settings=settings,matched_trades=len(rows),model_version=MODEL_VERSION)
    except (ValueError,KeyError,OSError) as exc:
        raise HTTPException(422,str(exc)) from exc

@router.post('',status_code=202)
async def submit(body: AnalysisRequest, request: Request):
    try:
        return await run_in_threadpool(request.app.state.prop_analyses.submit,request.app.state.runs,body.model_dump())
    except (ValueError,KeyError,OSError) as exc:
        raise HTTPException(422,str(exc)) from exc

@router.get('/{id}')
def job(id: str,request: Request):
    record=request.app.state.prop_analyses.get(id)
    if not record:
        raise HTTPException(404,'Analysis not found.')
    return record

@router.get('/{id}/downloads/{kind}')
def download(id: str,kind: Literal['report.json','trades.csv','daily.csv','analysis.zip'],request: Request):
    record=job(id,request)
    if record['status']!='complete':
        raise HTTPException(409,'Operation has not published a completed report.')
    path=request.app.state.prop_analyses.root/id/kind
    if not path.is_file():raise HTTPException(404,'This report has no such export; inspect its saved file list.')
    return FileResponse(path,filename=f'{id}-{kind}')

@router.get('/{id}/files/{name:path}')
def file(id: str,name: str,request: Request):
    record=job(id,request)
    if record['status']!='complete':raise HTTPException(409,'Operation has not completed.')
    root=request.app.state.prop_analyses.root/id
    report=json.loads((root/'report.json').read_text())
    if name not in report.get('files',{}):raise HTTPException(404,'File is not a captured result artifact.')
    path=(root/name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():raise HTTPException(404,'Invalid artifact path.')
    return FileResponse(path,filename=None if path.suffix=='.png' else path.name)
