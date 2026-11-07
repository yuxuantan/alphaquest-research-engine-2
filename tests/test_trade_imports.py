"""Ordinary import/report routes retain exact external evidence without replay."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import csv
from hashlib import sha256
import io
import json
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from alphaquest.app import create_app
from test_canonical_trades import envelope, raw


IMPORTS = '/api/backtests/imports'


def save(client, content=None, *, status=201, filename='SYNTHETIC-export.json'):
    response = client.post(IMPORTS, params={'filename':filename}, content=content or raw(),
                           headers={'content-type':'application/json'})
    assert response.status_code == status, response.text
    return response.json()


def snapshot(folder):
    return {p.name:p.read_bytes() for p in folder.iterdir() if p.is_file()}


def test_import_preview_saved_report_exact_outputs_and_original_downloads(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        content=raw(indent=2)
        before=client.get('/api/datasets').json()
        preview=client.post(IMPORTS+'/check',params={'filename':'SYNTHETIC-export.json'},content=content)
        assert preview.status_code==200,preview.text
        preview=preview.json()
        assert preview['status']=='compatible'
        assert preview['source']['raw_sha256']==sha256(content).hexdigest()
        assert preview['summary']['total_net_pnl']=='4'
        assert preview['summary']['total_gross_pnl']=='6'
        assert preview['summary']['total_slippage_cost']=='2'
        assert preview['summary']['total_commissions']=='2'
        assert not preview['capabilities']['prop_analysis']
        assert client.get('/api/backtests').json()['total']==0
        assert client.get('/api/datasets').json()==before
        record=save(client,content)
        id=record['id']; base='/api/backtests/'+id
        assert record['summary']['initial_capital']=='10000'
        assert record['summary']['final_equity']=='10004'
        assert record['summary']['total_net_pnl']=='4'
        assert record['report_kind']=='external_trade_export'
        assert record['run_metadata']['dataset']['id'] is None
        assert record['run_metadata']['dataset']['name']=='SYNTHETIC'
        assert record['run_metadata']['research']['phase']=='is'
        assert 'plan' not in record['run_metadata']['research']
        assert record['run_metadata']['selection']['row_count'] is None
        assert record['reconciliation']['observed_bar_count'] is None
        assert record['execution_settings']['commission_per_contract_per_side'] is None
        assert record['execution_settings']['slippage_ticks'] is None
        assert client.get('/api/datasets').json()==before
        assert client.get('/api/backtests').json()['total']==1
        assert client.get(base).json()==record
        trades=client.get(base+'/trades').json()
        assert trades['total']==1
        trade=trades['items'][0]
        assert trade['trade_number']==1 and trade['external_trade_id']=='mc-42'
        assert trade['contracts']==2 and trade['entry_bar_number'] is None and trade['exit_bar_number'] is None
        assert {k:trade[k] for k in ('reference_gross_pnl','slippage_cost','gross_pnl','total_commissions','net_pnl')}=={
            'reference_gross_pnl':'8','slippage_cost':'2','gross_pnl':'6','total_commissions':'2','net_pnl':'4'}
        equity=client.get(base+'/equity').json()
        assert [r['equity'] for r in equity['items']]==['10000','10004']
        chart=client.get(base+'/chart').json()
        assert [r['equity'] for r in chart['items']]==['10000','10004']
        assert chart['currency']=='USD'
        source=client.get(base+'/exports/source')
        assert source.status_code==200 and source.content==content
        canonical=client.get(base+'/exports/canonical_source')
        assert canonical.status_code==200,canonical.text
        canonical=canonical.json()
        assert canonical['trades']==envelope()['payload']['trades']
        assert canonical['risk_events']==envelope()['payload']['risk_events']
        assert canonical['manifest']['coverage']['sessions']==['2026-01-05','2026-01-06']
        assert canonical['capabilities']['tick_completeness_verified'] is False
        for kind in ('trades','equity','report'):
            response=client.get(base+'/exports/'+kind)
            assert response.status_code==200,response.text
        rows=list(csv.DictReader(io.StringIO(client.get(base+'/exports/trades').text)))
        assert rows[0]['external_trade_id']=='mc-42'
        assert rows[0]['entry_bar_number']=='' and rows[0]['exit_bar_number']==''
        assert client.get(base+'/exports/report').json()==record
        assert client.get(base+'/market-benchmark').json().get('unavailable')


def test_import_idempotency_changed_bytes_conflict_and_reopen_never_reruns(tmp_path,monkeypatch):
    import alphaquest.backtest_api as backtest_api
    import alphaquest.execution as execution
    def forbidden(*args,**kwargs):
        raise AssertionError('Imported evidence must not execute a strategy or synthesize bars.')
    monkeypatch.setattr(backtest_api,'run_backtest',forbidden)
    monkeypatch.setattr(execution,'execute',forbidden)
    database=tmp_path/'datasets.sqlite3'
    with TestClient(create_app(database)) as client:
        content=raw(); record=save(client,content)
        folder=tmp_path/'backtest_runs'/record['id']; before=snapshot(folder)
        assert save(client,content,status=200)==record
        changed=client.post(IMPORTS,params={'filename':'same-id-pretty.json'},content=raw(indent=2))
        assert changed.status_code==409,changed.text
        assert snapshot(folder)==before
        assert client.get('/api/backtests').json()['total']==1
    with TestClient(create_app(database)) as client:
        assert client.get('/api/backtests/'+record['id']).json()==record
        assert client.get('/api/backtests/'+record['id']+'/exports/source').content==content
        assert save(client,content,status=200)==record
        assert snapshot(folder)==before


def test_concurrent_same_export_publishes_one_ordinary_report(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        content=raw()
        def submit(_): return client.post(IMPORTS,params={'filename':'SYNTHETIC.json'},content=content)
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses=list(pool.map(submit,range(4)))
        assert sorted(r.status_code for r in responses)==[200,200,200,201],[(r.status_code,r.text) for r in responses]
        assert len({r.json()['id'] for r in responses})==1
        assert client.get('/api/backtests').json()['total']==1


@pytest.mark.parametrize('failure',['partial','count','hash','missing_identity','double_cost','future_stop','float','duplicate_key'])
def test_invalid_export_preview_and_save_leave_no_report_or_dataset(tmp_path,failure):
    doc=envelope()
    if failure=='partial':doc['completion']['status']='partial'
    elif failure=='count':doc['completion']['trade_count']=2
    elif failure=='missing_identity':doc['manifest']['dataset']['sha256']=None
    elif failure=='double_cost':doc['payload']['trades'][0]['net_pnl']='2'
    elif failure=='future_stop':doc['payload']['trades'][0]['initial_stop']['known_at_utc']='2026-01-05T15:01:00Z'
    content=raw(doc)
    if failure=='hash':
        sealed=json.loads(content);sealed['completion']['payload_sha256']='0'*64;content=json.dumps(sealed).encode()
    elif failure=='float':content=content.replace(b'"initial_capital":"10000"',b'"initial_capital":10000.0')
    elif failure=='duplicate_key':content=content.replace(b'"export_id":',b'"export_id":"duplicate","export_id":',1)
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        for route in (IMPORTS+'/check',IMPORTS):
            response=client.post(route,params={'filename':'SYNTHETIC-invalid.json'},content=content)
            assert response.status_code==422,response.text
        assert client.get('/api/backtests').json()['total']==0
        assert client.get('/api/datasets').json()==[]
        assert list((tmp_path/'backtest_runs').iterdir())==[]


def test_imported_is_declaration_cannot_launch_native_replays_or_prop(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        record=save(client);id=record['id'];base='/api/backtests/'+id
        requests=[('get',base+'/oos',None),('post',base+'/oos',{'request_id':uuid4().hex}),
                  ('post',base+'/detailed',None),('post',base+'/risk',None)]
        for method,path,body in requests:
            response=getattr(client,method)(path,**({'json':body} if body is not None else {}))
            assert response.status_code==409,(path,response.text)
            assert 'external' in response.text.lower() or 'import' in response.text.lower(),response.text
        response=client.post('/api/research-campaigns/robust/preview',json=dict(campaign_id=uuid4().hex,
            source_backtest_id=id,sources=[dict(backtest_id=id,sizes=[1])]))
        assert response.status_code in (409,422),response.text
        assert 'external' in response.text.lower() or 'import' in response.text.lower(),response.text
        source=client.get('/api/prop-analyses/sources/'+id,params={'discover_exports':False})
        assert source.status_code==200,source.text
        check=client.post('/api/prop-analyses/check',json={'source_backtest_id':id})
        assert check.status_code==422,check.text
        assert any(word in check.text.lower() for word in ('risk','external','invariance')),check.text
        assert client.get('/api/backtests').json()['total']==1


@pytest.mark.parametrize('artifact',['source.json','canonical_source.json','trades.csv','equity.csv','report.json'])
def test_tampered_artifact_blocks_saved_read_download_and_prop_use(tmp_path,artifact):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        record=save(client);id=record['id'];base='/api/backtests/'+id
        path=tmp_path/'backtest_runs'/id/artifact
        original=path.read_bytes();path.write_bytes(original+b'\n')
        for endpoint in (base,base+'/trades',base+'/equity',base+'/chart',base+'/exports/source',base+'/exports/canonical_source',base+'/exports/report'):
            response=client.get(endpoint)
            assert response.status_code in (409,422), (endpoint,response.status_code,response.text)
        check=client.post('/api/prop-analyses/check',json={'source_backtest_id':id})
        assert check.status_code in (409,422),check.text
        duplicate=client.post(IMPORTS,params={'filename':'SYNTHETIC.json'},content=raw())
        assert duplicate.status_code in (409,422),duplicate.text
        path.write_bytes(original)
        assert client.get(base).status_code==200


def test_catalogue_capability_or_provenance_drift_does_not_relabel_original(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        record=save(client);id=record['id'];runs=client.app.state.runs
        original=deepcopy(record)
        record['capabilities']['native_replay']=True
        record['run_metadata']['strategy']['parameters']={'changed':'yes'}
        with runs.connect() as db:
            db.execute('UPDATE runs SET manifest=? WHERE id=?',(json.dumps(record),id))
        response=client.get('/api/backtests/'+id)
        assert response.status_code in (409,422),response.text
        with runs.connect() as db:
            db.execute('UPDATE runs SET manifest=? WHERE id=?',(json.dumps(original),id))
        assert client.get('/api/backtests/'+id).json()==original


def test_separate_runstore_instances_resolve_concurrent_export_identity(tmp_path,monkeypatch):
    from threading import Barrier
    from alphaquest.backtest_runs import RunStore
    from alphaquest.trade_imports import save_import
    stores=[RunStore(tmp_path) for _ in range(4)]
    barrier=Barrier(4)
    original=RunStore.complete
    def synchronized(self,*args,**kwargs):
        # Every instance passed its own identity lookup before any publication.
        barrier.wait(timeout=10)
        return original(self,*args,**kwargs)
    monkeypatch.setattr(RunStore,'complete',synchronized)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda store:save_import(store,raw(),'SYNTHETIC.json'),stores))
    assert sum(fresh for _,fresh in results)==1
    assert len({record['id'] for record,_ in results})==1
    assert stores[0].list(0,100)['total']==1
    assert len([path for path in stores[0].root.iterdir() if not path.name.startswith('.')])==1


def test_missing_bar_identifiers_are_admitted_only_as_declared_external_rows(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        record=save(client);runs=client.app.state.runs
        path=runs.root/record['id']/'trades.csv'
        with pytest.raises(ValueError):
            list(runs._rows(path,'trades'))
        external=list(runs._rows(path,'trades',external=True))
        assert len(external)==1
        assert json.loads(external[0][1])['entry_bar_number'] is None


def test_saved_import_reopens_without_parser_or_summary_recalculation(tmp_path,monkeypatch):
    import alphaquest.canonical_trades as canonical_trades
    import alphaquest.trade_imports as trade_imports
    database=tmp_path/'datasets.sqlite3'
    content=raw(indent=2)
    with TestClient(create_app(database)) as client:
        record=save(client,content)
        base='/api/backtests/'+record['id']
        folder=tmp_path/'backtest_runs'/record['id']
        before=snapshot(folder)
        routes=[base,base+'/trades',base+'/equity',base+'/chart',base+'/exports/report',
                base+'/exports/source',base+'/exports/canonical_source',base+'/exports/trades',base+'/exports/equity']
        saved={route:client.get(route).content for route in routes}
    def forbidden(*args,**kwargs):
        raise AssertionError('Opening saved evidence must not invoke the current parser or recalculate its summary.')
    monkeypatch.setattr(canonical_trades,'parse_trade_export',forbidden)
    monkeypatch.setattr(trade_imports,'parse_trade_export',forbidden)
    monkeypatch.setattr(trade_imports,'summarize',forbidden)
    with TestClient(create_app(database)) as client:
        library=client.get('/api/backtests')
        assert library.status_code==200,library.text
        assert library.json()['items']==[record]
        for route in routes:
            response=client.get(route)
            assert response.status_code==200,(route,response.text)
            assert response.content==saved[route],route
        assert client.get(base+'/exports/source').content==content
        assert snapshot(folder)==before
