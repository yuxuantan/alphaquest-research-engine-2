"""Phase campaigns use normal phase calculations, reports, security and workers."""
from uuid import UUID, uuid5
from typing import Literal
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from starlette.concurrency import run_in_threadpool
from .research import ResearchConflict
from .research_campaigns import CampaignRequest, FreezeRequest, AssessmentRequest, SourceWindowRequest
from .prop.adapter import canonical
from .prop.phase_search import CandidateConfirmationRequired

router = APIRouter(prefix='/api/research-campaigns', tags=['Research campaigns'])


async def call(request, method, *args):
    try:
        return await run_in_threadpool(getattr(request.app.state.campaigns, method), *args)
    except CandidateConfirmationRequired as exc:
        raise HTTPException(409, exc.detail) from exc
    except ResearchConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ValueError, TypeError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post('', status_code=201)
async def create(body: CampaignRequest, request: Request):
    return await call(request, 'create', body)


@router.get('')
async def history(request: Request, source_id: str | None = Query(default=None, pattern=r'^[0-9a-f]{32}$'),
                  limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)):
    return dict(items=await call(request, 'list', source_id, limit, offset))


@router.get('/defaults')
def defaults():
    from .prop.phase_profiles import rule_version
    return dict(profiles={name:rule_version(name) for name in ('apex-50k-eod', 'lucidflex-50k')})


@router.get('/sources')
async def sources(request: Request, kind: Literal['backtest_id', 'optimization_id'],
                  q: str = Query(default='', max_length=200), offset: int = Query(default=0, ge=0),
                  limit: int = Query(default=50, ge=1, le=100)):
    return await call(request, 'sources', kind, q, offset, limit)


@router.post('/source-window')
async def source_window(body: SourceWindowRequest, request: Request):
    return await call(request, 'source_window', body)


@router.get('/{id}')
async def status(id: UUID, request: Request):
    return await call(request, 'get', id.hex)


@router.post('/{id}/check')
async def check(id: UUID, request: Request):
    return await call(request, 'validate', id.hex)


@router.post('/{id}/run', status_code=202)
async def run(id: UUID, request: Request):
    return await call(request, 'run', id.hex)


@router.get('/{id}/candidates')
async def candidates(id: UUID, request: Request):
    report = await call(request, 'report', id.hex)
    return dict(analysis_id=report['id'], candidates=report['calculations']['candidates'])


@router.get('/{id}/attempts')
async def attempts(id: UUID, request: Request):
    return dict(items=await call(request, 'attempts', id.hex))


@router.get('/{id}/selection')
async def selection(id: UUID, request: Request):
    report = await call(request, 'report', id.hex)
    return {k:v for k,v in report['calculations'].items() if k != 'candidates'}


@router.post('/{id}/freeze')
async def freeze(id: UUID, body: FreezeRequest, request: Request):
    return await call(request, 'freeze', id.hex, body)


@router.get('/{id}/assessments')
async def assessments(id: UUID, request: Request):
    return dict(items=await call(request, 'assessments', id.hex))


@router.post('/{id}/assessments', status_code=202)
async def assess(id: UUID, body: AssessmentRequest, request: Request):
    from .research_api import run_oos, OOSRequest
    attempt, fresh = await call(request, 'begin_assessment', id.hex, body.request_id)
    if not fresh:
        return attempt
    sources = {}
    try:
        for parent in attempt['parent_source_ids']:
            # The existing manual OOS path enforces dataset/strategy/parameter/
            # execution identity and records unlimited prior-access attempts.
            result = await run_oos(UUID(parent), OOSRequest(request_id=uuid5(UUID(body.request_id), parent)), request)
            if not isinstance(result, dict):
                import json
                result = json.loads(result.body)
            if not result.get('id'):
                raise ResearchConflict('The ordinary OOS backtest did not complete; inspect saved OOS attempts.')
            sources[parent] = result['id']
            attempt['oos_sources'] = dict(sources)
            await call(request, 'save_assessment', attempt)
        return await call(request, 'finish_assessment', id.hex, attempt, sources)
    except Exception as exc:
        await call(request, 'save_assessment', dict(attempt, status='error', error=str(exc)))
        raise


@router.get('/{id}/exports/{kind}')
async def export(id: UUID, kind: str, request: Request):
    row = await call(request, 'get', id.hex)
    if kind in ('campaign.json', 'frozen_package.json'):
        value = row if kind == 'campaign.json' else row['frozen']
        if value is None:
            raise HTTPException(409, 'Campaign has not been frozen.')
        return Response(canonical(value), media_type='application/json',
            headers={'Content-Disposition': f'attachment; filename="{id.hex}-{kind}"'})
    report = await call(request, 'report', id.hex)
    files = {'results.json':'calculations.json', 'results.csv':'phase_metrics.csv',
             'analysis.zip':'analysis.zip', 'report.json':'report.json', 'source_checks.json':'source_checks.json'}
    name = files.get(kind)
    if name is None or (name not in report['files'] and name not in ('analysis.zip', 'report.json')):
        raise HTTPException(404, 'Unknown campaign export.')
    return FileResponse(request.app.state.prop_analyses.root/report['id']/name, filename=f'{id.hex}-{kind}')
