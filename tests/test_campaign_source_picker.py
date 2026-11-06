"""Catalogue metadata selection: bounded pages, no OOS outcomes or source replay."""
from copy import deepcopy
import json
from uuid import uuid4

import pytest
from test_research_campaigns import library


def test_metadata_only_picker_search_pagination_and_status(library,monkeypatch):
    client,a,b,_=library
    runs=client.app.state.runs
    created_runs=[];created_jobs=[]
    try:
        # Test-only catalogue rows exercise large lists and excluded metadata.
        with runs.connect() as db:
            for i in range(54):
                row=deepcopy(a);row['id']=uuid4().hex;created_runs.append(row['id'])
                row['run_metadata']['strategy']['parameters']['green_bar_count']=i+10
                row['run_metadata']['dataset']['name']='PICKER-pagination'
                db.execute('INSERT INTO runs VALUES (?,?,?)',(row['id'],f'2026-11-06T01:{i:02}:00Z',json.dumps(row)))
            for phase in ('oos','legacy'):
                row=deepcopy(a);row['id']=uuid4().hex;created_runs.append(row['id'])
                row['run_metadata']['research']['phase']=phase
                row['summary']={'NEVER_EXPOSE_OOS_OUTCOMES':999999}
                db.execute('INSERT INTO runs VALUES (?,?,?)',(row['id'],'2099-01-01',json.dumps(row)))
            for status,phase in [('complete','is'),('running','is'),('failed','is'),('interrupted','is'),('deleting','is'),('complete','oos')]:
                id=uuid4().hex;created_jobs.append(id)
                job=dict(id=id,status=status,total_trials=3,strategy={'id':'consecutive_green_hold'},
                    dataset={'name':'PICKER jobs'},research={'phase':phase,'plan':a['run_metadata']['research']['plan']},
                    request={'parameter_ranges':{'green_bar_count':{'start':1,'end':3,'step':1}}},
                    NEVER_EXPOSE_OOS_OUTCOMES=999999)
                db.execute('INSERT INTO optimizations VALUES (?,?,?)',(id,'2026-11-06',json.dumps(job)))
        def forbidden(*a,**kw):pytest.fail('Picker loaded full reports or calculated sources')
        monkeypatch.setattr(runs,'get',forbidden)
        monkeypatch.setattr(client.app.state.prop_analyses,'summary',forbidden)
        monkeypatch.setattr(client.app.state.campaigns,'expand',forbidden)
        first=client.get('/api/research-campaigns/sources',params=dict(kind='backtest_id',q='PICKER-pagination',limit=50)).json()
        second=client.get('/api/research-campaigns/sources',params=dict(kind='backtest_id',q='PICKER-pagination',offset=50,limit=50)).json()
        assert first['total']==second['total']==54
        assert len(first['items'])==50 and len(second['items'])==4
        assert not {r['id'] for r in first['items']} & {r['id'] for r in second['items']}
        all_rows=client.get('/api/research-campaigns/sources',params=dict(kind='backtest_id',limit=100)).json()
        assert all_rows['total']==56
        assert set(created_runs[-2:]).isdisjoint(r['id'] for r in all_rows['items'])
        assert 'NEVER_EXPOSE' not in json.dumps(all_rows) and 'summary' not in json.dumps(all_rows)
        for query in (b['id'], 'green_bar_count', 'consecutive green', '2026-01-05'):
            found=client.get('/api/research-campaigns/sources',params=dict(kind='backtest_id',q=query)).json()
            assert found['total']>=1
        exact=client.get('/api/research-campaigns/sources',params=dict(kind='backtest_id',q=b['id'])).json()
        assert [r['id'] for r in exact['items']]==[b['id']]
        assert exact['items'][0]['parameters']['green_bar_count']==2
        jobs=client.get('/api/research-campaigns/sources',params=dict(kind='optimization_id',q='PICKER')).json()
        assert jobs['total']==4
        assert {r['status'] for r in jobs['items']}=={'complete','running','failed','interrupted'}
        assert [r['id'] for r in jobs['items'] if r['selectable']]==[created_jobs[0]]
        assert 'NEVER_EXPOSE' not in json.dumps(jobs)
        for bad in ({'kind':'unknown'},{'kind':'backtest_id','limit':101},{'kind':'backtest_id','offset':-1}):
            assert client.get('/api/research-campaigns/sources',params=bad).status_code==422
    finally:
        with runs.connect() as db:
            db.executemany('DELETE FROM runs WHERE id=?',[(id,) for id in created_runs])
            db.executemany('DELETE FROM optimizations WHERE id=?',[(id,) for id in created_jobs])
