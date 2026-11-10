"""Read-only, paged job history over the existing execution catalogues."""
import json
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool

JobKind = Literal['mechanic_validation', 'backtest_batch', 'backtest', 'prop_analysis']
JobFilter = Literal['all', 'active', 'completed', 'attention']

# Only metadata is queried. Numerical reports stay in their existing stores.
SOURCES = '''
 SELECT 'mechanic_validation' AS kind,j.id,j.recorded_at AS recorded_at_utc,j.status,
        w.strategy_id,COALESCE(json_extract(w.payload,'$.declaration.dataset.name'),'Unavailable source') AS dataset_name,
        json_object('workflow_id',j.workflow_id,'started_at',j.started_at,'finished_at',j.finished_at,
                    'error',j.error,'total_bars',COALESCE(j.total_bars,json_extract(r.manifest,'$.run_metadata.selection.row_count')),
                    'report_available',r.id IS NOT NULL,'current_run_id',json_extract(w.payload,'$.run_id'),
                    'review_status',json_extract(w.payload,'$.status')) AS payload
 FROM mechanic_job_attempts j JOIN campaign_workflows w ON w.id=j.workflow_id LEFT JOIN runs r ON r.id=j.id
 UNION ALL
 SELECT 'backtest_batch',id,created_at,
        CASE json_extract(payload,'$.status') WHEN 'error' THEN 'failed' ELSE json_extract(payload,'$.status') END,
        json_extract(payload,'$.strategy.id'),json_extract(payload,'$.dataset.name'),payload FROM optimizations
 UNION ALL
 SELECT 'backtest',r.id,r.created_at,'complete',json_extract(r.manifest,'$.run_metadata.strategy.id'),
        json_extract(r.manifest,'$.run_metadata.dataset.name'),r.manifest FROM runs r
 WHERE NOT EXISTS (SELECT 1 FROM mechanic_job_attempts j WHERE j.id=r.id)
   AND NOT EXISTS (SELECT 1 FROM optimization_trials t WHERE json_extract(t.payload,'$.run_id')=r.id)
   AND COALESCE(json_extract(r.manifest,'$.run_metadata.research.workflow_phase'),'') NOT IN ('is_broad_cost_stress','is_narrow_cost_stress')
 UNION ALL
 SELECT 'prop_analysis',a.id,a.created,CASE a.status WHEN 'error' THEN 'failed' ELSE a.status END,
        COALESCE(json_extract(r.manifest,'$.run_metadata.strategy.id'),''),
        COALESCE(json_extract(r.manifest,'$.run_metadata.dataset.name'),'Saved source '||a.source_id),
        json_object('progress',a.progress,'error',a.error,'source_id',a.source_id)
 FROM prop_catalog.analyses a LEFT JOIN runs r ON r.id=a.source_id
'''


def public_job(row, tracker):
    kind, id, recorded, status, strategy, dataset, raw = row
    payload = json.loads(raw)
    result = dict(id=id, kind=kind, recorded_at_utc=recorded, status=status,
                  strategy_id=strategy, dataset_name=dataset, started_at_utc=None, finished_at_utc=None,
                  error=payload.get('error'), progress=None, links=[])
    result['href'] = f'#jobs/{kind}/{id}'
    links = result['links']
    if kind == 'mechanic_validation':
        result.update(workflow_id=payload['workflow_id'], review_status=payload['review_status'],
                      started_at_utc=payload['started_at'], finished_at_utc=payload['finished_at'])
        links.append(dict(label='Open mechanic validation' if payload['current_run_id']==id else 'Open current mechanic workflow',
                          href=f"#campaigns/workflows/{payload['workflow_id']}/mechanic_validation"))
        if payload['report_available']:
            links.append(dict(label='Open backtest report', href=f'#backtests/report/{id}'))
        progress = tracker.get(str(UUID(id))) if status == 'running' else None
        result['progress'] = dict(stage=progress['stage'], completed=progress.get('bars_processed'), total=progress.get('total_bars'), unit='bars') if progress else dict(
            stage=status, completed=payload['total_bars'] if status == 'complete' else None, total=payload['total_bars'], unit='bars')
    elif kind == 'backtest_batch':
        result.update(started_at_utc=payload.get('started_at_utc'),finished_at_utc=payload.get('finished_at_utc'))
        result['progress'] = dict(stage=payload.get('stage',status),completed=payload.get('completed_trials'),total=payload.get('total_trials'),unit='trials')
        research = payload.get('research') or {}
        if research.get('workflow_phase') == 'is_broad' and research.get('workflow_id'):
            result['phase'] = 'is_broad'
            links.append(dict(label='Open IS Broad',href=f"#campaigns/workflows/{research['workflow_id']}/is_broad?job={id}"))
        elif research.get('workflow_phase') == 'is_narrow' and research.get('workflow_id'):
            result['phase'] = 'is_narrow'
            links.append(dict(label='Open IS Narrow',href=f"#campaigns/workflows/{research['workflow_id']}/is_narrow?broad_trial={research['broad_trial']}"))
        else:
            links.append(dict(label='Open batch progress / results',href=f'#backtests/batches/{id}'))
    elif kind == 'backtest':
        # Creation time is publication time; old reports do not record start time.
        result['progress'] = dict(stage='complete',completed=payload['summary']['trades_taken'],total=None,unit='trades')
        links.append(dict(label='Open backtest report',href=f'#backtests/report/{id}'))
    else:
        result['progress'] = dict(stage=payload.get('progress') or status,completed=None,total=None,unit=None)
        links.append(dict(label='Open prop analysis',href=f'#backtests/prop/job/{id}'))
    return result


def history(request, *, status='all', kind='all', q='', offset=0, limit=25, id=None):
    states = {'all':None,'active':('queued','running'),'completed':('complete',),'attention':('failed','interrupted','cancelled','deleting')}
    where, params = [], []
    if states[status]:
        where.append('status IN ('+','.join('?' for _ in states[status])+')');params.extend(states[status])
    if kind != 'all':
        where.append('kind=?');params.append(kind)
    if id:
        where.append('id=?');params.append(id)
    if q:
        where.append("instr(lower(COALESCE(strategy_id,'')||' '||COALESCE(dataset_name,'')||' '||id),lower(?))>0");params.append(q)
    query = 'SELECT * FROM ('+SOURCES+')'+(' WHERE '+' AND '.join(where) if where else '')
    with request.app.state.runs.connect() as db:
        db.execute('ATTACH DATABASE ? AS prop_catalog',(str(request.app.state.prop_analyses.path),))
        db.execute('BEGIN')
        total = db.execute('SELECT COUNT(*) FROM ('+query+')',params).fetchone()[0]
        rows = db.execute(query+' ORDER BY recorded_at_utc DESC,kind,id LIMIT ? OFFSET ?',(*params,limit,offset)).fetchall()
    return dict(items=[public_job(row,request.app.state.progress) for row in rows],total=total,offset=offset,limit=limit)


router = APIRouter()


@router.get('/api/jobs')
async def list_jobs(request: Request, status: JobFilter='all', kind: Literal['all','mechanic_validation','backtest_batch','backtest','prop_analysis']='all',
                    q: str=Query('',max_length=200),offset: int=Query(0,ge=0),limit: int=Query(25,ge=1,le=100)):
    return await run_in_threadpool(history,request,status=status,kind=kind,q=q,offset=offset,limit=limit)


@router.get('/api/jobs/{kind}/{job_id}')
async def job(kind: JobKind, job_id: UUID, request: Request):
    result = await run_in_threadpool(history,request,kind=kind,id=job_id.hex)
    if not result['items']:
        raise HTTPException(404,'Job not found. Its original activity or report may have been deleted.')
    return result['items'][0]
