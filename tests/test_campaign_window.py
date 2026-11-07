"""Campaign defaults use common observed IS bar coverage, never trade bounds."""
from copy import deepcopy
from datetime import date,timedelta
import json
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from alphaquest.app import create_app
from alphaquest.research_campaigns import CampaignStore,SourceWindowRequest
from test_optimization import wait_job
from test_research_campaigns import declaration,create,run


def window_history():
    rows=['Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol']
    days=[date(2020,12,31)]
    d=date(2021,1,4)
    while d<=date(2021,2,5):
        if d.weekday()<5 and d!=date(2021,1,18):days.append(d)
        d+=timedelta(days=1)
    for d in days:
        # Chicago 17:01 on the previous civil date belongs to session d.
        # At the IS edges green=2 has no entry; green=1 still wins $3000.
        held='250,250,250,250' if d in (date(2021,1,4),date(2021,1,15)) else '100,250,100,250'
        for minute,prices in enumerate(('99,100,99,100',held,'300,300,300,300','300,300,300,300'),1):
            rows.append((d-timedelta(days=1)).strftime('%m/%d/%Y')+f',23:0{minute},{prices},100,60,40')
    return ('\n'.join(rows)+'\n').encode()


def saved_window_grid(client):
    response=client.post('/api/datasets',params=dict(filename='SYNTHETIC-IS-window.csv',
        name='SYNTHETIC declared versus observed IS coverage',source_timezone='UTC',symbol='NQ',
        tick_size='.25',point_value='20'),content=window_history())
    assert response.status_code==201,response.text
    response=client.post('/api/optimizations',json=dict(dataset_id=response.json()['id'],
        strategy_id='consecutive_green_hold',method='exhaustive',workers=1,automatic_prop=False,
        parameter_ranges=dict(green_bar_count=dict(start=1,end=2,step=1),
            hold_minutes=dict(start=1,end=1,step=0),contracts=dict(start=1,end=1,step=0)),
        execution_settings=dict(initial_capital='10000',slippage_ticks=0,commission_per_contract_per_side='0'),
        sample_split=dict(mode='dates',is_start='2021-01-01',is_end='2021-01-17',
            oos_start='2021-01-18',oos_end='2021-02-04')))
    assert response.status_code==202,response.text
    job=wait_job(client,response.json()['id']);assert job['status']=='complete',job
    rows=client.get(f"/api/optimizations/{job['id']}/results").json()['items']
    records=[client.get('/api/backtests/'+r['run_id']).json() for r in rows]
    return sorted(records,key=lambda r:r['run_metadata']['strategy']['parameters']['green_bar_count']),job,rows


def record(id,start,end,plan_start='2021-01-01',plan_end='2021-01-17',phase='is'):
    return dict(id=id,status='complete',period_start_utc=start,period_end_utc=end,
        run_metadata=dict(research=dict(phase=phase,plan=dict(is_start=plan_start,is_end=plan_end))))


def test_common_window_uses_session_dates_and_declared_is_intersection():
    a,b='a'*32,'b'*32
    records={a:record(a,'2021-01-03T23:01:00Z','2021-01-14T23:04:00Z'),
        b:record(b,'2021-01-05T23:01:00Z','2021-01-13T23:04:00Z',plan_end='2021-01-13')}
    store=CampaignStore(SimpleNamespace(read_source_record=lambda id:records[id]),None,None)
    body=SourceWindowRequest(sources=[dict(backtest_id=id,sizes=[1]) for id in (a,b)])
    result=store.source_window(body)
    assert result['is_window']==dict(first_session='2021-01-06',last_session='2021-01-13')
    assert result['sources'][0]['saved_coverage']==dict(first_session='2021-01-04',last_session='2021-01-15')
    records[b]['period_start_utc']='2021-01-18T23:01:00Z'
    records[b]['period_end_utc']='2021-01-19T23:04:00Z'
    with pytest.raises(ValueError,match='no common saved IS coverage'):store.source_window(body)
    records[b]['run_metadata']['research']['phase']='oos'
    with pytest.raises(ValueError,match='OOS'):store.source_window(body)


@pytest.mark.parametrize('stamp,expected',[
    ('2021-03-14T22:01:00Z','2021-03-15'), # Chicago DST Sunday 17:01.
    ('2021-11-07T23:01:00Z','2021-11-08'), # Chicago standard-time Sunday 17:01.
])
def test_session_date_dst_boundaries(stamp,expected):
    id='a'*32
    r=record(id,stamp,stamp,plan_start='2021-01-01',plan_end='2021-12-31')
    store=CampaignStore(SimpleNamespace(read_source_record=lambda _:r),None,None)
    result=store.source_window(SourceWindowRequest(sources=[dict(backtest_id=id,sizes=[1])]))
    assert result['is_window']==dict(first_session=expected,last_session=expected)


@pytest.fixture(scope='module')
def window_library(tmp_path_factory):
    root=tmp_path_factory.mktemp('window-library')
    with TestClient(create_app(root/'datasets.sqlite3')) as client:
        yield client,*saved_window_grid(client),root


def test_normal_metadata_window_job_trials_zero_trade_edges_and_no_side_effects(window_library,monkeypatch):
    client,records,job,rows,root=window_library
    def forbidden(*a,**kw):pytest.fail('Default window must not load trades/datasets or perform source/simulation checks')
    with monkeypatch.context() as m:
        m.setattr('alphaquest.prop.source.prepare_source',forbidden)
        m.setattr('alphaquest.prop.phase_search.check_candidates',forbidden)
        m.setattr(client.app.state.store,'get',forbidden)
        requests=[dict(backtest_id=r['id'],sizes=[1]) for r in records]
        for sources in ([requests[0]],[requests[1]],requests,
                [dict(optimization_id=job['id'],sizes=[1])],
                [dict(optimization_id=job['id'],trials=[rows[0]['trial']],sizes=[1])]):
            response=client.post('/api/research-campaigns/source-window',json=dict(sources=sources))
            assert response.status_code==200,response.text
            assert response.json()['is_window']==dict(first_session='2021-01-04',last_session='2021-01-15')
        assert client.get('/api/research-campaigns').json()['items']==[]
    with (root/'backtest_runs'/records[1]['id']/'trades.csv').open() as stream:
        import csv
        trades=list(csv.DictReader(stream))
    assert len(trades)==8
    assert trades[0]['entry_time_utc'].startswith('2021-01-04') # session Jan 5, after first observed session.
    invalid=client.post('/api/research-campaigns/source-window',json=dict(sources=[dict(optimization_id=job['id'],trials=[9999],sizes=[1])]))
    assert invalid.status_code==422 and 'does not exist' in invalid.text


@pytest.mark.parametrize('phase',['evaluation','funded'])
def test_derived_window_normal_run_downloads_and_explicit_bounds_still_validate(window_library,phase):
    client,records,job,rows,root=window_library
    body=declaration(records[0],phase=phase)
    body['sources'][0]['sizes']=[10 if phase=='evaluation' else 3]
    body['search_settings']['calendar']=dict(start_dates=['2021-01-04'])
    # The old populated split fails exactly as reported; no request is silently clipped.
    response=client.post('/api/research-campaigns',json=body)
    assert response.status_code==422 and 'Research period lies outside' in response.text
    body['is_window']=client.post('/api/research-campaigns/source-window',json=dict(sources=body['sources'])).json()['is_window']
    campaign=run(client,create(client,body)['campaign_id'])
    report=client.get(f"/api/research-campaigns/{campaign['campaign_id']}/exports/report.json").json()
    row=report['calculations']['candidates'][0]
    assert row['manifest']['source']['profile_research_period']['weekdays']==10
    assert row['manifest']['configuration']['period']==dict(first_session='2021-01-04',last_session='2021-01-15')
    if phase=='evaluation':assert row['metrics']['cost_per_funded']==70 and row['metrics']['expected_calendar_days_to_funded']==2
    else:assert row['metrics']['expected_payouts']==row['metrics']['expected_pending_cash']==1500
    # Explicit valid overrides are unchanged, including in the saved concrete request.
    custom=deepcopy(body);custom['campaign_id']=uuid4().hex
    custom['is_window']=dict(first_session='2021-01-05',last_session='2021-01-14')
    assert create(client,custom)['manifest']['request']['candidates'][0]['period']==custom['is_window']
    (root/(phase+'-window.json')).write_text(json.dumps(dict(campaign=campaign['campaign_id'],analysis=campaign['analysis_id'],period=body['is_window']),indent=2))
