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
from .robust_research import RobustResearchRequest

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
    return dict(folds=FoldSettings().model_dump(mode='json'), qualification=QualificationSettings().model_dump(mode='json'),
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
    if kind not in ('report.json', 'analysis.zip', 'qualification.csv', 'research_plan.json', 'calculations.json'):
        raise HTTPException(404, 'Unknown research download.')
    return FileResponse(request.app.state.prop_analyses.root/report['id']/kind, filename=f'{id.hex}-{kind}')
