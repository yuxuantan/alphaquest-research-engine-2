"""Actual native current policy → supplied dynamic decisions → immutable report."""
from copy import deepcopy
from datetime import date,datetime,timedelta,timezone
from decimal import Decimal
from hashlib import sha256
import json
from time import monotonic,sleep
from uuid import uuid4
from zoneinfo import ZoneInfo

from alphaquest.app import create_app
from research_fixtures import ResearchClient
from native_replay_fixtures import bars
from test_native_replay_api import source
from test_native_nested_economics import native_nested_declaration
from test_robust_research_api import PREFIX
from test_research_procedure_api import wait_application
from tests.test_forward_api import wait_monitor


def march_market():
    """Sixteen genuine full session templates, no calendar-derived missing bars.

    Source one-MNQ entry118→target268 =300/session. A one-contract baseline
    cannot clear the2100 safety cushion in five sessions. Dynamic larger policy
    has five qualifying profit days, requesting1500 under the saved model.
    """
    zone=ZoneInfo('America/Chicago');template=bars(days=1,payout=True)
    lines=['Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol'];day=date(2026,3,2)
    for _ in range(16):
        while day.weekday()>4:day+=timedelta(days=1)
        for bar in template:
            old=bar.timestamp_utc.astimezone(zone)
            local=datetime.combine(day+(old.date()-date(2026,1,5)),old.time(),zone)
            stamp=local.astimezone(timezone.utc)
            lines.append(','.join([stamp.strftime('%m/%d/%Y'),stamp.strftime('%H:%M'),*bar.source_fields[2:]]))
        day+=timedelta(days=1)
    return ('\n'.join(lines)+'\n').encode()


def dynamic_current(client):
    original=source(client,raw=march_market())
    assert Decimal(original['summary']['total_net_pnl'])==4800
    request=native_nested_declaration(client,original)
    study=request['economic_studies'][0]
    policy=deepcopy(study['policies'][1]);policy['sizing']['policy']['risk_percent']='0.8'
    study['policies']=[policy];study['search_settings']['receipt_delay_calendar_days']=0
    request['folds'].update(outer_train_sessions=6,outer_test_sessions=5,inner_train_sessions=2)
    request['reliability']=dict(client.get(PREFIX+'/defaults').json()['reliability'],minimum_outer_blocks=2,
        minimum_calibration_blocks=2,historical_bootstrap_replicates=400)
    checked=client.post(PREFIX+'/preview',json=request);assert checked.status_code==200,checked.text
    candidate,=checked.json()['candidates']
    request['baselines']=[dict(id='Predeclared native one MNQ',source_configuration_id=candidate['id'],phase='funded',
        profile=study['profiles'][0],policy=dict(micros=1),required=True)]
    response=client.post(PREFIX,json=request);assert response.status_code==201,response.text
    campaign=response.json()['campaign_id'];launched=client.post(PREFIX+'/'+campaign+'/run');assert launched.status_code==202,launched.text
    deadline=monotonic()+240
    while monotonic()<deadline:
        current=client.get(PREFIX+'/'+campaign).json()
        if current['status'] not in ('queued','running'):break
        sleep(.05)
    assert current['status']=='complete',current
    reliability=current['result']['reliability']['phases']['funded']
    assert reliability['status']=='ASSESSABLE_WITH_LIMITATIONS',reliability
    assert reliability['scalar_metrics']['mean_cash_received']==1500
    assert reliability['baseline_comparisons'][0]['paired_mean_improvement']==1500
    preview=client.post(f'{PREFIX}/{campaign}/procedure/preview',json={});assert preview.status_code==200,preview.text
    response=client.post(f'{PREFIX}/{campaign}/procedure/freeze',json=dict(procedure_id=uuid4().hex,expected_preview_sha256=preview.json()['preview_sha256']))
    assert response.status_code==201,response.text
    application_id=uuid4().hex
    response=client.post(f'{PREFIX}/{campaign}/development-selection/run',json=dict(request_id=application_id,procedure_sha256=response.json()['procedure_sha256']))
    assert response.status_code==202,response.text
    application=wait_application(client,campaign,application_id)
    recommendation,=application['result']['recommendation']
    assert recommendation['status']=='RESEARCH_CANDIDATE_ONLY',recommendation
    package,=recommendation['selected_packages']
    assert package['configuration']['sizing']['policy']['kind']=='percentage_risk'
    assert Decimal(package['configuration']['sizing']['policy']['risk_percent'])==Decimal('.8')
    return original,campaign,application,package


def observed_decisions(start,*,wrong_quantity=False):
    """Independent price/cost ledger:10*(-5)*2=-100;9*10*2=180."""
    def clock(n):return (start+timedelta(microseconds=n)).isoformat().replace('+00:00','Z')
    events=[];balance=Decimal(50000)
    def emit(n,kind,**fields):events.append(dict(event_id=f'e{n}',source_sequence=n+1,event_time_utc=clock(n),kind=kind,**fields))
    for index,(quantity,exit_price,net) in enumerate([(10,'95',-100),(9,'110',180)]):
        n=index*20;signal=f's{index}';closing=f'c{index}';oid=f'o{index}'
        emit(n,'position',signed_quantity=0,account_balance=str(balance))
        emit(n+1,'signal',signal_id=signal,side='buy',quantity=quantity,reference_price='100',stop_price='80')
        emit(n+2,'sizing_decision',signal_id=signal,position_event_id=f'e{n}',context_known_at_utc=clock(n),
            account_state=dict(initial_configured_capital='50000',equity_change_from_initial=str(balance-50000),
                account_floor_from_initial='-2000',daily_floor_from_initial=None,provider_max_contracts=20,user_max_contracts=40),
            execution_timing='next_open',side='long',decision_reference_price='100',initial_stop_price='80',
            initial_stop_known_at_utc=clock(n+1),submitted_quantity=quantity-1 if wrong_quantity and index==0 else quantity,action='trade')
        emit(n+3,'intent',intent_id=f'i{index}',signal_id=signal,side='buy',quantity=quantity,reference_price='100',stop_price='80')
        emit(n+4,'order',order_id=oid,intent_id=f'i{index}',side='buy',quantity=quantity,execution_kind='paper')
        emit(n+5,'order_status',order_id=oid,status='acknowledged')
        emit(n+6,'fill',fill_id=f'f{index}',order_id=oid,side='buy',quantity=quantity,price='100',commission='0',execution_kind='paper')
        emit(n+7,'protection',protective_order_id=f'p{index}',order_id=oid,protection_type='stop',side='sell',quantity=quantity,trigger_price='80',status='active')
        emit(n+8,'signal',signal_id=closing,side='sell',quantity=quantity,reference_price=exit_price)
        emit(n+9,'intent',intent_id=f'j{index}',signal_id=closing,side='sell',quantity=quantity,reference_price=exit_price)
        emit(n+10,'order',order_id=f'x{index}',intent_id=f'j{index}',side='sell',quantity=quantity,execution_kind='paper')
        emit(n+11,'order_status',order_id=f'x{index}',status='acknowledged')
        emit(n+12,'fill',fill_id=f'y{index}',order_id=f'x{index}',side='sell',quantity=quantity,price=exit_price,commission='0',execution_kind='paper')
        emit(n+13,'protection',protective_order_id=f'p{index}',order_id=oid,protection_type='stop',side='sell',quantity=quantity,trigger_price='80',status='cancelled')
        balance+=net
    emit(40,'position',signed_quantity=0,account_balance=str(balance));emit(41,'market',price='110');emit(42,'heartbeat');emit(43,'connection',status='connected')
    return events


def test_actual_native_current_percentage_policy_reconciles_supplied_arithmetic_and_freezes_report(tmp_path,monkeypatch):
    database=tmp_path/'datasets.sqlite3'
    with ResearchClient(create_app(database)) as client:
        original,campaign,application,package=dynamic_current(client)
        monitor=uuid4().hex
        body=dict(monitor_id=monitor,name='SYNTHETIC supplied dynamic arithmetic; actual current native policy',observation_kind='synthetic_harness',
            policy_binding=dict(campaign_id=campaign,application_id=application['application_id'],phase='funded',package_sha256=package['package_sha256']),
            source=dict(source_id='dynamic-paper',label='SYNTHETIC supplied paper events, no platform connection'),
            instrument=dict(symbol='MNQ',tick_size='.25',point_value='2'),thresholds=dict(maximum_position_contracts=40))
        checked=client.post('/api/forward-monitors/check',json=body);assert checked.status_code==200,checked.text
        response=client.post('/api/forward-monitors',json=body);assert response.status_code==201,response.text
        url='/api/forward-monitors/'+monitor;start=datetime.now(timezone.utc)
        events=observed_decisions(start)
        for event in events:
            if 'execution_kind' in event:event['execution_kind']='synthetic'
        raw=json.dumps(dict(schema_version='aq-forward-events-v1',source_id='dynamic-paper',batch_id=uuid4().hex,events=events)).encode()
        response=client.post(url+'/events',content=raw);assert response.status_code==201,response.text
        response=client.post(url+'/assess',json=dict(request_id=uuid4().hex,as_of_utc=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')))
        assert response.status_code==200,response.text
        report,original_report=wait_monitor(client,response.json()['id']);result=report['calculations']
        assert result['advisory']['state']=='ACTIVE',result
        assert result['forward_evidence']['status']=='SYNTHETIC_ONLY'
        assert result['policy_conformance']['status']=='MATCH',result['policy_conformance']
        decisions=result['policy_conformance']['decisions']
        assert [r['recalculated']['quantity'] for r in decisions]==[10,9]
        assert [Decimal(r['recalculated']['denominator_value']) for r in decisions]==[50000,49900]
        assert all(Decimal(r['recalculated']['planned_risk_per_mnq'])==40 for r in decisions)
        assert Decimal(result['metrics']['net_realized_pnl'])==80
        assert Decimal(result['metrics']['net_trading_equity'])==50080
        assert result['policy_conformance']['supplied_context_independently_verified'] is False
        assert result['forecast_comparison']['status']=='NOT_COMPARABLE' # No complete horizon asserted.
        # Append a new immutable correction to the submitted quantity. This must
        # not silently repair or overwrite the previously saved MATCH snapshot.
        corrected=deepcopy(events[2]);corrected.update(event_id='incorrect-size-correction',supersedes_event_id=events[2]['event_id'],correction_reason='SYNTHETIC quantity discrepancy probe',submitted_quantity=9)
        response=client.post(url+'/events',content=json.dumps(dict(schema_version='aq-forward-events-v1',source_id='dynamic-paper',batch_id=uuid4().hex,events=[corrected])).encode())
        assert response.status_code==201,response.text
        response=client.post(url+'/assess',json=dict(request_id=uuid4().hex,as_of_utc=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')))
        changed,_=wait_monitor(client,response.json()['id'])
        assert changed['calculations']['policy_conformance']['status']=='MISMATCH'
        assert changed['calculations']['advisory']['state']=='PAUSED'
        assert client.get('/api/prop-analyses/'+report['id']+'/downloads/report.json').content==original_report
        (tmp_path/'dynamic-monitor-request.json').write_text(json.dumps(body,indent=2))
        (tmp_path/'dynamic-monitor-events.json').write_bytes(raw)
        (tmp_path/'dynamic-monitor-report.json').write_bytes(original_report)
        (tmp_path/'dynamic-monitor-evidence.json').write_text(json.dumps(dict(source_id=original['id'],campaign_id=campaign,
            application_id=application['application_id'],monitor_id=monitor,analysis_id=report['id'],
            discrepancy_analysis_id=changed['id'],report_sha256=sha256(original_report).hexdigest(),
            expected=dict(quantities=[10,9],balances=[50000,49900],planned_unit_risk=40,trading_profit=80,final_equity=50080),
            library=str(tmp_path)),indent=2))
    with ResearchClient(create_app(database)) as client:
        def forbidden(*args,**kwargs):raise AssertionError('Saved forward read recalculated')
        monkeypatch.setattr('alphaquest.forward_monitoring.reconcile',forbidden)
        assert client.get('/api/prop-analyses/'+report['id']+'/downloads/report.json').content==original_report
