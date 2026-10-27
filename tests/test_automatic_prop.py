"""Real default-count Apex analyses and independent historical-cash expectations."""

import csv
from datetime import date, timedelta
from decimal import Decimal
import io
import json
from pathlib import Path

import pytest

from alphaquest.prop.native_analysis import DEFAULTS
from alphaquest import optimization
from test_backtest_api import body, save_fixture
from test_optimization import client, optimization_body, start, wait_job


def synthetic_history(days=60):
    lines=["Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol"]
    stamp=date(2026,1,5)
    count=0
    while count<days:
        if stamp.weekday()<5:
            for minute,prices in [(0,'99,100,99,100'),(1,'100,103,100,103'),(2,'103,103,103,103')]:
                lines.append(stamp.strftime('%m/%d/%Y')+f',18:0{minute},{prices},100,60,40')
            count+=1
        stamp+=timedelta(days=1)
    return ('\n'.join(lines)+'\n').encode()


def save_history(client,days=60):
    result=client.post('/api/datasets',params=dict(filename='SYNTHETIC-apex-cash.csv',name='SYNTHETIC automatic Apex cash arithmetic',source_timezone='UTC',tick_size='0.25',point_value='1000'),content=synthetic_history(days))
    assert result.status_code==201,result.text
    return result.json()


def expected_cash(report):
    c=report['calculations']
    assert report['settings']==DEFAULTS
    assert c['evaluation']['simulations']==20000
    assert all(row['simulations']==3000 for row in c['evaluation_sweep'])
    assert c['evaluation']['pass_rate']==1 and c['evaluation']['selected_micros']==1
    assert c['evaluation']['cost_per_funded']==178  # 49 / 100% + 129 activation
    assert c['evaluation']['days_to_funded']==11  # 10 x 300 + one activation day
    assert c['funded']['selected']['micros']==3 and c['funded']['selected']['sims']==20000
    assert all(row['sims']==3000 for row in c['funded']['sweep'])
    # 3 MNQ earns 900 per day. All six caps pay after 30 sessions (13,000).
    # Replacement waits 11 sessions. Remaining 19 sessions pay 1,500+1,500+2,000.
    # 20 slots: 18,000*20 payouts - 2 starts*20 slots*(49+129) = 352,880.
    assert c['history']['totals']['payouts']==360000
    assert c['history']['totals']['costs']==7120
    assert c['history']['totals']['net']==352880
    assert c['history']['totals']['new_funded_accounts']==40
    assert report['source']['excursion_input']['measured_mae_count']==0
    assert 'close-only fallback' in report['source']['excursion_provenance']


def test_default_fees_unavailable_source_and_immutable_backtest(client):
    dataset=save_fixture(client)
    response=client.post('/api/backtests',json=body(dataset['id']))
    assert response.status_code==201,response.text
    record=response.json();automatic=record['run_metadata']['automatic_prop_analysis']
    assert automatic['settings']==DEFAULTS
    assert automatic['settings']['ACTIVATION_FEE']=='129'
    job=client.get('/api/prop-analyses/'+automatic['id']).json()
    assert job['status']=='incompatible' and job['historical_net'] is None
    assert 'two session weekdays' in job['reason']
    original=client.get(f"/api/backtests/{record['id']}/exports/report").content
    assert client.get(f"/api/backtests/{record['id']}").json()==record
    assert client.get(f"/api/backtests/{record['id']}/exports/report").content==original
    assert client.get(f"/api/prop-analyses/{automatic['id']}/downloads/report.json").status_code==409


def test_zero_evaluation_passes_is_a_completed_outcome_without_operation_error(client):
    from test_prop_analysis_api import backtest
    record=backtest(client)
    id=record['run_metadata']['automatic_prop_analysis']['id']
    result=client.get('/api/prop-analyses/'+id).json()
    assert result['status']=='complete' and result['error'] is None
    assert result['historical_net'] is None and 'No validation evaluation passed' in result['reason']
    report=client.get(f'/api/prop-analyses/{id}/downloads/report.json').json()
    assert report['calculations']['evaluation']['simulations']==20000
    assert report['calculations']['evaluation']['passed']==0


def test_default_full_counts_historical_net_and_each_parallel_trial(client,tmp_path):
    dataset=save_history(client)
    request=body(dataset['id'])
    request['strategy_parameters']=dict(green_bar_count=1,hold_minutes=1,contracts=1)
    request['execution_settings'].update(slippage_ticks=0,commission_per_contract_per_side='0')
    standalone=client.post('/api/backtests',json=request)
    assert standalone.status_code==201,standalone.text
    record=standalone.json();id=record['run_metadata']['automatic_prop_analysis']['id']
    report=client.get(f'/api/prop-analyses/{id}/downloads/report.json').json()
    expected_cash(report)
    assert report['source']['backtest']==record
    # Configuring the same native/default analysis reopens the completed report.
    same=client.post('/api/prop-analyses',json=dict(source_backtest_id=record['id'],trade_file='',settings={}))
    assert same.status_code==202 and same.json()['id']==id
    opt=optimization_body(dataset['id'])
    opt.update(workers=min(2,optimization.MAX_WORKERS),reuse_results=True)
    opt['execution_settings']=request['execution_settings']
    opt['parameter_ranges']=dict(green_bar_count=dict(start=1,end=2,step=1),hold_minutes=dict(start=1,end=1,step=0),contracts=dict(start=1,end=1,step=0))
    job=wait_job(client,start(client,opt))
    assert job['status']=='complete',job
    rows=client.get(f"/api/optimizations/{job['id']}/results?sort=historical_net&direction=desc").json()['items']
    assert [row['metrics']['historical_net'] for row in rows]==[352880,None]
    assert all(row['prop_analysis']['status']=='complete' for row in rows)
    assert all(client.get('/api/prop-analyses/'+row['prop_analysis']['id']).json()['error'] is None for row in rows)
    expected_cash(client.get('/api/prop-analyses/'+rows[0]['prop_analysis']['id']+'/downloads/report.json').json())
    for direction in ('asc','desc'):
        page=client.get(f"/api/optimizations/{job['id']}/results?sort=historical_net&direction={direction}").json()
        assert [row['metrics']['historical_net'] for row in page['items']]==[352880,None]
    download=client.get(f"/api/optimizations/{job['id']}/exports/results?sort=historical_net&direction=desc")
    exported=list(csv.DictReader(io.StringIO(download.text)))
    assert [row['historical_net'] for row in exported]==['352880','']
    assert all(row['prop_analysis_id'] for row in exported)
    rerun=wait_job(client,start(client,opt))
    assert rerun['reused_trials']==2
    assert client.get('/api/backtests').json()['total']==3
    assert [r['run_id'] for r in client.get(f"/api/optimizations/{rerun['id']}/results").json()['items']]==[r['run_id'] for r in sorted(rows,key=lambda r:r['trial'])]
    (tmp_path/'default-prop-verification.json').write_text(json.dumps(dict(backtest=record,job=job,rows=rows,rerun=rerun,expected_historical_net=352880,expected_costs=7120,standard_counts_verified=True),indent=2))


def test_analysis_operation_error_is_visible_and_never_a_zero_result(client,monkeypatch):
    from alphaquest.prop import automatic
    def fail(*args,**kwargs):raise RuntimeError('Controlled automatic calculation failure')
    monkeypatch.setattr(automatic,'run_analysis',fail)
    dataset=save_history(client,2)
    request=body(dataset['id']);request['strategy_parameters']=dict(green_bar_count=1,hold_minutes=1,contracts=1)
    result=client.post('/api/backtests',json=request)
    assert result.status_code==201,result.text
    prop_id=result.json()['run_metadata']['automatic_prop_analysis']['id']
    prop=client.get('/api/prop-analyses/'+prop_id).json()
    assert prop['status']=='error' and prop['historical_net'] is None
    assert 'Controlled automatic calculation failure' in prop['reason']


def test_backtest_publication_failure_rolls_back_only_new_default_analysis(client,monkeypatch):
    dataset=save_fixture(client)
    def fail(*args,**kwargs):raise OSError('Controlled backtest publication failure')
    monkeypatch.setattr(client.app.state.runs,'complete',fail)
    response=client.post('/api/backtests',json=body(dataset['id']))
    assert response.status_code==500
    with client.app.state.prop_analyses.connect() as db:
        assert db.execute('select count(*) from analyses').fetchone()[0]==0
    assert client.get('/api/backtests').json()['total']==0


@pytest.mark.parametrize('name',['report.json','analysis.zip','charts/evaluation.svg'])
def test_default_reuse_rejects_modified_prop_artifacts(client,name):
    from test_prop_analysis_api import backtest,wait
    record=backtest(client)
    id=record['run_metadata']['automatic_prop_analysis']['id']
    path=client.app.state.prop_analyses.root/id/name
    path.write_bytes(path.read_bytes()+b'\n')
    assert client.app.state.prop_analyses.fingerprint(id) is None
    if name=='report.json':
        actual=client.get('/api/prop-analyses/'+id).json()
        assert actual['status']=='error' and actual['historical_net'] is None
        assert 'integrity check' in actual['reason']
    fresh=client.post('/api/prop-analyses',json=dict(source_backtest_id=record['id'],trade_file='',settings={})).json()
    assert fresh['id']!=id
    assert wait(client,fresh['id'])['status']=='complete'


def test_historical_prop_reports_keep_their_original_reader_and_downloads(client):
    store=client.app.state.prop_analyses
    id='a'*32;folder=store.root/id;folder.mkdir()
    raw=b'{"format_version":1,"status":"complete","settings":{},"legacy":true}'
    (folder/'report.json').write_bytes(raw)
    with store.connect() as db:
        db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,?)',(id,'historical','b'*32,'2026-01-01','complete','Saved report ready',None))
    assert client.get('/api/prop-analyses/'+id).json()['status']=='complete'
    assert client.get(f'/api/prop-analyses/{id}/downloads/report.json').content==raw


def test_cli_uses_default_analysis_and_normal_catalogue_without_interrupting_jobs(client,tmp_path):
    import subprocess
    import sys
    dataset=save_fixture(client)
    pending='c'*32
    with client.app.state.prop_analyses.connect() as db:
        db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,?)',(pending,'pending','d'*32,'2026-01-01','queued','Queued',None))
    output=tmp_path/'cli-default-report'
    completed=subprocess.run([sys.executable,'-m','alphaquest.run_backtest','--database',str(client.app.state.store.path),
        '--dataset-id',dataset['id'],'--output',str(output),'--initial-capital','10000','--slippage-ticks','1',
        '--commission-per-contract-per-side','1'],capture_output=True,text=True,check=True)
    result=json.loads(completed.stdout)
    record=client.get('/api/backtests/'+result['backtest_id']).json()
    automatic=record['run_metadata']['automatic_prop_analysis']
    assert automatic['settings']['ACTIVATION_FEE']=='129'
    assert client.get('/api/prop-analyses/'+automatic['id']).json()['status']=='incompatible'
    assert output.resolve()==client.app.state.runs.root/record['id']
    assert (output/'trades.csv').read_bytes()==client.get(f"/api/backtests/{record['id']}/exports/trades").content
    assert client.app.state.prop_analyses.get(pending)['status']=='queued'


def test_polling_status_and_error_share_one_catalogue_snapshot(client,monkeypatch):
    calls=[]
    def transitioning(id):
        calls.append(id)
        failed=len(calls)>1
        return dict(id=id,status='error' if failed else 'running',progress='Operation failed' if failed else 'Calculating',
                    error='Controlled operation failure' if failed else None)
    monkeypatch.setattr(client.app.state.prop_analyses,'get',transitioning)
    first=client.get('/api/prop-analyses/'+'e'*32).json()
    assert len(calls)==1 and first['status']=='running' and first['error'] is None
    second=client.get('/api/prop-analyses/'+'e'*32).json()
    assert len(calls)==2 and second['status']=='error' and second['error']=='Controlled operation failure'


def test_completed_analysis_identity_includes_engine_version(monkeypatch):
    from alphaquest import optimization_cache
    from alphaquest.prop.store import request_key
    source=dict(backtest=dict(id='e'*32),trades_sha256='native-source')
    monkeypatch.setattr(optimization_cache,'engine_identity',lambda:'engine-one')
    first=request_key(source,DEFAULTS)
    assert request_key(source,dict(DEFAULTS))==first
    assert request_key(source,{**DEFAULTS,'ACTIVATION_FEE':'0'})!=first
    monkeypatch.setattr(optimization_cache,'engine_identity',lambda:'engine-two')
    assert request_key(source,DEFAULTS)!=first


def test_saved_analysis_lookup_skips_export_discovery(client,monkeypatch):
    from alphaquest import prop_api
    dataset=save_fixture(client)
    record=client.post('/api/backtests',json=body(dataset['id'])).json()
    def reject(*args):raise AssertionError('Viewing saved results must not discover new exports')
    monkeypatch.setattr(prop_api,'matching_exports',reject)
    result=client.get(f'/api/prop-analyses/sources/{record["id"]}?discover_exports=false')
    assert result.status_code==200,result.text
    saved=result.json()
    assert saved['source']==record and saved['matched_exports']==[]
    assert saved['analyses'][0]['id']==record['run_metadata']['automatic_prop_analysis']['id']
