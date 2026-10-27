import json
from pathlib import Path
from time import perf_counter
from test_backtest_api import client,body,save_fixture
from test_automatic_prop import synthetic_history,expected_cash


def test_result_reuse_verifies_artifacts_and_deletion_cascades(client):
    dataset=save_fixture(client);request={**body(dataset['id']),'reuse_results':True}
    first=client.post('/api/backtests',json=request);assert first.status_code==201,first.text
    id=first.json()['id'];root=client.app.state.runs.root/id
    before={p.name:p.read_bytes() for p in root.iterdir()}
    from uuid import uuid4
    progress_id=str(uuid4())
    second=client.post('/api/backtests',json=request,params=dict(progress_id=progress_id))
    assert second.status_code==200 and second.headers['X-AlphaQuest-Reused']=='true'
    assert client.get('/api/progress/'+progress_id).json()['run_id']==id
    assert second.json()==first.json() and before=={p.name:p.read_bytes() for p in root.iterdir()}
    (root/'equity.csv').write_text('corrupted')
    third=client.post('/api/backtests',json=request);assert third.status_code==201
    assert third.json()['id']!=id
    new=third.json()['id'];assert client.delete('/api/backtests/'+new).status_code==204
    assert client.post('/api/backtests',json=request).status_code==201


def test_pure_prop_calculation_reuse_keeps_new_source_identity_and_exact_standard_results(client,tmp_path):
    response=client.post('/api/datasets',params=dict(filename='SYNTHETIC-reuse-cash.csv',name='SYNTHETIC reusable calculations',source_timezone='UTC',tick_size='.25',point_value='1000'),content=synthetic_history())
    assert response.status_code==201,response.text
    dataset=response.json();request=body(dataset['id'])
    request['strategy_parameters']=dict(green_bar_count=1,hold_minutes=1,contracts=1)
    request['execution_settings'].update(slippage_ticks=0,commission_per_contract_per_side='0')
    records=[];reports=[];observations=[]
    for _ in range(2):
        start=perf_counter();response=client.post('/api/backtests',json=request)
        assert response.status_code==201,response.text
        record=response.json();records.append(record);id=record['run_metadata']['automatic_prop_analysis']['id']
        report=client.get('/api/prop-analyses/'+id+'/downloads/report.json').json()
        expected_cash(report);reports.append(report)
        assert report['source']['backtest']['id']==record['id']
        observations.append(dict(id=record['id'],prop_id=id,seconds=perf_counter()-start,performance=client.get('/api/backtests/'+record['id']+'/performance').json()))
    assert records[0]['id']!=records[1]['id']
    assert reports[0]['calculations']==reports[1]['calculations']
    assert reports[0]['runtime']['calculation_reused_from'] is None
    assert reports[1]['runtime']['calculation_reused_from']==reports[0]['id']
    response=client.post('/api/backtests',json={**request,'reuse_results':True})
    assert response.status_code==200 and response.json()==records[1]
    assert client.get('/api/backtests').json()['total']==2
    (tmp_path/'reuse-verification.json').write_text(json.dumps(dict(synthetic=True,expected_historical_net=352880,all_calculations_equal=True,source_identity_preserved=True,observations=observations,reopened_id=response.json()['id']),indent=2))


def test_calculation_reuse_bad_checksum_and_setting_change_force_computation(tmp_path):
    from alphaquest.prop.calculation_cache import calculate,use
    from hashlib import sha256
    path=tmp_path/'calculations.json';raw=b'{"cash":123}';path.write_bytes(raw)
    snapshot=dict(trades_sha256='abc',excursion_input={},source_timezone='UTC',session_grid={})
    calls=[]
    def compute(rows,settings,progress):calls.append(settings);return {'cash':123}
    result,original,key=calculate([],{},snapshot,lambda _:None,compute)
    entry={key:dict(id='saved',path=str(path),sha256=sha256(raw).hexdigest())}
    with use(entry):
        assert calculate([],{},snapshot,lambda _:None,compute)[:2]==({'cash':123},'saved')
        assert len(calls)==1
        path.write_text('{"cash":999}')
        assert calculate([],{},snapshot,lambda _:None,compute)[1] is None
        path.write_bytes(raw)
        assert calculate([],{'ACTIVATION_FEE':'130'},snapshot,lambda _:None,compute)[1] is None
    assert len(calls)==3
