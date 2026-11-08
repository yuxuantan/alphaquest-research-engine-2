"""Nested research within the existing campaign API and report catalogue."""
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from starlette.concurrency import run_in_threadpool

from .edge_qualification import QualificationSettings
from .execution_scenarios import ExecutionScenario
from .prop.adapter import canonical
from .research import ResearchConflict
from .research_folds import FoldSettings
from .research_regimes import RegimeSettings
from .research_reliability import ReliabilitySettings
from .research_procedure import TerminalSelection, FinalEvidenceRules
from .robust_research import RobustResearchRequest
from .research_phase_selection import study_defaults

router = APIRouter(prefix='/api/research-campaigns/robust', tags=['Research campaigns'])


async def call(request, method, *args):
    try:
        return await run_in_threadpool(getattr(request.app.state.robust_research, method), *args)
    except ResearchConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ValueError, TypeError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get('/defaults')
def defaults():
    return dict(**study_defaults(),terminal_selection=TerminalSelection().model_dump(mode='json'),final_evidence=FinalEvidenceRules().model_dump(mode='json'), reliability=ReliabilitySettings().model_dump(mode='json'), folds=FoldSettings().model_dump(mode='json'), qualification=QualificationSettings().model_dump(mode='json'),
        execution_scenario=ExecutionScenario(name='cost_stress').model_dump(mode='json'),
        regimes=RegimeSettings().model_dump(mode='json'), regime_names={
            'trend':'Trending prior prices', 'range':'Ranging prior prices',
            'high_volatility':'High prior volatility', 'low_volatility':'Low prior volatility',
            'high_liquidity':'High prior volume (liquidity proxy)', 'low_liquidity':'Low prior volume (liquidity proxy)',
            'asia_session':'Asia clock window', 'europe_session':'Europe clock window', 'us_session':'US clock window'})


@router.post('/preview')
async def preview(body: RobustResearchRequest, request: Request):
    return await call(request, 'preview', body)


@router.post('', status_code=201)
async def create(body: RobustResearchRequest, request: Request):
    return await call(request, 'create', body)


@router.get('')
async def history(request: Request, source_id: str | None = Query(default=None, pattern=r'^[0-9a-f]{32}$')):
    return dict(items=await call(request, 'list', source_id))


@router.get('/{id}')
async def status(id: UUID, request: Request):
    return await call(request, 'get', id.hex)


@router.post('/{id}/check')
async def check(id: UUID, request: Request):
    return await call(request, 'check', id.hex)


@router.post('/{id}/run', status_code=202)
async def run(id: UUID, request: Request):
    return await call(request, 'run', id.hex)


@router.post('/{id}/cancel')
async def cancel(id: UUID, request: Request):
    return await call(request, 'cancel', id.hex)


@router.get('/{id}/exports/{kind}')
async def export(id: UUID, kind: str, request: Request):
    if kind == 'campaign.json':
        value = await call(request, 'get', id.hex)
        return Response(canonical(value), media_type='application/json',
                        headers={'Content-Disposition':f'attachment; filename="{id.hex}-{kind}"'})
    report = await call(request, 'report', id.hex)
    if kind not in ('report.json', 'analysis.zip', 'qualification.csv', 'research_plan.json', 'calculations.json', 'economic_selection.json', 'chronological_replay.json', 'research_journal.json', 'baseline_results.json', 'reliability.json', 'reliability_folds.csv', 'baseline_comparison.csv'):
        raise HTTPException(404, 'Unknown research download.')
    path=request.app.state.prop_analyses.root/report['id']/kind
    if not path.is_file():
        raise HTTPException(404, 'This saved research report does not contain this artifact.')
    return FileResponse(path, filename=f'{id.hex}-{kind}')


from pydantic import BaseModel, ConfigDict, Field


class ProcedurePreviewRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    reservation_id:str|None=Field(default=None,pattern=r'^[0-9a-f]{32}$')
    source_snapshot_id:str|None=None


class ProcedureFreezeRequest(ProcedurePreviewRequest):
    procedure_id:str=Field(pattern=r'^[0-9a-f]{32}$')
    expected_preview_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')


class FinalPreviewRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    procedure_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
    reservation_id:str=Field(pattern=r'^[0-9a-f]{32}$')
    source_snapshot_id:str


class FinalRunRequest(FinalPreviewRequest):
    request_id:str=Field(pattern=r'^[0-9a-f]{32}$')
    expected_preview_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')


class DevelopmentRunRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    request_id:str=Field(pattern=r'^[0-9a-f]{32}$')
    procedure_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')


@router.post('/{id}/procedure/preview')
async def procedure_preview(id:UUID,body:ProcedurePreviewRequest,request:Request):
    return await call(request,'procedure_preview',id.hex,body.model_dump(mode='json'))


@router.post('/{id}/procedure/freeze',status_code=201)
async def procedure_freeze(id:UUID,body:ProcedureFreezeRequest,request:Request):
    return await call(request,'procedure_freeze',id.hex,body.model_dump(mode='json'))


@router.post('/{id}/final-verification/preview')
async def final_preview(id:UUID,body:FinalPreviewRequest,request:Request):
    return await call(request,'final_preview',id.hex,body.model_dump(mode='json'))


@router.post('/{id}/final-verification/run',status_code=202)
async def final_run(id:UUID,body:FinalRunRequest,request:Request):
    return await call(request,'run_application',id.hex,body.model_dump(mode='json'),'final_verification')


@router.post('/{id}/development-selection/run',status_code=202)
async def development_run(id:UUID,body:DevelopmentRunRequest,request:Request):
    return await call(request,'run_application',id.hex,body.model_dump(mode='json'),'current_development')


@router.get('/{id}/applications/{application_id}')
async def application(id:UUID,application_id:UUID,request:Request):
    return await call(request,'application',id.hex,application_id.hex)


@router.post('/{id}/applications/{application_id}/cancel')
async def cancel_application(id:UUID,application_id:UUID,request:Request):
    return await call(request,'cancel_application',id.hex,application_id.hex)


@router.get('/{id}/applications/{application_id}/exports/{kind}')
async def application_export(id:UUID,application_id:UUID,kind:str,request:Request):
    report=await call(request,'application_report',id.hex,application_id.hex)
    if kind not in ('report.json','analysis.zip','procedure.json','terminal_plan.json','qualification.json','economic_selection.json',
                    'baseline_results.json','final_verification.json','recommendation.json','research_journal.json','access_evidence.json','calculations.json'):
        raise HTTPException(404,'Unknown procedure application download.')
    path=request.app.state.prop_analyses.root/report['id']/kind
    if not path.is_file():raise HTTPException(404,'Saved application does not contain this artifact.')
    return FileResponse(path,filename=f'{application_id.hex}-{kind}')
