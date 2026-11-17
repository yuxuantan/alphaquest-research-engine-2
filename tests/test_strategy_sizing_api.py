"""Real Twin backtest -> independent phase source/check/run/sealed downloads."""
from dataclasses import asdict,replace
from datetime import date,datetime,time,timedelta
from decimal import Decimal as D
from pathlib import Path
from uuid import uuid4
import json,os
import pytest
from alphaquest.app import create_app
from alphaquest.session_calendar import CT
from alphaquest.strategies.twin_continuation import Parameters
from research_fixtures import ResearchClient
from test_twin_continuation import breakout_rows
from test_optimization import wait_job
from test_native_replay_api import wait
from test_native_phase_campaigns import declaration
from alphaquest.prop.sizing_search import PercentageGrid


def twin_source(client, *, with_oos=False):
    parameters=Parameters(max_bars_back=0,use_momentum=False,bo_pivot_tf=15,bo_atr_period=1)
    pattern=breakout_rows();lines=['Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol']
    first=date(2026,1,5)
    days=[first+timedelta(days=offset) for offset in range(12 if with_oos else 5)]
    for day in days:
        if day.weekday()>=5:continue
        start=datetime.combine(day-timedelta(days=1),time(17,1),CT)
        for minute in range(1380):
            stamp=start+timedelta(minutes=minute)
            values=(pattern[minute].open,pattern[minute].high,pattern[minute].low,pattern[minute].close) if minute<len(pattern) else (126,127,125,126)
            lines.append(','.join([stamp.strftime('%m/%d/%Y'),stamp.strftime('%H:%M'),*map(str,values),'100','50','50']))
    raw=('\n'.join(lines)+'\n').encode()
    saved=client.post('/api/datasets',params=dict(filename='SYNTHETIC-twin-sizing.csv',name='SYNTHETIC Twin sizing contract',symbol='MNQ',source_timezone='America/Chicago',tick_size='.25',point_value='2'),content=raw)
    assert saved.status_code==201,saved.text
    values={k:str(v) if isinstance(v,D) else v for k,v in asdict(parameters).items()}
    response=client.post('/api/optimizations',json=dict(dataset_id=saved.json()['id'],strategy_id='twin_continuation',method='exhaustive',workers=1,automatic_prop=False,
        parameter_ranges={k:dict(start=v,end=v,step='0' if isinstance(v,str) else 0) for k,v in values.items()},execution_settings=dict(initial_capital='10000',slippage_ticks=0,commission_per_contract_per_side='0'),
        **(dict(sample_split=dict(mode='dates',is_start='2026-01-04',is_end='2026-01-09',oos_start='2026-01-11',oos_end='2026-01-16')) if with_oos else {})))
    assert response.status_code==202,response.text
    job=wait_job(client,response.json()['id']);assert job['status']=='complete',job
    row,=client.get('/api/optimizations/'+job['id']+'/results').json()['items']
    record=client.get('/api/backtests/'+row['run_id']).json()
    return record,raw


@pytest.mark.parametrize('phase',['evaluation','funded'])
@pytest.mark.parametrize('profile',['apex-50k-eod','lucidflex-50k'])
def test_twin_native_percentage_both_account_profiles_and_phases(tmp_path,phase,profile):
    destination=os.environ.get('ALPHAQUEST_STRATEGY_SIZING_EVIDENCE_DIR')
    library=Path(destination)/f'{profile}-{phase}'/'library' if destination else tmp_path
    with ResearchClient(create_app(library/'datasets.sqlite3')) as client:
        record,raw=twin_source(client)
        request=declaration(client,record,phase)
        request['is_window']=dict(first_session='2026-01-05',last_session='2026-01-09')
        request['profile'].update(profile_id=profile,rule_version=__import__('alphaquest.prop.phase_profiles',fromlist=['rule_version']).rule_version(profile))
        if profile=='lucidflex-50k' and phase=='evaluation':request['profile']['activation_fee']='0'
        request['simulation']['simulations']=8
        request['costs']=dict(mode='override',broker='synthetic',per_side='0',instrument='auto')
        if phase=='evaluation':request['sampling'].update(chain_simulations=8,chain_seed=1732)
        request['search_settings']['native_execution'].update(model='native_percentage_observed_blocks_v2',horizon_calendar_days=64 if phase=='evaluation' else 30)
        request['search_settings']['calendar']['start_dates']=['2026-02-02']
        request['search_settings']['calendar']['coverage_end']='2026-12-31'
        if phase=='funded':request['search_settings']['horizon_calendar_days']=30
        grid=PercentageGrid(minimum='.2',maximum='.2',step='.1',maximum_contracts=40)
        request['sources'][0].update(sizes=[40],sizing_policies=[asdict(p) for p in grid.policies(dict(tick_size='.25',point_value='2',commission_per_contract_per_side='0'))])
        created=client.post('/api/research-campaigns',json=request)
        assert created.status_code==201,created.text
        campaign_id=created.json()['campaign_id']
        checked=client.post(f'/api/research-campaigns/{campaign_id}/check')
        assert checked.status_code==200,checked.text
        launched=client.post(f'/api/research-campaigns/{campaign_id}/run')
        assert launched.status_code==202,launched.text
        analysis_id=launched.json()['analysis_id'];wait(client,analysis_id)
        report=client.get(f'/api/prop-analyses/{analysis_id}/downloads/report.json').json()
        candidate,=report['calculations']['candidates']
        assert candidate['quantity_summary']['admitted_entries']>0
        assert len(candidate['native_forecast']['paths'])==8
        assert candidate['manifest']['native_source_check']['source_check']['sizing_capabilities']['percentage_risk']['supported']
        assert candidate['native_forecast']['captures']
        # Reopen sealed evidence rather than run the numerical owner again.
        assert client.get(f'/api/prop-analyses/{analysis_id}/downloads/report.json').json()==report
        archive=client.get(f'/api/research-campaigns/{campaign_id}/exports/analysis.zip')
        assert archive.status_code==200
        if destination:=os.environ.get('ALPHAQUEST_STRATEGY_SIZING_EVIDENCE_DIR'):
            target=Path(destination)/f'{profile}-{phase}';target.mkdir(parents=True,exist_ok=True)
            (target/'SYNTHETIC-source.csv').write_bytes(raw)
            (target/'request.json').write_text(json.dumps(request,indent=2))
            (target/'source.json').write_text(json.dumps(record,indent=2))
            (target/'report.json').write_text(json.dumps(report,indent=2))
            (target/'analysis.zip').write_bytes(archive.content)


def test_twin_saved_fixed_path_searches_share_capabilities_for_both_phases(tmp_path):
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        record,_=twin_source(client)
        for profile in ['apex-50k-eod','lucidflex-50k']:
            for phase in ['evaluation','funded']:
                request=declaration(client,record,phase)
                request['search_settings'].pop('native_execution')
                request['search_settings']['calendar']['coverage_end']='2036-12-31'
                request['is_window']=dict(first_session='2026-01-05',last_session='2026-01-09')
                request['profile'].update(profile_id=profile,rule_version=__import__('alphaquest.prop.phase_profiles',fromlist=['rule_version']).rule_version(profile))
                if profile=='lucidflex-50k' and phase=='evaluation':request['profile']['activation_fee']='0'
                request['simulation']['simulations']=8
                if phase=='evaluation':request['sampling'].update(chain_simulations=8,chain_seed=request['simulation']['seed'] if profile=='lucidflex-50k' else 1732)
                created=client.post('/api/research-campaigns',json=request);assert created.status_code==201,created.text
                campaign=created.json()['campaign_id']
                launched=client.post(f'/api/research-campaigns/{campaign}/run');assert launched.status_code==202,launched.text
                wait(client,launched.json()['analysis_id'])
                rows=client.get(f'/api/research-campaigns/{campaign}/exports/results.json').json()['candidates']
                assert len(rows)==2
                for row in rows:
                    support=row['manifest']['source']['phase_suitability']['sizing_capabilities']
                    assert support['fixed_contracts']['supported']


def test_twin_frozen_native_oos_keeps_policy_and_creates_actual_controlled_backtest(tmp_path):
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        record,_=twin_source(client,with_oos=True)
        oos=client.post('/api/backtests/'+record['id']+'/oos',json=dict(request_id=uuid4().hex))
        assert oos.status_code==201,oos.text
        request=declaration(client,record,'funded')
        request['is_window']=dict(first_session='2026-01-05',last_session='2026-01-09')
        request['simulation']['simulations']=8
        request['costs']=dict(mode='override',broker='synthetic',per_side='0',instrument='auto')
        request['search_settings'].update(horizon_calendar_days=5)
        request['search_settings']['calendar'].update(start_dates=['2026-02-02'],coverage_end='2026-03-10')
        request['search_settings']['native_execution'].update(model='native_percentage_observed_blocks_v2',horizon_calendar_days=5)
        grid=PercentageGrid(minimum='.8',maximum='.8',step='.1',maximum_contracts=40)
        request['sources'][0].update(sizes=[40],sizing_policies=[asdict(p) for p in grid.policies(dict(tick_size='.25',point_value='2',commission_per_contract_per_side='0'))])
        created=client.post('/api/research-campaigns',json=request);assert created.status_code==201,created.text
        campaign=created.json()['campaign_id']
        launched=client.post(f'/api/research-campaigns/{campaign}/run');assert launched.status_code==202,launched.text
        wait(client,launched.json()['analysis_id'])
        results=client.get(f'/api/research-campaigns/{campaign}/exports/results.json').json()
        candidate,=results['candidates']
        frozen=client.post(f'/api/research-campaigns/{campaign}/freeze',json=dict(candidate_ids=[candidate['candidate_id']],rationale='Synthetic causal Twin policy; retain the IS choice for OOS.'))
        assert frozen.status_code==200,frozen.text
        before=frozen.json()
        assessed=client.post(f'/api/research-campaigns/{campaign}/assessments',json=dict(request_id=uuid4().hex))
        assert assessed.status_code==202,assessed.text
        wait(client,assessed.json()['analysis_id'])
        report=client.get(f"/api/prop-analyses/{assessed.json()['analysis_id']}/downloads/report.json").json()
        calculation=report['calculations'];row,=calculation['candidates']
        assert calculation['selection_status']=='assessment_only_no_reselection'
        assert row['frozen_candidate_id']==candidate['candidate_id']
        assert row['native_chronological_replay']['historical_paths']==1
        assert row['quantity_summary']['admitted_entries']>0
        assert client.get('/api/backtests/'+row['native_backtest_id']).status_code==200
        assert client.get(f'/api/research-campaigns/{campaign}/exports/frozen_package.json').json()==before
