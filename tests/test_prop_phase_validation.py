"""Fast independent admission/window boundaries; no production fixture oracles."""
from copy import deepcopy
import pytest

from alphaquest.prop import native_analysis as analysis
from alphaquest.prop import phase_lifecycle as phases


def inputs():
    rows=[dict(trade_id=i,entry_utc=f'2026-01-0{i+4}T18:00:00+00:00',exit_utc=f'2026-01-0{i+4}T18:01:00+00:00',quantity='1',source_net_pnl='3000',export_net_pnl=None,measured_mae='0') for i in range(1,6)]
    plan=dict(source_timezone='UTC',is_start='2026-01-05',is_end='2026-01-09',oos_start='2026-01-12',oos_end='2026-01-13')
    def snapshot(id):
        return dict(backtest=dict(id=id,period_start_utc='2026-01-05T18:00:00+00:00',period_end_utc='2026-01-09T18:02:00+00:00',
            run_metadata=dict(strategy=dict(id='consecutive_green_hold',parameters=dict(contracts=1)),dataset=dict(symbol='NQ'),research=dict(phase='is',plan=plan))),commission_simulation=dict(source_instrument='NQ'))
    return {'a'*32:snapshot('a'*32),'b'*32:snapshot('b'*32)},rows


def install(monkeypatch,snapshots,rows,calls=None):
    def prepare(runs,id,path,settings,zone):
        if calls is not None:calls.append((id,path,zone))
        return deepcopy(snapshots[id]),deepcopy(rows),analysis.resolved_settings(settings)
    monkeypatch.setattr(analysis,'prepare',prepare)


def request(**kwargs):
    return dict(source_backtest_id='a'*32,funded_source_backtest_id='b'*32,settings=dict(ANALYSIS_MODE='dated_lifecycle'),**kwargs)


def test_partial_phase_settings_cannot_select_an_annual_calculation():
    with pytest.raises(ValueError,match='ANALYSIS_MODE'):
        analysis.resolved_settings(dict(FUNDED_MICROS='3'))


def test_aware_utc_instants_required():
    with pytest.raises(ValueError,match='timezone'):
        phases.instant('2026-01-05T18:00:00')


def test_shared_window_excludes_an_already_open_source_position(monkeypatch):
    snapshots,rows=inputs();snapshots['b'*32]['backtest']['period_start_utc']='2026-01-06T18:00:00+00:00'
    rows[1]['entry_utc']='2026-01-06T17:00:00+00:00'  # Already open at shared start.
    install(monkeypatch,snapshots,rows)
    snapshot,selected,settings=phases.prepare_request(None,request())
    assert snapshot['phase_checks']['evaluation_excluded_trades']==2
    c=phases.replay(snapshot,selected,settings)
    assert c['trace'][0]['source_trade_ids']==[]
    assert c['phase_metrics']['evaluation']['pass_date']=='2026-01-07'
    assert c['activation']['funded_start_session']=='2026-01-09'
    assert c['trace'][-1]['source_trade_ids']==[5]
    assert c['trace'][-1]['session_open_utc']=='2026-01-08T23:00:00+00:00'


def test_conflicting_calendars_and_disjoint_windows_reject(monkeypatch):
    snapshots,rows=inputs()
    for i,s in enumerate(snapshots.values()):s['backtest']['run_metadata']['strategy']['session_flattening']=dict(calendar=dict(sha256=str(i)))
    install(monkeypatch,snapshots,rows)
    with pytest.raises(ValueError,match='calendars differ'):phases.prepare_request(None,request())
    snapshots['b'*32]['backtest']['period_start_utc']='2026-02-01T18:00:00+00:00'
    with pytest.raises(ValueError,match='no common research window'):phases.prepare_request(None,request())


def test_inherited_same_source_export_keeps_its_own_timezone(monkeypatch):
    snapshots,rows=inputs();calls=[];install(monkeypatch,snapshots,rows,calls)
    body=request(trade_file='test-only.xlsx',export_timezone='UTC',funded_export_timezone='America/Chicago')
    body['funded_source_backtest_id']='a'*32
    phases.prepare_request(None,body)
    assert [c[2] for c in calls]==['UTC','UTC']
    assert [c[1] for c in calls]==['test-only.xlsx','test-only.xlsx']


def test_overnight_source_cannot_inherit_a_position(monkeypatch):
    snapshots,rows=inputs();rows[0]['exit_utc']='2026-01-06T18:01:00+00:00'
    install(monkeypatch,snapshots,rows)
    with pytest.raises(ValueError,match='intraday flat'):phases.prepare_request(None,request())


def test_every_phase_source_and_selection_participates_in_request_identity():
    from alphaquest.prop.store import request_key
    sources,rows=inputs()
    snapshot=dict(phase_sources=dict(evaluation=sources['a'*32],funded=sources['b'*32]))
    settings=analysis.resolved_settings(dict(ANALYSIS_MODE='dated_lifecycle'))
    key=request_key(snapshot,settings)
    for name,value in [('trades_sha256','changed-trades'),('native_risk',dict(sha256='changed-risk')),
                       ('excursion_input',dict(sha256='changed-export')),('backtest',dict(id='c'*32))]:
        changed=deepcopy(snapshot);changed['phase_sources']['funded'][name]=value
        assert request_key(changed,settings)!=key
    for name,value in [('EVALUATION_MICROS','9'),('FUNDED_MICROS','2'),('ACTIVATION_WAIT_WEEKDAYS','2')]:
        assert request_key(snapshot,{**settings,name:value})!=key
    assert request_key(snapshot,settings)==key
