"""HTTP validation/orchestration for notebook-compatible analysis."""
from typing import Literal
from fastapi import APIRouter,Request,HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel,ConfigDict,Field,StrictStr
from .prop.analysis import AVAILABLE_INCREMENT,prepare
from .prop.adapter import source_record
from .prop.settings import DEFAULTS,PRESETS,NOTEBOOK_SHA256
from starlette.concurrency import run_in_threadpool

router=APIRouter(prefix='/api/prop-analyses',tags=['Prop analysis'])

class AnalysisRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    source_backtest_id:StrictStr=Field(pattern=r'^[0-9a-f]{32}$')
    overrides:dict=Field(default_factory=dict)
    preset:Literal['source','notebook']='source'
    pricing:Literal['notebook','49+129','109+0']='notebook'
    increment:int=Field(default=AVAILABLE_INCREMENT,ge=1,le=AVAILABLE_INCREMENT,strict=True)

@router.get('/defaults')
def defaults():return dict(defaults=DEFAULTS,pricing=PRESETS,notebook_sha256=NOTEBOOK_SHA256,available_increment=AVAILABLE_INCREMENT)

@router.get('/sources/{source_id}')
def source(source_id:str,request:Request):
    try:return dict(source=source_record(request.app.state.runs,source_id),analyses=request.app.state.prop_analyses.list(source_id))
    except ValueError as exc:raise HTTPException(404,str(exc)) from exc

@router.post('/check')
async def check(body:AnalysisRequest,request:Request):
    try:
        frame,snapshot,settings,origins=await run_in_threadpool(prepare,request.app.state.runs,body.source_backtest_id,body.overrides,body.preset,body.pricing)
        return dict(status='compatible',source=snapshot,settings=settings,setting_origins=origins,weekday_input_trades=len(frame),requested_engine=settings['ENGINE'],effective_engine='trade' if settings['ENGINE']=='excursion' else settings['ENGINE'])
    except (ValueError,KeyError,FileNotFoundError) as exc:raise HTTPException(422,str(exc)) from exc

@router.post('',status_code=202)
async def submit(body:AnalysisRequest,request:Request):
    try:return await run_in_threadpool(request.app.state.prop_analyses.submit,request.app.state.runs,body.model_dump())
    except (ValueError,KeyError,FileNotFoundError) as exc:raise HTTPException(422,str(exc)) from exc

@router.get('/{id}')
def job(id:str,request:Request):
    record=request.app.state.prop_analyses.get(id)
    if not record:raise HTTPException(404,'Analysis not found.')
    return record

@router.get('/{id}/downloads/{kind}')
def download(id:str,kind:Literal['report.json','trades.csv','daily.csv','analysis.zip'],request:Request):
    record=job(id,request)
    if record['status']!='complete':raise HTTPException(409,'Operation has not published a completed report.')
    return FileResponse(request.app.state.prop_analyses.root/id/kind,filename=f'{id}-{kind}')
