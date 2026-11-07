"""Native decision provenance through ordinary RunStore/report/replay routes."""
from hashlib import sha256
from decimal import Decimal
import json
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from alphaquest.app import create_app
from alphaquest.backtest_api import prepare_backtest_report, run_backtest
from alphaquest.backtest_data import DateRange
from alphaquest.backtest_requests import ExecutionSettings
from alphaquest.decision_capture import SIDE_CAR
from alphaquest.optimization_cache import artifacts
from alphaquest.strategies.registry import get_strategy
from test_prop_phases import phase_history


def inputs(client):
    response=client.post('/api/datasets',params=dict(filename='SYNTHETIC-native-decisions.csv',name='SYNTHETIC decision capture',source_timezone='UTC',symbol='MNQ',tick_size='.25',point_value='2'),content=phase_history(3))
    assert response.status_code==201,response.text
    dataset=response.json();definition=get_strategy('consecutive_green_hold')
    parameters=definition.parameters(dict(green_bar_count=1,hold_minutes=1,contracts=1))
    config=ExecutionSettings(initial_capital='10000',tick_size='.25',point_value='2',slippage_ticks=0,commission_per_contract_per_side='0').execution_config(dataset)
    return dataset,definition,parameters,config


def save(client,values,*,historical=False):
    dataset,definition,parameters,config=values
    store,runs=client.app.state.store,client.app.state.runs
    id=uuid4().hex
    if historical:
        output=runs.root.parent/('pending-'+id)
        manifest,_,_=prepare_backtest_report(store,output,dataset,definition,parameters,config,DateRange(),lambda *args:None,
            report_detail='compact',research={'phase':'is'},capture_decisions=False)
        return runs.complete(id,output,manifest)
    return run_backtest(store,runs,id,dataset,definition,parameters,config,DateRange(),lambda *args:None,
        prop_analyses=None,reuse_results=False,reuse_calculations=False,research={'phase':'is'})


def test_new_native_report_download_and_detailed_reproduction_keep_exact_decisions(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        record=save(client,inputs(client));runs=client.app.state.runs
        description=record['execution_decisions'];id=record['id']
        path=runs.root/id/SIDE_CAR;content=path.read_bytes()
        assert description['filled_trades']==3 and description['decisions']==3
        assert description['sha256']==sha256(content).hexdigest()
        assert artifacts(runs.root,record)[SIDE_CAR]==description['sha256']
        result=client.get(f'/api/backtests/{id}/exports/execution_decisions')
        assert result.status_code==200 and result.content==content
        rows=[json.loads(line) for line in content.splitlines()]
        assert all(row['stop_price'] is None for row in rows if row['kind']=='entry_decision')
        # The ordinary detail route reproduces the same source evidence, while
        # its report may retain additional per-bar equity.
        result=client.post(f'/api/backtests/{id}/detailed')
        assert result.status_code==201,result.text
        detailed=result.json()
        assert detailed['execution_decisions']==description
        assert (runs.root/detailed['id']/SIDE_CAR).read_bytes()==content
        for name in ('trades.csv','equity.csv'):
            assert (runs.root/id/name).read_bytes()==(runs.root/detailed['id']/name).read_bytes()


def test_historical_report_replay_keeps_missing_capture_and_original_artifacts(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        record=save(client,inputs(client),historical=True)
        runs=client.app.state.runs;folder=runs.root/record['id']
        before={p.name:p.read_bytes() for p in folder.iterdir()}
        assert 'execution_decisions' not in record
        assert client.get(f"/api/backtests/{record['id']}/exports/execution_decisions").status_code==404
        result=client.post(f"/api/backtests/{record['id']}/detailed")
        assert result.status_code==201,result.text
        detailed=result.json()
        assert 'execution_decisions' not in detailed
        assert not (runs.root/detailed['id']/SIDE_CAR).exists()
        assert before=={p.name:p.read_bytes() for p in folder.iterdir()}


def test_changed_native_sidecar_rejects_download_and_new_replay(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        record=save(client,inputs(client));runs=client.app.state.runs
        path=runs.root/record['id']/SIDE_CAR
        path.write_bytes(path.read_bytes()+b'\n')
        assert client.get(f"/api/backtests/{record['id']}/exports/execution_decisions").status_code==409
        result=client.post(f"/api/backtests/{record['id']}/detailed")
        assert result.status_code==422,result.text
        assert 'provenance' in result.text
        assert runs.list(0,100)['total']==1


def test_optimization_worker_captures_new_native_decisions_without_auto_prop(tmp_path):
    from alphaquest.optimization_worker import TrialContext,compute_trial
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        dataset,definition,parameters,config=inputs(client)
        snapshot=tmp_path/'worker-source.csv'
        snapshot.write_bytes(b''.join(client.app.state.store.iter_csv(dataset['id'])))
        output=tmp_path/'worker-output';output.mkdir()
        context=TrialContext(snapshot,output,dataset,'consecutive_green_hold',config,DateRange(),default_prop=False,research={'phase':'is'})
        result=compute_trial(context,1,dict(green_bar_count=1,hold_minutes=1,contracts=1),'trial-native-decisions',lambda *args:None)
        assert result['prop_analysis'] is None
        assert result['manifest']['execution_decisions']['filled_trades']==3
        assert (output/'trial-native-decisions'/SIDE_CAR).is_file()


def native_vwap_product_inputs():
    """Complete labelled synthetic sessions; no inferred or padded coverage."""
    from dataclasses import asdict
    from datetime import timedelta
    import csv
    import io
    from alphaquest.reporting import json_value
    from test_vwap_pullback import scenario,parameters
    output=io.StringIO(newline='')
    writer=csv.writer(output,lineterminator='\n')
    writer.writerow(['Date','Time','Open','High','Low','Close','Volume','UpVol','DownVol'])
    # Each declared day supplies its entire independently constructed source
    # session, including actual indicator warmup and the subsequent fill bars.
    for offset in range(4):
        for bar in scenario():
            stamp=bar.timestamp_utc+timedelta(days=offset)
            writer.writerow([stamp.strftime('%m/%d/%Y'),stamp.strftime('%H:%M'),
                *[str(getattr(bar,key)) for key in ('open','high','low','close','volume','up_vol','down_vol')]])
    body=dict(strategy_id='vwap_pullback_risk_sizing',
        strategy_parameters=json.loads(json.dumps(asdict(parameters(day_reset_time=700)),default=json_value)),
        execution_settings=dict(initial_capital='10000',tick_size='0.25',point_value='20',slippage_ticks=1,commission_per_contract_per_side='1'),
        sample_split=dict(mode='dates',is_start='2026-01-05',is_end='2026-01-07',oos_start='2026-01-08',oos_end='2026-01-08'),
        report_detail='compact',reuse_results=False)
    return output.getvalue().encode(),body


def native_phase_sizing_request(record):
    from alphaquest.prop.phase_profiles import rule_version
    from sizing_fixtures import sizing_configuration
    return dict(mode='evaluation_optimization',source_backtest_id=record['id'],
        candidates=[dict(source=dict(source_backtest_id=record['id']),
            profile=dict(profile_id='apex-50k-eod',rule_version=rule_version('apex-50k-eod'),evaluation_price='30',activation_fee='40'),
            micros=10,simulation=dict(simulations=8,seed=42,max_micros=40),
            sampling=dict(block_weekdays=1,chain_simulations=8,chain_seed=45),
            costs=dict(mode='source'),period=dict(first_session='2026-01-05',last_session='2026-01-07'),
            sizing=sizing_configuration('fixed_contracts',contracts=10))],
        calendar=dict(start_dates=['2026-01-05'],coverage_end='2037-01-01',closures=[]))


def exercise_native_vwap_product(client):
    """Reusable ordinary-API journey, returning inspectable actual evidence."""
    from copy import deepcopy
    from alphaquest.canonical_trades import project_native_source
    from sizing_fixtures import sizing_configuration
    content,request=native_vwap_product_inputs()
    response=client.post('/api/datasets',params=dict(filename='SYNTHETIC-native-VWAP-four-sessions.csv',
        name='SYNTHETIC native VWAP causal stops — four complete sessions',source_timezone='UTC',symbol='NQ',tick_size='0.25',point_value='20'),content=content)
    assert response.status_code==201,response.text
    dataset=response.json();request['dataset_id']=dataset['id']
    response=client.post('/api/backtests',json=request)
    assert response.status_code==201,response.text
    record=response.json();id=record['id'];base='/api/backtests/'+id
    assert record['run_metadata']['research']['phase']=='is'
    assert record['run_metadata']['research']['plan']['oos_start']=='2026-01-08'
    assert record['summary']['trades_taken']==3 and Decimal(record['summary']['total_net_pnl'])==Decimal('879')
    trade_response=client.get(base+'/trades')
    assert trade_response.status_code==200,trade_response.text
    trades=trade_response.json()['items']
    assert [Decimal(trade['net_pnl']) for trade in trades]==[Decimal('293')]*3
    assert all(trade['entry_reference_price']=='115' and trade['entry_fill_price']=='115.25' for trade in trades)
    download=client.get(base+'/exports/execution_decisions')
    assert download.status_code==200,download.text
    evidence=[json.loads(line) for line in download.content.splitlines()]
    signals=[event for event in evidence if event['kind']=='entry_decision']
    assert len(signals)==3 and all(event['reference_price']=='108' and event['stop_price']=='90' for event in signals)
    assert [event['timestamp_utc'] for event in signals]==[f'2026-01-0{day}T15:01:00Z' for day in (5,6,7)]
    projection=project_native_source(client.app.state.runs,id)
    assert all(trade['sizing_decision']['reference_price']=='108' and trade['initial_stop']['price']=='90' for trade in projection['trades'])
    assert projection['capabilities']['quantity_path_policy']=='native_rerun_required'
    source_check=client.get('/api/prop-analyses/sources/'+id,params={'discover_exports':False})
    assert source_check.status_code==200,source_check.text
    fixed=native_phase_sizing_request(record)
    compatible=client.post('/api/prop-analyses/check',json=fixed)
    assert compatible.status_code==200,compatible.text
    assert compatible.json()['status']=='compatible'
    dynamic=deepcopy(fixed);dynamic['candidates'][0]['sizing']=sizing_configuration('fixed_dollar_risk')
    rejected=client.post('/api/prop-analyses/check',json=dynamic)
    assert rejected.status_code==422,rejected.text
    assert 'Native risk-based policies require a strategy rerun' in rejected.json()['detail']
    oos_status=client.get(base+'/oos')
    assert oos_status.status_code==200 and oos_status.json()['used']==0 and oos_status.json()['attempts']==[]
    report_download=client.get(base+'/exports/report')
    assert report_download.status_code==200,report_download.text
    return dict(dataset=dataset,request=request,record=record,source_csv=content,
        decisions=download.content,report=report_download.content,canonical_projection=projection,
        source_check=source_check.json(),oos_status=oos_status.json(),fixed_request=fixed,fixed_check=compatible.json(),
        risk_request=dynamic,risk_rejection=dict(status=rejected.status_code,body=rejected.json()),
        observed=dict(signal_close='108',initial_stop='90',actual_entry_reference='115',actual_entry_fill='115.25',
                      trade_net=trades[0]['net_pnl'],trades=len(trades),total_net=record['summary']['total_net_pnl'],reserved_oos_accessed=False,
                      quantity_path_policy='native_rerun_required'))


def test_native_vwap_normal_api_source_capture_fixed_check_and_risk_rejection(tmp_path,monkeypatch):
    import alphaquest.backtest_api as backtest_api
    database=tmp_path/'datasets.sqlite3'
    with TestClient(create_app(database)) as client:
        result=exercise_native_vwap_product(client)
    def forbidden(*args,**kwargs):raise AssertionError('Saved native source must reopen without rerunning its strategy.')
    monkeypatch.setattr(backtest_api,'run_backtest',forbidden)
    with TestClient(create_app(database)) as client:
        id=result['record']['id']
        assert client.get('/api/backtests/'+id).json()==result['record']
        assert client.get(f'/api/backtests/{id}/exports/execution_decisions').content==result['decisions']
        assert client.get(f'/api/backtests/{id}/exports/report').content==result['report']
