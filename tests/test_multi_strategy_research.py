"""True multi-strategy normal workflow; no generated winners or joined objectives."""
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
import os

from fastapi.testclient import TestClient

from alphaquest.app import create_app
from alphaquest.optimization_cache import engine_identity
from multi_strategy_fixtures import source_bytes,strategies,configuration_key,EXPECTED_DAILY
from test_optimization import wait_job
from test_robust_research_api import PREFIX,declaration,save,run
from test_robust_economic_api import economic
from test_research_procedure_api import wait_application


def save_multistrategy_grid(client):
    response=client.post('/api/datasets',params=dict(filename='SYNTHETIC-two-strategy-sparse.csv',
        name='SYNTHETIC two genuine strategies, sparse observed bars and zero costs',source_timezone='America/Chicago',
        symbol='MNQ',tick_size='.25',point_value='2'),content=source_bytes())
    assert response.status_code==201,response.text
    dataset=response.json();jobs=[];records=[]
    base=dict(dataset_id=dataset['id'],method='exhaustive',workers=1,automatic_prop=False,reuse_results=False,
        execution_settings=dict(initial_capital='10000',tick_size='.25',point_value='2',slippage_ticks=0,commission_per_contract_per_side='0'),
        sample_split=dict(mode='dates',is_start='2026-01-05',is_end='2026-01-22',oos_start='2026-01-23',oos_end='2026-01-30'))
    for strategy,parameters,axis in strategies():
        ranges={name:dict(start=value,end=value,step='0' if isinstance(value,str) else 0) for name,value in parameters.items()}
        ranges[axis]=dict(start=1,end=2,step=1)
        response=client.post('/api/optimizations',json=dict(base,strategy_id=strategy,parameter_ranges=ranges))
        assert response.status_code==202,response.text
        job=wait_job(client,response.json()['id']);assert job['status']=='complete',job
        jobs.append(job)
        rows=client.get('/api/optimizations/'+job['id']+'/results').json()['items'];assert len(rows)==2
        for row in rows:
            record=client.get('/api/backtests/'+row['run_id']).json();records.append(record)
            key=configuration_key(record);trades=client.get('/api/backtests/'+record['id']+'/trades').json()
            assert trades['total']==14
            assert {Decimal(t['net_pnl']) for t in trades['items']}=={Decimal(EXPECTED_DAILY[key])}
            assert {int(t['contracts']) for t in trades['items']}=={1}
            assert Decimal(record['summary']['total_net_pnl'])==Decimal(EXPECTED_DAILY[key])*14
    assert len(records)==4
    return dataset,jobs,records


def test_two_strategies_full_membership_phase_abstention_outer_and_fresh_current_fit(tmp_path,monkeypatch):
    if os.environ.get('AQ_EXPECTED_SOURCE_ROOT'):
        import alphaquest
        assert Path(alphaquest.__file__).resolve().is_relative_to(Path(os.environ['AQ_EXPECTED_SOURCE_ROOT']).resolve())
    before=engine_identity();database=tmp_path/'datasets.sqlite3'
    with TestClient(create_app(database)) as client:
        _,jobs,records=save_multistrategy_grid(client)
        body=declaration(jobs[0],records,economic_studies=[economic(client,'evaluation'),economic(client,'funded')])
        body['name']='SYNTHETIC four configurations from two genuine strategies'
        body['sources']=[dict(optimization_id=job['id'],sizes=[1]) for job in jobs]
        # Four candidates need sufficient two-sided family-tail computation;
        # these repetitions do not increase the four historical sessions.
        body['qualification'].update(additional_round_trip_cost='0',bootstrap_replicates=1000)
        response=client.post(PREFIX+'/preview',json=body);assert response.status_code==200,response.text
        plan=response.json();ids={c['id'] for c in plan['candidates']}
        assert len(ids)==4 and len(plan['folds'])==2
        assert {c['strategy_id'] for c in plan['candidates']}=={'consecutive_green_hold','vwap_pullback_risk_sizing'}
        campaign=save(client,body)['campaign_id'];completed=run(client,campaign)
        children=[];outer_ids=[]
        for fold in completed['result']['folds']:
            assert set(fold['qualification']['approved_ids'])==ids
            for candidate in fold['qualification']['candidates']:
                assert candidate['metrics']['validation_sessions']==4
                assert candidate['metrics']['validation_trades']==4
                assert len(candidate['parameter_stability']['neighbor_ids'])==1
            for phase in fold['economic_selection']['phases']:
                children.append(phase['analysis_id'])
                response=client.get('/api/prop-analyses/'+phase['analysis_id']+'/downloads/report.json')
                assert response.status_code==200,response.text
                report=response.json();assert len(report['calculations']['candidates'])==8
                assert {c['micros'] for c in report['request']['candidates']}=={10,20}
                assert len({c['source']['source_backtest_id'] for c in report['request']['candidates']})==4
                if phase['phase']=='evaluation':
                    # $4/day*20 MNQ*21 sessions=$1680<$3000. The full
                    # family's acquisition mean is unresolved; no hidden winner.
                    assert phase['decision']['status']=='INSUFFICIENT_EVIDENCE'
                    assert phase['decision']['reason']=='complete_candidate_family_not_resolved'
                    assert not phase['frozen_packages'] and report['calculations']['unresolved_candidates']
                else:
                    assert len(phase['frozen_packages'])==8
                    assert {p['strategy']['id'] for p in phase['frozen_packages']}=={'consecutive_green_hold','vwap_pullback_risk_sizing'}
                    assert {c['metrics']['expected_funded_cash_payouts_within_horizon'] for c in report['calculations']['candidates']}=={0}
            replay=fold['chronological_replay'];assert replay['status']=='complete' and len(replay['items'])==8
            for item in replay['items']:
                assert item['phase']=='funded'
                assert Decimal(item['result']['cash_received'])==Decimal(item['result']['pending_cash'])==0
                outer_ids.append(item['outer_run_id'])
                actual=client.get('/api/backtests/'+item['outer_run_id']).json()
                assert Decimal(actual['summary']['total_net_pnl'])==Decimal(EXPECTED_DAILY[configuration_key(actual)])*2
                assert actual['run_metadata']['research']['role']=='outer_test'
        assert len(children)==4 and len(outer_ids)==16
        for phase in ('evaluation','funded'):
            assert completed['result']['reliability']['phases'][phase]['status']=='INSUFFICIENT_EVIDENCE'
        response=client.post(f'{PREFIX}/{campaign}/procedure/preview',json={});assert response.status_code==200,response.text
        response=client.post(f'{PREFIX}/{campaign}/procedure/freeze',json=dict(procedure_id=uuid4().hex,expected_preview_sha256=response.json()['preview_sha256']))
        assert response.status_code==201,response.text
        procedure=response.json();assert len(procedure['algorithm']['configurations'])==4
        app_id=uuid4().hex
        response=client.post(f'{PREFIX}/{campaign}/development-selection/run',json=dict(request_id=app_id,procedure_sha256=procedure['procedure_sha256']))
        assert response.status_code==202,response.text
        current=wait_application(client,campaign,app_id)['result']
        assert current['terminal_plan']['application_role']=='current_development'
        assert set(current['qualification']['approved_ids'])==ids
        assert len(current['economic_selection']['membership']['configuration_ids'])==4
        assert current['final_verification']['replay'] is None
        assert {r['phase'] for r in current['recommendation']}=={'evaluation','funded'}
        assert all(r['status']=='NO_QUALIFIED_DEPLOYMENT_CANDIDATE' for r in current['recommendation'])
        urls=[f'{PREFIX}/{campaign}/exports/{name}' for name in ('report.json','economic_selection.json','chronological_replay.json','reliability.json','analysis.zip')]
        urls.append(f'{PREFIX}/{campaign}/applications/{app_id}/exports/report.json')
        downloads={}
        for url in urls:
            response=client.get(url);assert response.status_code==200,response.text
            downloads[url]=sha256(response.content).hexdigest()
    def forbidden(*args,**kwargs):raise AssertionError('Saved evidence reopening must not rerun calculations')
    monkeypatch.setattr('alphaquest.robust_research.run_backtest',forbidden)
    monkeypatch.setattr('alphaquest.prop.evaluation_optimization.optimize_evaluation',forbidden)
    monkeypatch.setattr('alphaquest.prop.funded_optimization.optimize_funded',forbidden)
    with TestClient(create_app(database)) as client:
        for url,hash in downloads.items():assert sha256(client.get(url).content).hexdigest()==hash
    assert before==engine_identity()
