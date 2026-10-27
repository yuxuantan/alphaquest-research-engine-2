"""Adapt existing execution oracles to a declared IS with a synthetic holdout.

The original fixture rows remain the complete IS oracle, byte/price values intact.
One explicitly synthetic reserved date is appended for tests that are concerned
with fills/reporting rather than holdout policy. Requests still pass through the
real required declaration, source checks and permanent-plan enforcement. New
research-policy tests use ordinary clients and their own IS/OOS datasets.
"""
import csv
from datetime import datetime,timedelta
from hashlib import sha256
import io
import json

import httpx
from fastapi.testclient import TestClient

SPLITS={}
_sources={}


def reserved_source(raw):
    if isinstance(raw,str):raw=raw.encode()
    if not isinstance(raw,bytes):return raw,None
    identity=sha256(raw).hexdigest()
    if identity in _sources:return raw,_sources[identity]
    try:
        rows=list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
        if rows[0]!=['Date','Time','Open','High','Low','Close','Volume','UpVol','DownVol']:return raw,None
        days=sorted({datetime.strptime(r[0],'%m/%d/%Y').date() for r in rows[1:]})
        reserved=days[-1]+timedelta(days=1)
        while reserved.weekday()>4:reserved+=timedelta(days=1)
        extra=[reserved.strftime('%m/%d/%Y'),*rows[-1][1:]]
        buffer=io.StringIO(newline='');csv.writer(buffer,lineterminator='\n').writerow(extra)
        data=raw.rstrip(b'\r\n')+b'\n'+buffer.getvalue().encode()
        split=dict(mode='dates',is_start=days[0].isoformat(),is_end=days[-1].isoformat(),oos_start=reserved.isoformat(),oos_end=reserved.isoformat())
        _sources[sha256(data).hexdigest()]=split
        return data,split
    except (ValueError,UnicodeDecodeError,IndexError,csv.Error):return raw,None


def register(dataset,split):
    if split:SPLITS[dataset['id']]=split


def declaration(id):
    return dict(SPLITS.get(id,dict(mode='dates',is_start='2026-01-05',is_end='2026-01-05',oos_start='2026-01-06',oos_end='2026-01-06')))


class FixtureRequests:
    def post(self,url,**kwargs):
        path=str(url).split('?')[0].rstrip('/')
        split=None
        if path.endswith('/api/datasets') and isinstance(kwargs.get('content'),(bytes,str)):
            kwargs['content'],split=reserved_source(kwargs['content'])
        if path.endswith(('/api/backtests','/api/optimizations')) and 'json' in kwargs:
            body=dict(kwargs['json'])
            if 'sample_split' not in body or 'from_date' in body or 'to_date' in body:
                sample=dict(body.get('sample_split') or declaration(body.get('dataset_id')))
                for old,new in (('from_date','is_start'),('to_date','is_end')):
                    if old in body:
                        value=body.pop(old)
                        if value is not None:sample[new]=value
                # Open bounds historically meant all available source dates.
                # Clamp only syntactically valid encompassing bounds.
                original=declaration(body.get('dataset_id'))
                for key in ('is_start','is_end'):
                    value=sample[key]
                    if isinstance(value,str) and len(value)==10:
                        try:datetime.strptime(value,'%Y-%m-%d')
                        except ValueError:continue
                        if key=='is_start' and value<original[key]:sample[key]=original[key]
                        if key=='is_end' and value>original[key]:sample[key]=original[key]
                body['sample_split']=sample
            kwargs['json']=body
        response=super().post(url,**kwargs)
        if split and response.status_code==201:register(response.json(),split)
        return response


class ResearchClient(FixtureRequests,TestClient):pass
class ResearchHTTPClient(FixtureRequests,httpx.Client):pass


def declare_in_form(page,split):
    page.locator('#sample-split-mode').select_option('dates')
    for id,key in [('backtest-from-date','is_start'),('backtest-to-date','is_end'),('sample-oos-start','oos_start'),('sample-oos-end','oos_end')]:page.locator('#'+id).fill(split[key])
    page.locator('#sample-review').click()


def cli_split(split):
    return [part for key,value in split.items() if key!='mode' for part in ('--'+key.replace('_','-'),value)]


def seed_declarations(app):
    from alphaquest.research import SplitDeclaration
    from alphaquest.strategies.registry import STRATEGIES
    for dataset in app.state.store.list():
        if dataset['id'] not in SPLITS:continue
        for strategy in STRATEGIES:
            plan=app.state.research.resolve(app.state.store,dataset,strategy,SplitDeclaration.model_validate(SPLITS[dataset['id']]))
            app.state.research.claim(plan)
