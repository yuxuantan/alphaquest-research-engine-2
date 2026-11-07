"""Existing portal workflow, calculated locally in AlphaQuest."""
import json
import sqlite3
from uuid import UUID
from typing import Literal
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, StrictStr
from starlette.concurrency import run_in_threadpool
from .prop.native_analysis import DEFAULTS, MODEL_VERSION,model_version
from .prop.adapter import source_record
from .prop.source import matching_exports
from .prop.commissions import catalog, source_instrument
from .prop.phase_dispatch import module_for_mode
from .prop.phase_search import CandidateConfirmationRequired, require_candidate_confirmation
from .research import ResearchConflict

router = APIRouter(prefix='/api/prop-analyses', tags=['Prop analysis'])

class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_backtest_id: StrictStr = Field(pattern=r'^[0-9a-f]{32}$')
    funded_source_backtest_id: StrictStr | None = Field(default=None, pattern=r'^[0-9a-f]{32}$')
    funded_trade_file: StrictStr | None = Field(default=None, max_length=4096)
    funded_export_timezone: Literal['America/Chicago', 'America/New_York', 'UTC'] | None = None
    trade_file: StrictStr | None = Field(default=None, max_length=4096)
    export_timezone: Literal['America/Chicago', 'America/New_York', 'UTC'] = 'America/Chicago'
    settings: dict = Field(default_factory=dict)

class EvaluationSearchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['evaluation_optimization']
    source_backtest_id: StrictStr = Field(pattern=r'^[0-9a-f]{32}$')
    candidates: list[dict] = Field(min_length=1)
    confirmed_candidate_count: int | None = Field(default=None, ge=1, strict=True)
    calendar: dict
    constraints: dict | None = None

class FundedSearchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['funded_optimization']
    source_backtest_id: StrictStr = Field(pattern=r'^[0-9a-f]{32}$')
    candidates: list[dict] = Field(min_length=1)
    confirmed_candidate_count: int | None = Field(default=None, ge=1, strict=True)
    calendar: dict
    horizon_calendar_days: int = Field(strict=True)
    receipt_delay_calendar_days: int = Field(strict=True)
    constraints: dict = Field(default_factory=dict)
    bootstrap_replicates: int = Field(default=400, strict=True)
    bootstrap_seed: int = Field(default=137, strict=True)
    near_tie_cash: float = Field(default=0, strict=True)
    conservative_objective: dict | None = None

def phase_request(body):
    require_candidate_confirmation(len(body.candidates), body.confirmed_candidate_count)
    return body.model_dump(exclude={'confirmed_candidate_count'})


@router.get('/defaults')
def defaults():
    from .prop.automatic import profiles
    return dict(defaults=DEFAULTS,model_version=MODEL_VERSION,engine='AlphaQuest local calculations',commissions=catalog(),
        profiles=[dict(item,commissions=catalog(item['settings']['PROP_FIRM'])) for item in profiles()])

@router.get('/sources/{source_id}')
async def source(source_id: str, request: Request, discover_exports: bool = True):
    try:
        record=source_record(request.app.state.runs,source_id)
        if record['run_metadata'].get('source', {}).get('kind') == 'external_trade_export':
            from .trade_imports import verify_import
            from .prop.external_source import capabilities
            canonical_source = await run_in_threadpool(verify_import, request.app.state.runs, record)
            # Current admission diagnostics are separate from immutable saved bytes.
            record = {**record, 'capabilities':capabilities(canonical_source)}
        matches=await run_in_threadpool(matching_exports,request.app.state.runs,source_id) if discover_exports else []
        return dict(source=record,matched_exports=matches,analyses=request.app.state.prop_analyses.list(source_id),commission_source_instrument=source_instrument(record))
    except ValueError as exc:
        raise HTTPException(404,str(exc)) from exc

@router.post('/check')
async def check(body: AnalysisRequest | EvaluationSearchRequest | FundedSearchRequest, request: Request):
    try:
        if isinstance(body, (EvaluationSearchRequest, FundedSearchRequest)):
            module = module_for_mode(body.mode)
            search = module.parse_request(phase_request(body))
            checks = await run_in_threadpool(module.check_search, request.app.state.runs, search)
            return dict(status='compatible', mode=search.mode, candidates=checks, model_version=module.MODEL_VERSION)
        from .prop.phase_lifecycle import prepare_request, source_snapshots, dated
        snapshot,rows,settings=await run_in_threadpool(prepare_request,request.app.state.runs,body.model_dump())
        for source in source_snapshots(snapshot):
            await run_in_threadpool(request.app.state.prop_analyses.check_oos,source,settings,request.app.state.runs)
        return dict(status='compatible',source=snapshot,settings=settings,matched_trades=len(rows['evaluation']) if dated(body.model_dump()) else len(rows),model_version=model_version(settings))
    except CandidateConfirmationRequired as exc:
        raise HTTPException(409, exc.detail) from exc
    except ResearchConflict as exc:
        raise HTTPException(409,str(exc)) from exc
    except (ValueError,KeyError,OSError) as exc:
        raise HTTPException(422,str(exc)) from exc

@router.post('',status_code=202)
async def submit(body: AnalysisRequest | EvaluationSearchRequest | FundedSearchRequest, request: Request):
    try:
        if isinstance(body, (EvaluationSearchRequest, FundedSearchRequest)):
            module = module_for_mode(body.mode)
            return await run_in_threadpool(request.app.state.prop_analyses.submit_phase,
                request.app.state.runs, module.parse_request(phase_request(body)))
        return await run_in_threadpool(request.app.state.prop_analyses.submit,request.app.state.runs,body.model_dump())
    except CandidateConfirmationRequired as exc:
        raise HTTPException(409, exc.detail) from exc
    except ResearchConflict as exc:
        raise HTTPException(409,str(exc)) from exc
    except (ValueError,KeyError,OSError) as exc:
        raise HTTPException(422,str(exc)) from exc

@router.get('/{id}')
def job(id: str,request: Request):
    record=request.app.state.prop_analyses.get(id)
    if not record:
        raise HTTPException(404,'Analysis not found.')
    return {**record,**(request.app.state.prop_analyses.summary(id,record=record) or {})}

@router.get('/{id}/downloads/{kind}')
def download(id: str,kind: Literal['report.json','trades.csv','daily.csv','analysis.zip','sizing_summary.json','sizing_decisions.csv'],request: Request):
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
    return FileResponse(path,filename=None if path.suffix in ('.png','.svg') else path.name)


@router.delete('/{id}',status_code=204)
def delete_analysis(id:UUID,request:Request):
    try:deleted=request.app.state.prop_analyses.delete(id.hex)
    except ValueError as exc:raise HTTPException(409,str(exc)) from None
    except OSError as exc:raise HTTPException(500,str(exc)) from exc
    except sqlite3.Error as exc:
        raise HTTPException(500,'Could not update the prop catalogue. No deletion was committed; try again.') from exc
    if not deleted:raise HTTPException(404,'Prop analysis not found.')
