"""Real native percentage account calculations on a labeled short synthetic source.

Only prior-admission and evidence minima are overridden to exercise the numerical
branch. These tests cannot establish production qualification or market GO.
"""
from datetime import datetime,timedelta
from uuid import uuid4
import json
import os
from pathlib import Path
import pytest
from alphaquest.app import create_app
from research_fixtures import ResearchClient
from native_replay_fixtures import source_bytes,parameter_values
from test_optimization import wait_job
from test_prop_sim_automatic import wait_automatic
from test_percentage_automatic import configuration,install_admission_fixture


def source_pair(client):
    raw=source_bytes(days=12,payout=True).decode().splitlines();later=[]
    for line in raw[1:]:
        cells=line.split(',');cells[0]=(datetime.strptime(cells[0],'%m/%d/%Y')+timedelta(days=28)).strftime('%m/%d/%Y');later.append(','.join(cells))
    upload=client.post('/api/datasets',params=dict(filename='SYNTHETIC-complementary-native.csv',name='SYNTHETIC short numerical branch; no qualification claim',symbol='MNQ',source_timezone='UTC',tick_size='.25',point_value='2'),content=('\n'.join(raw+later)+'\n').encode());assert upload.status_code==201,upload.text
    values=parameter_values();request=dict(dataset_id=upload.json()['id'],method='exhaustive',workers=1,automatic_prop=False,strategy_id='vwap_pullback_risk_sizing',parameter_ranges={k:dict(start=v,end=v,step='0' if isinstance(v,str) else 0) for k,v in values.items()},execution_settings=dict(initial_capital='10000',slippage_ticks=0,commission_per_contract_per_side='0'),sample_split=dict(mode='dates',is_start='2026-01-04',is_end='2026-01-20',oos_start='2026-02-01',oos_end='2026-02-17'))
    response=client.post('/api/optimizations',json=request);assert response.status_code==202,response.text
    job=wait_job(client,response.json()['id']);assert job['status']=='complete',job
    row,=client.get('/api/optimizations/'+job['id']+'/results').json()['items'];source=client.get('/api/backtests/'+row['run_id']).json()
    oos=client.post('/api/backtests/'+source['id']+'/oos',json=dict(request_id=uuid4().hex));assert oos.status_code==201,oos.text
    return dict(selection=dict(workflow_id=uuid4().hex,oos_job_id=uuid4().hex,monte_carlo_id=uuid4().hex,candidate=1),source_backtest_id=source['id'],oos_report_id=oos.json()['id'],strategy_id=source['run_metadata']['strategy']['id'],dataset=upload.json(),parameters=values,plan=source['run_metadata']['research']['plan'],broad_trial=1,narrow_trial=1,qualification='SYNTHETIC admission fixture only')


@pytest.mark.parametrize('profile',['apex-50k-eod','lucidflex-50k'])
def test_native_both_phases_do_actual_accounts_without_nested_refits(tmp_path,monkeypatch,profile):
    from alphaquest.prop import complementary_assessment as owner
    monkeypatch.setitem(owner.RULES,'minimum_complete_months',0)
    monkeypatch.setitem(owner.RULES,'minimum_closed_trades',0)
    # Retain every production account count, horizon and stress scenario.
    monkeypatch.setattr('alphaquest.prop.native_oos_bootstrap.run',lambda *a,**k:pytest.fail('Nested native historical refit'))
    monkeypatch.setattr('alphaquest.prop.oos_bootstrap.run',lambda *a,**k:pytest.fail('Nested historical refit'))
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        source=source_pair(client);install_admission_fixture(monkeypatch,source)
        body=configuration(source,profile)
        if profile=='lucidflex-50k':body.update(evaluation_price='99.50',activation_fee='0',evaluation_consistency_percent=50)
        response=client.post('/api/prop-sim',json=body);assert response.status_code==202,response.text
        saved=wait_automatic(client,response.json()['id'],timeout=240)
        assert all(p['stage']=='complete' for p in saved['automation']['phases'].values()),saved
        for phase in ('evaluation','funded'):
            state=saved['automation']['phases'][phase]
            report=client.get(f"/api/prop-sim/{saved['id']}/validation/{phase}/{state['oos_request_id']}").json()
            calc=report['calculations']
            assert 'qualification_bootstrap' not in calc
            for row in calc['candidates']:
                q=row['prop_qualification']
                assert q['version']==owner.VERSION and q['historical_replicates']==0
                assert q['status'] in ('GO','REVIEW_REQUIRED','INSUFFICIENT_EVIDENCE') # Short-start coverage is reported, never fabricated.
                assert q['account_comparison']['oos'][0]['paths']==5000
                assert len(q['stress_scenarios'])==5
                if phase=='evaluation':
                    assert q['account_comparison']['oos'][0]['funded_probability']['mean']==1
                    assert q['account_comparison']['oos'][0]['fees_spent']['mean']==(178 if profile=='apex-50k-eod' else 99.5)
                else:
                    # First gross payout: Apex $1,500; Lucid $2,000 at 90% trader share.
                    assert q['account_comparison']['oos'][0]['received_cash']['mean']==(1500 if profile=='apex-50k-eod' else 1800)
            assert client.app.state.prop_analyses.fingerprint(report['id'])
            if destination:=os.environ.get('ALPHAQUEST_COMPLEMENTARY_NATIVE_EVIDENCE_DIR'):
                target=Path(destination)/profile;target.mkdir(parents=True,exist_ok=True)
                (target/(phase+'-report.json')).write_text(json.dumps(report,indent=2))
                (target/'scope.json').write_text(json.dumps(dict(synthetic=True,admission_fixture=True,evidence_minima_overridden_only_in_test=True,production_path_counts=True,production_deadlines=True,source=source,configuration=body,simulation=saved),indent=2))
