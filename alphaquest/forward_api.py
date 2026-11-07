"""ordinary product API; no demo endpoints or order-placement capability."""
from fastapi import APIRouter,HTTPException,Request,Response
from fastapi.responses import JSONResponse
from .forward_contracts import MonitorDeclaration,EventBatch,Assessment,Control,Thresholds
from .forward_monitoring import Conflict

router=APIRouter(prefix='/api/forward-monitors',tags=['forward observation'])


def owner(request):return request.app.state.forward_monitors


def call(function,*args,**kwargs):
    try:return function(*args,**kwargs)
    except KeyError as exc:raise HTTPException(404,str(exc)) from exc
    except Conflict as exc:raise HTTPException(409,str(exc)) from exc
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc


@router.get('/defaults')
def defaults():
    return dict(schema_version='aq-forward-monitor-v1',thresholds=Thresholds().model_dump(mode='json'),
        observation_kinds=['synthetic_harness','paper','actual_import'],control_mode='advisory_only',
        order_placement_enabled=False,accepted_event_schema=EventBatch.model_json_schema(),
        monitor_schema=MonitorDeclaration.model_json_schema(),limits=dict(batch_bytes=4*1024*1024,batch_events=5000,monitor_events=100000),
        limitations=['Incoming observations are supplied records; no direct broker or market-data connection is verified.',
            'Synthetic observations remain separate from paper and actual-import evidence.'])


@router.post('/check')
def check(body:MonitorDeclaration,request:Request):return call(owner(request).check,body)


@router.post('')
def create(body:MonitorDeclaration,request:Request):
    value,created=call(owner(request).create,body)
    return JSONResponse(value,status_code=201 if created else 200)


@router.get('')
def monitors(request:Request,application_id:str|None=None,limit:int=50,offset:int=0,q:str=''):
    return call(owner(request).list,application_id=application_id,limit=limit,offset=offset,q=q)


@router.get('/{id}')
def monitor(id:str,request:Request):return call(owner(request).get,id)


async def raw_body(request):
    data=bytearray()
    async for piece in request.stream():
        data.extend(piece)
        if len(data)>4*1024*1024:raise HTTPException(413,'Event batch exceeds the 4 MiB input limit.')
    return bytes(data)


@router.post('/{id}/events/check')
async def check_events(id:str,request:Request,filename:str='events.json'):
    return call(owner(request).check_events,id,await raw_body(request),filename=filename)


@router.post('/{id}/events')
async def events(id:str,request:Request,filename:str='events.json'):
    value=call(owner(request).append,id,await raw_body(request),filename=filename)
    return JSONResponse(value,status_code=200 if value['existing_batch'] else 201)


@router.get('/{id}/events')
def event_history(id:str,request:Request,offset:int=0,limit:int=100):
    return call(owner(request).events,id,offset=offset,limit=limit)


@router.post('/{id}/assess')
def assess(id:str,body:Assessment,request:Request):return call(owner(request).submit,id,body)


@router.post('/{id}/control')
def control(id:str,body:Control,request:Request):return call(owner(request).control,id,body)


@router.get('/{id}/snapshots')
def snapshots(id:str,request:Request):return call(owner(request).snapshots,id)


@router.get('/{id}/batches')
def batches(id:str,request:Request):return call(owner(request).batches,id)


@router.get('/{id}/batches/{batch_id}/download')
def original_batch(id:str,batch_id:str,request:Request):
    value=call(owner(request).raw_batch,id,batch_id)
    return Response(value,media_type='application/json',headers={'Content-Disposition':'attachment; filename="source-events.json"'})


@router.get('/{id}/exports/{kind}')
def export(id:str,kind:str,request:Request):
    value=call(owner(request).export,id,kind)
    return Response(value,media_type='application/x-ndjson' if kind.endswith('.jsonl') else 'application/json',
        headers={'Content-Disposition':'attachment; filename="'+kind+'"'})
