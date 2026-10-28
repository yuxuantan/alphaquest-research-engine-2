"""Normal source/replay checks, original artifacts and holdout budgets."""
import csv
from hashlib import sha256
import json

import pytest

from test_research_workflow import client,save,body,status,oos
from alphaquest.prop.source import prepare_source
from alphaquest.prop.automatic import profile


def run(client):
    dataset=save(client,days=4)
    response=client.post('/api/backtests',json=body(dataset))
    assert response.status_code==201,response.text
    return response.json(),dataset


def test_native_risk_capture_default_source_hashes_downloads_and_fail_closed(client):
    record,dataset=run(client)
    id=record['id'];base='/api/backtests/'+id
    assert record['intratrade_risk']['trades']==2
    raw=client.get(base+'/exports/intratrade_risk').content
    assert sha256(raw).hexdigest()==record['intratrade_risk']['sha256']
    request=dict(source_backtest_id=id,trade_file='',settings={})
    check=client.post('/api/prop-analyses/check',json=request)
    assert check.status_code==200,check.text
    inp=check.json()['source']['excursion_input']
    assert inp['native_ohlc_count']==2 and inp['measured_mae_count']==0
    assert inp['risk_policy']=='conservative_held_ohlc_upper'
    prop=record['run_metadata']['automatic_prop_analysis']
    report=client.get('/api/prop-analyses/'+prop['id']+'/downloads/report.json').json()
    assert client.get('/api/prop-analyses/'+prop['id']+'/files/inputs/intratrade_risk.csv').content==raw
    assert report['source']['native_risk']==record['intratrade_risk']
    assert client.post(base+'/risk').json()['id']==id # No duplicate replay.
    assert status(client,dataset)['used']==0
    path=client.app.state.runs.root/id/'intratrade_risk.csv'
    path.write_bytes(raw+b'\n')
    broken=client.post('/api/prop-analyses/check',json=request)
    assert broken.status_code==422 and 'SHA-256' in broken.text
    path.unlink()
    assert client.post('/api/prop-analyses/check',json=request).status_code==422


def make_older(client,record):
    # Fixture simulates an immutable pre-capture manifest without editing any
    # financial oracles; only this test database is changed.
    record=json.loads(json.dumps(record));record.pop('intratrade_risk')
    record['artifacts'].pop('intratrade_risk_csv')
    with client.app.state.runs.connect() as db:
        db.execute('UPDATE runs SET manifest=? WHERE id=?',(json.dumps(record),record['id']))
    return record


def test_is_risk_upgrade_keeps_original_financial_results_and_budget(client):
    record,dataset=run(client);record=make_older(client,record)
    root=client.app.state.runs.root/record['id']
    original={p.name:sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p.is_file()}
    response=client.post('/api/backtests/'+record['id']+'/risk')
    assert response.status_code==201,response.text
    upgraded=response.json()
    assert upgraded['id']!=record['id']
    assert upgraded['run_metadata']['risk_from_run_id']==record['id']
    assert upgraded['summary']==record['summary']
    assert upgraded['report_storage']['detail']=='compact'
    assert upgraded['run_metadata']['automatic_prop_analysis']['id']!=record['run_metadata']['automatic_prop_analysis']['id']
    assert upgraded['run_metadata']['automatic_prop_analysis']['version']==profile()['version']
    assert original=={p.name:sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p.is_file()}
    for kind in ('trades','equity'):
        assert client.get('/api/backtests/'+record['id']+'/exports/'+kind).content==client.get('/api/backtests/'+upgraded['id']+'/exports/'+kind).content
    assert client.post('/api/backtests/'+record['id']+'/risk').json()['id']==upgraded['id']
    assert status(client,dataset)['used']==0
    out=oos(client,upgraded);assert out.status_code==201,out.text
    blocked=client.post('/api/backtests/'+out.json()['id']+'/risk')
    assert blocked.status_code==409 and 'manual OOS' in blocked.text
    assert status(client,dataset)['used']==1


def test_risk_upgrade_rejects_changed_strategy_and_legacy(client,monkeypatch):
    record,_=run(client);record=make_older(client,record)
    from alphaquest import backtest_api
    class Changed:
        def description(self):return dict(source_sha256='changed')
    monkeypatch.setattr(backtest_api,'get_strategy',lambda name:Changed())
    response=client.post('/api/backtests/'+record['id']+'/risk')
    assert response.status_code==422 and 'Strategy source has changed' in response.text
    record['run_metadata'].pop('research')
    with client.app.state.runs.connect() as db:db.execute('UPDATE runs SET manifest=? WHERE id=?',(json.dumps(record),record['id']))
    assert client.post('/api/backtests/'+record['id']+'/risk').status_code==409


def test_risk_snapshot_rejects_corrupt_costs_even_with_resigned_file(client):
    record,_=run(client)
    root=client.app.state.runs.root/record['id'];path=root/'intratrade_risk.csv'
    rows=list(csv.DictReader(path.open()));rows[0]['net_pnl']='999999'
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    record['intratrade_risk']['sha256']=sha256(path.read_bytes()).hexdigest()
    with client.app.state.runs.connect() as db:db.execute('UPDATE runs SET manifest=? WHERE id=?',(json.dumps(record),record['id']))
    with pytest.raises(ValueError,match='net costs differ'):
        prepare_source(client.app.state.runs,record['id'],'')
