"""Reversible workspace links; execution evidence and campaign definitions stay intact."""
from datetime import datetime, timezone
from hashlib import sha256
import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictStr
from starlette.concurrency import run_in_threadpool


def fingerprint(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


class SourceIdentity(BaseModel):
    model_config=ConfigDict(extra='forbid')
    sha256: StrictStr=Field(pattern=r'^[0-9a-f]{64}$')
    source_timezone: StrictStr=Field(min_length=1,max_length=128)
    source_kind: StrictStr=Field(default='native',pattern=r'^(native|external_trade_export)$')


class Preview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    strategy_id: StrictStr=Field(min_length=1,max_length=128)
    source: SourceIdentity



def identity(dataset):
    return dict(sha256=dataset['sha256'],source_timezone=dataset['source_timezone'],
        source_kind=dataset.get('source_kind','native'))


class CampaignDatasetLinks:
    def __init__(self,runs):
        self.runs=runs
        with runs.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS campaign_dataset_removals (
                strategy_id TEXT NOT NULL, source_key TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(strategy_id,source_key))''')

    def removed(self,strategy_id):
        with self.runs.connect() as db:
            rows=db.execute('SELECT payload FROM campaign_dataset_removals WHERE strategy_id=? ORDER BY rowid DESC',(strategy_id,)).fetchall()
        return dict(items=[json.loads(r[0]) for r in rows])

    def preview(self,strategy_id,source,db=None):
        if db is None:
            with self.runs.connect() as db:return self.preview(strategy_id,source,db)
        source=SourceIdentity.model_validate(source).model_dump()
        key=fingerprint([strategy_id,source]);workflows=[];groups=[];name=None;reports=0
        for id,raw in db.execute('SELECT id,payload FROM campaign_workflows WHERE strategy_id=?',(strategy_id,)):
            dataset=json.loads(raw)['declaration']['dataset']
            if identity(dataset)==source:workflows.append(id);name=name or dataset['name']
        for id,raw,count in db.execute('''SELECT d.id,d.payload,COUNT(r.run_id) FROM library_datasets d
                JOIN library_runs r ON r.group_id=d.id WHERE d.strategy_id=? GROUP BY d.id''',(strategy_id,)):
            dataset=json.loads(raw)['dataset']
            if identity(dataset)==source:groups.append(id);name=name or dataset['name'];reports+=count
        previous=db.execute('SELECT payload FROM campaign_dataset_removals WHERE strategy_id=? AND source_key=?',(strategy_id,key)).fetchone()
        if not workflows and not groups and not previous:raise KeyError('Campaign–dataset link not found.')
        scope=dict(strategy_id=strategy_id,source_key=key,source=source,workflow_ids=sorted(workflows),group_ids=sorted(groups))
        return dict(**scope,dataset_name=name or json.loads(previous[0])['dataset_name'],removed=bool(previous),
            retained_workflows=len(workflows),retained_reports=reports,confirmation_sha256=fingerprint(scope),
            interpretation='Remove only this dataset link from Campaigns. The campaign, dataset files, phase progress, backtests and saved reports are retained. Running jobs continue in Job history.')

    def remove_source(self,body,confirmation):
        with self.runs.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            preview=self.preview(body.strategy_id,body.source.model_dump(),db)
            if preview['removed']:
                return json.loads(db.execute('SELECT payload FROM campaign_dataset_removals WHERE strategy_id=? AND source_key=?',
                    (body.strategy_id,preview['source_key'])).fetchone()[0])
            if preview['confirmation_sha256']!=confirmation:
                raise ValueError('The linked workflows changed. Review the updated removal preview and try again.')
            receipt=dict(preview,removed=True,removed_at_utc=datetime.now(timezone.utc).isoformat())
            db.execute('INSERT INTO campaign_dataset_removals VALUES (?,?,?)',(body.strategy_id,preview['source_key'],json.dumps(receipt)))
            return receipt

    def restore(self,strategy_id,key):
        with self.runs.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            changed=db.execute('DELETE FROM campaign_dataset_removals WHERE strategy_id=? AND source_key=?',(strategy_id,key)).rowcount
        return dict(strategy_id=strategy_id,source_key=key,restored=bool(changed))

    def relink(self,strategy_id,dataset):
        return self.restore(strategy_id,fingerprint([strategy_id,identity(dataset)]))


class Remove(Preview):
    confirmation_sha256: StrictStr=Field(pattern=r'^[0-9a-f]{64}$')


router=APIRouter(prefix='/api/campaign-dataset-links',tags=['Campaign dataset links'])


async def call(request,method,*args):
    try:return await run_in_threadpool(getattr(request.app.state.campaign_dataset_links,method),*args)
    except KeyError as error:raise HTTPException(404,str(error)) from error
    except ValueError as error:raise HTTPException(409,str(error)) from error


@router.get('')
async def removed(request:Request,strategy_id:str):
    return await call(request,'removed',strategy_id)


@router.post('/preview')
async def preview(body:Preview,request:Request):
    await run_in_threadpool(request.app.state.strategy_library.browser.sync)
    return await call(request,'preview',body.strategy_id,body.source.model_dump())


@router.delete('')
async def remove(body:Remove,request:Request):
    return await call(request,'remove_source',body,body.confirmation_sha256)


@router.post('/{strategy_id}/{key}/restore')
async def restore(strategy_id:str,key:str,request:Request):
    return await call(request,'restore',strategy_id,key)
