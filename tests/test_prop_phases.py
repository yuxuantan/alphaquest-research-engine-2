"""Milestone 1: independent dated expectations and normal saved-report workflow."""
import csv
from datetime import date, timedelta
import io
import json
from threading import Event

import pytest

from alphaquest.app import create_app
from alphaquest.prop.phase_lifecycle import prepare_request, replay
from research_fixtures import ResearchClient
from test_prop_analysis_api import wait


def phase_history(days=35, recovery=False):
    lines=['Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol']
    stamp=date(2026,1,5);count=0
    while count<days:
        if stamp.weekday()<5:
            # A 150-point NQ winner = $3000, then 50 points = $1000.
            # On the recovery source the held bar gaps 150 points down and
            # recovers: opening adverse $3000, yet final source net +$3000.
            held='-50,250,-50,250' if recovery else '100,250,100,250'
            for minute,prices in enumerate(['99,100,99,100',held,'300,300,300,300','300,300,300,300']):
                lines.append(stamp.strftime('%m/%d/%Y')+f',18:0{minute},{prices},100,60,40')
            count+=1
        stamp+=timedelta(days=1)
    return ('\n'.join(lines)+'\n').encode()


def save_source(client, *, green=1, recovery=False, days=35, instrument="NQ", contracts=1):
    raw=phase_history(days,recovery)
    point="20" if instrument=="NQ" else "2"
    if instrument=="MNQ":raw=raw.replace(b",100,60,40",b",101,61,40")
    result=client.post('/api/datasets',params=dict(filename='SYNTHETIC-phase-source.csv',name='SYNTHETIC dated phase '+('recovering winner' if recovery else 'arithmetic'),source_timezone='UTC',tick_size='.25',point_value=point,symbol=instrument),content=raw)
    assert result.status_code in (201,409),result.text
    dataset=result.json() if result.status_code==201 else dict(id=result.json()['dataset_id'])
    result=client.post('/api/backtests',json=dict(dataset_id=dataset['id'],strategy_id='consecutive_green_hold',
        strategy_parameters=dict(green_bar_count=green,hold_minutes=1,contracts=contracts),
        execution_settings=dict(initial_capital='10000',tick_size='.25',point_value=point,slippage_ticks=0,commission_per_contract_per_side='0')))
    assert result.status_code==201,result.text
    return result.json()


def phase_request(evaluation, funded=None, **settings):
    return dict(source_backtest_id=evaluation['id'],funded_source_backtest_id=(funded or evaluation)['id'],trade_file='',export_timezone='UTC',
        settings=dict(ANALYSIS_MODE='dated_lifecycle',EVALUATION_MICROS='10',FUNDED_MICROS='3',COMMISSION_MODE='source',SLOTS='1',**settings))


def report_for(client, request):
    checked=client.post('/api/prop-analyses/check',json=request)
    assert checked.status_code==200,checked.text
    response=client.post('/api/prop-analyses',json=request)
    assert response.status_code==202,response.text
    id=response.json()['id'];job=wait(client,id)
    assert job['status']=='complete',job
    return client.get(f'/api/prop-analyses/{id}/downloads/report.json').json()


def test_saved_two_sources_fixed_sizes_and_subsequent_observations(tmp_path):
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        a=save_source(client);b=save_source(client,green=2)
        original={r['id']:client.get(f"/api/backtests/{r['id']}/exports/trades").content for r in (a,b)}
        same=report_for(client,phase_request(a));different=report_for(client,phase_request(a,b))
        for report in [same,different]:
            c=report['calculations'];assert c['phase_metrics']['evaluation']['pass_date']=='2026-01-05'
            assert c['activation']['eligible_session']=='2026-01-06'
            assert c['activation']['funded_start_session']=='2026-01-07'
            assert c['trace'][0]['effective_micros']==10
            assert c['trace'][1]['event']=='activation_eligible'
            first=c['trace'][2]
            assert first['phase']=='funded' and first['source_trade_ids']==[3]
            assert first['effective_micros']==3
            assert c['history'] is None  # Never substitute annualized acquired-funded history.
            assert client.post('/api/prop-analyses',json=phase_request(a,b if report is different else a)).json()['id']==report['id']
            for source in (a,b if report is different else a):
                assert report['id'] in [j['id'] for j in client.get('/api/prop-analyses/sources/'+source['id'],params=dict(discover_exports=False)).json()['analyses']]
            assert client.get(f"/api/prop-analyses/{report['id']}/files/transition_trace.csv").status_code==200
        # Different funded source alone: evaluation/activation identical, sizes
        # 10/3 fixed. A's $900/day pays full six caps by day 30; B's $300/day
        # first reaches safety net + $1500 at session 12, never before.
        assert same['calculations']['phase_metrics']['evaluation']==different['calculations']['phase_metrics']['evaluation']
        assert same['calculations']['phase_metrics']['funded']['trader_payouts']==13000
        assert different['calculations']['trace'][2]['equity']==300
        first=next(t for t in different['calculations']['trace'] if t['trader_payout'])
        assert first['date']=='2026-01-22' and first['trader_payout']==1500
        assert different['calculations']['phase_metrics']['funded']['trader_payouts']==7500
        priced=phase_request(a,b);priced['settings'].update(COMMISSION_MODE='override',COMMISSION_PER_SIDE='1')
        c=report_for(client,priced)['calculations']
        assert c['phase_metrics']['evaluation']['pass_date']=='2026-01-06'
        assert c['activation']['funded_start_session']=='2026-01-08'
        assert c['trace'][3]['equity']==294  # $1000 / 10 - $2 = $98 per MNQ, times three.
        for r in (a,b): assert client.get(f"/api/backtests/{r['id']}/exports/trades").content==original[r['id']]


def test_recovering_winner_breaches_before_recovery(tmp_path):
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        a=save_source(client);recover=save_source(client,recovery=True)
        report=report_for(client,phase_request(recover))
        c=report['calculations'];assert c['outcome']=='account_breach'
        assert c['phase_metrics']['evaluation']['account_breaches']==1
        assert c['phase_metrics']['funded']['sessions']==0
        assert c['trace'][0]['equity']==-3000
        assert c['trace'][0]['source_trade_ids']==[1]
        trades=list(csv.DictReader(io.StringIO(client.get('/api/backtests/'+recover['id']+'/exports/trades').text)))
        assert all(float(t['net_pnl'])==3000 for t in trades)
        body=phase_request(a,recover);body['settings']['FUNDED_MICROS']='10'
        c=report_for(client,body)['calculations']
        assert c['phase_metrics']['funded']['account_breaches']==1
        assert c['trace'][-1]['date']=='2026-01-07' and c['trace'][-1]['equity']==-3000


def test_both_sources_protected_and_modified_funded_identity(tmp_path,monkeypatch):
    import alphaquest.prop.store as store
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        a=save_source(client);b=save_source(client,green=2)
        entered=Event();release=Event();original=store.run_analysis
        def paused(*args,**kwargs):
            entered.set();assert release.wait(15)
            return original(*args,**kwargs)
        monkeypatch.setattr(store,'run_analysis',paused)
        body=phase_request(a,b);job=client.post('/api/prop-analyses',json=body).json()
        assert entered.wait(5)
        try:
            for source in (a,b):assert client.delete('/api/backtests/'+source['id']).status_code==409
            assert client.post('/api/prop-analyses',json=body).json()['id']==job['id']
            assert job['id'] in [r['id'] for r in client.app.state.prop_analyses.list(b['id'])]
        finally:release.set()
        assert wait(client,job['id'])['status']=='complete'
        first=client.get(f"/api/prop-analyses/{job['id']}/downloads/report.json").content
        new=report_for(client,phase_request(a))
        assert new['id']!=job['id']
        assert client.get(f"/api/prop-analyses/{job['id']}/downloads/report.json").content==first


def test_rejection_missing_risk_mixed_windows_and_scaling(tmp_path):
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        a=save_source(client);b=save_source(client,green=2)
        for changes in [dict(EVALUATION_MICROS='0'),dict(FUNDED_MICROS='41'),dict(ACTIVATION_WAIT_WEEKDAYS='0'),dict(MAX_TOTAL_NQ='0.2')]:
            body=phase_request(a,b);body['settings'].update(changes)
            assert client.post('/api/prop-analyses/check',json=body).status_code==422
        # Alter only fixture-owned manifest to exercise declared corruption,
        # uncovered risk and unsupported source-policy rejection.
        runs=client.app.state.runs
        with runs.connect() as db:
            saved=db.execute('SELECT manifest FROM runs WHERE id=?',(b['id'],)).fetchone()[0]
        for change,reason in [('risk','risk coverage'),('research','research phase'),('scaling','size scaling')]:
            record=json.loads(saved)
            if change=='risk':record.pop('intratrade_risk',None)
            if change=='research':record['run_metadata']['research']['phase']='oos'
            if change=='scaling':record['run_metadata']['strategy']['parameters']['use_vol_sizing']=True
            with runs.connect() as db:db.execute('UPDATE runs SET manifest=? WHERE id=?',(json.dumps(record),b['id']))
            response=client.post('/api/prop-analyses/check',json=phase_request(a,b))
            assert response.status_code==422,response.text
            assert reason in response.text,response.text
        with runs.connect() as db:db.execute('UPDATE runs SET manifest=? WHERE id=?',(saved,b['id']))


def replay_case(nets, *, firm='Apex', eval_size='10', funded_size='40', delay='', start='2026-01-05', adverse=None):
    import pandas as pd
    from alphaquest.prop.native_analysis import resolved_settings
    grid=pd.bdate_range(start,periods=len(nets))
    settings=resolved_settings(dict(ANALYSIS_MODE='dated_lifecycle',PROP_FIRM=firm,
        EVALUATION_MICROS=eval_size,FUNDED_MICROS=funded_size,ACTIVATION_WAIT_WEEKDAYS=delay))
    rows=[]
    for i,(stamp,net) in enumerate(zip(grid,nets)):
        date=stamp.date().isoformat();loss,gap=(adverse[i] if adverse else (max(0,-net),False))
        rows.append(dict(trade_id=i+1,entry_utc=date+'T18:00:00+00:00',exit_utc=date+'T18:01:00+00:00',
            quantity='1',source_net_pnl=str(net),export_net_pnl=None,measured_mae=str(loss),
            ohlc_adverse_path=json.dumps([[str(loss),gap]] if loss else [])))
    source=dict(backtest=dict(id='a'*32))
    snapshot=dict(phase_sources=dict(evaluation=source,funded=source),phase_checks=dict(
        start_utc=rows[0]['entry_utc'],end_utc=rows[-1]['exit_utc'],first_session=str(grid[0].date()),last_session=str(grid[-1].date())))
    return replay(snapshot,dict(evaluation=rows,funded=rows),settings)


def test_independent_calendar_delay_expiry_unresolved_and_scaling():
    # Friday pass → Monday eligibility (one waiting weekday) → Tuesday first
    # funded observation. No reuse of Friday's $3000 or Monday's $9000 winner.
    c=replay_case([3000,9000,100,100],start='2026-01-09')
    assert c['activation']['eligible_session']=='2026-01-12'
    assert c['activation']['funded_start_session']=='2026-01-13'
    assert c['trace'][2]['source_trade_ids']==[3] and c['trace'][2]['equity']==200
    assert c['trace'][2]['target_micros']==40 and c['trace'][2]['effective_micros']==20
    # No pass in the 21-weekday Apex lifetime; a daily stop is a soft pause,
    # while a later account floor hit is a distinct terminal outcome.
    c=replay_case([0]*22)
    assert c['outcome']=='evaluation_expired' and len(c['trace'])==21
    assert c['activation']['eligible_session'] is None
    c=replay_case([100,100],adverse=[(1500,False),(1500,False)])
    assert c['trace'][0]['first_limit_hit']=='daily_stop' and c['trace'][0]['equity']==-1000
    assert c['trace'][1]['first_limit_hit']=='account_breach'
    assert c['phase_metrics']['evaluation']['daily_stops']==1
    assert c['phase_metrics']['evaluation']['account_breaches']==1
    assert replay_case([0,0])['outcome']=='evaluation_unresolved'
    assert replay_case([3000,100],delay='3')['outcome']=='activation_pending'
    # Lucid consistency prevents one-day pass; three equal days qualify. Zero
    # additional wait still means the following session, not the passing day.
    c=replay_case([3000]*6,firm='Lucid',eval_size='10',funded_size='3')
    assert c['phase_metrics']['evaluation']['pass_date']=='2026-01-07'
    assert c['activation']['eligible_session']=='2026-01-07'
    assert c['activation']['funded_start_session']=='2026-01-08'
    assert c['trace'][3]['source_trade_ids']==[4] and c['trace'][3]['equity']==900
    assert c['outcome']=='funded_open'
    c=replay_case([1]*24,firm='Lucid',eval_size='10',funded_size='3')
    assert c['outcome']=='evaluation_unresolved'


def save_vwap_source(client, days=35):
    """Second real registered strategy through ordinary dataset/backtest routes."""
    from dataclasses import asdict
    from test_vwap_pullback import scenario, parameters
    from alphaquest.reporting import json_value
    stamp=date(2026,1,5);count=0
    base=scenario();lines=['Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol']
    while count<days:
        if stamp.weekday()<5:
            for bar in base:
                utc=bar.timestamp_utc.replace(year=stamp.year,month=stamp.month,day=stamp.day)
                lines.append(','.join([utc.strftime('%m/%d/%Y'),utc.strftime('%H:%M'),*bar.source_fields[2:]]))
            count+=1
        stamp+=timedelta(days=1)
    response=client.post('/api/datasets',params=dict(filename='SYNTHETIC-phase-vwap.csv',name='SYNTHETIC dated VWAP phase',source_timezone='UTC',tick_size='.25',point_value='20',symbol='NQ'),content=('\n'.join(lines)+'\n').encode())
    assert response.status_code==201,response.text
    response=client.post('/api/backtests',json=dict(dataset_id=response.json()['id'],strategy_id='vwap_pullback_risk_sizing',
        strategy_parameters=json.loads(json.dumps(asdict(parameters(day_reset_time=700)),default=json_value)),execution_settings=dict(initial_capital='10000',tick_size='.25',point_value='20',slippage_ticks=0,commission_per_contract_per_side='0')))
    assert response.status_code==201,response.text
    return response.json()


def test_mixed_nq_mnq_sources_normalize_quantity_once(tmp_path):
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        nq=save_source(client)
        mnq=save_source(client,instrument='MNQ',contracts=10)
        # Same 150-point move: $20 * 1 NQ = $2 * 10 MNQ = $3000.
        # Three simulated MNQ must make exactly $900 in either funded source.
        c=report_for(client,phase_request(nq,mnq))
        assert c['source']['phase_sources']['funded']['phase_suitability']['instrument']=='MNQ'
        assert c['calculations']['trace'][2]['equity']==900
        assert c['calculations']['phase_metrics']['funded']['trader_payouts']==13000
        (tmp_path/'mixed-instrument-report.json').write_text(json.dumps(c,indent=2))
