"""Current procedure → supplied synthetic events → immutable advisory snapshots."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from hashlib import sha256
import io
import json
from uuid import uuid4
import zipfile

import httpx
from test_backtests_browser import browser,page,playwright
from test_research_procedure_browser import portal
from test_forward_api import current_policy
from test_forward_reconcile import fixture


def utc():return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')


def event_file(tmp_path,name,events,*,batch_id=None):
    path=tmp_path/name
    path.write_text(json.dumps(dict(schema_version='aq-forward-events-v1',source_id='synthetic-observer',batch_id=batch_id or uuid4().hex,events=events),indent=2))
    return path


def import_file(page,path):
    page.locator('#forward-events-file').set_input_files(path)
    page.locator('#forward-events-check').click()
    playwright.expect(page.locator('#forward-events-import')).to_be_enabled(timeout=30000)
    page.locator('#forward-events-import').click()
    playwright.expect(page.locator('#forward-event-status')).to_contain_text('Imported',timeout=30000)


def assess(page,portal):
    page.locator('#forward-use-now').click();page.locator('#forward-assess').click()
    playwright.expect(page.locator('#prop-heading-title')).to_have_text('Forward observation assessment',timeout=30000)
    id=page.url.rsplit('/',1)[-1]
    response=page.request.get(portal['url']+f'/api/prop-analyses/{id}/downloads/report.json')
    assert response.ok,response.text()
    return response.json(),response.body()


def monitor(page):
    page.get_by_role('link',name='Open monitor · new events and advisory controls',exact=True).click()
    playwright.expect(page.locator('#forward-monitor-state')).to_be_visible()


def test_current_policy_supplied_events_corrections_and_acknowledged_recovery(page,portal,tmp_path):
    with httpx.Client(base_url=portal['url'],timeout=300) as client:
        dataset,campaign,application,package=current_policy(client)
    page.goto(portal['url']+'/#backtests/prop/job/'+application['analysis_id'])
    page.locator('#forward-launcher > summary').click()
    page.locator('#forward-name').fill('SYNTHETIC current-policy observation arithmetic')
    page.locator('#forward-policy').select_option(package['package_sha256'])
    page.locator('#forward-source-id').fill('synthetic-observer')
    page.locator('#forward-source-label').fill('SYNTHETIC independently supplied events, no broker connection')
    playwright.expect(page.locator('#forward-maximum_position_contracts')).to_have_value('3')
    page.locator('#forward-check').click()
    playwright.expect(page.locator('#forward-create')).to_be_enabled(timeout=30000)
    playwright.expect(page.locator('#forward-admission')).to_contain_text('authoritative_current_procedure_policy')
    page.locator('#forward-source-check').screenshot(path=str(tmp_path/'current-policy-observation-check.png'))
    page.locator('#forward-create').click()
    playwright.expect(page.locator('#forward-monitor-state')).to_be_visible()
    monitor_id=page.url.rsplit('/',1)[-1];base=portal['url']+'/api/forward-monitors/'+monitor_id
    saved=page.request.get(base).json();assert saved['declaration']['observation_kind']=='synthetic_harness'
    start=datetime.now(timezone.utc);events=fixture()
    for i,event in enumerate(events):
        event['event_time_utc']=(start+timedelta(microseconds=i*10)).isoformat().replace('+00:00','Z')
        if event.get('quantity')==2:event['quantity']=3
        if event['kind']=='fill':event['commission']='1.5'
        if event['kind']=='position' and event.get('account_balance')=='50002':event['account_balance']='50003'
    for i,(category,amount,id,extra) in enumerate([('payout_request','50','request',dict(request_amount_basis='trader_entitlement')),('provider_deduction','60','deduction',dict(related_cash_event_id='request')),('trader_receipt','50','receipt',dict(related_cash_event_id='request'))],17):
        events.append(dict(event_id='event-'+str(i),source_sequence=i+1,event_time_utc=(start+timedelta(microseconds=i*10)).isoformat().replace('+00:00','Z'),kind='cash',cash_event_id=id,category=category,amount=amount,**extra))
    original=event_file(tmp_path,'SYNTHETIC-forward-events.json',events)
    import_file(page,original)
    assert page.request.get(base).json()['assessment_pending']
    first,first_bytes=assess(page,portal);m=first['calculations']['metrics']
    assert Decimal(m['gross_realized_pnl'])==6 and Decimal(m['commissions'])==3 and Decimal(m['net_realized_pnl'])==3
    assert Decimal(m['net_trading_equity'])==50003 and Decimal(m['provider_balance_from_observed_ledger'])==49943
    assert Decimal(m['payout_requests'])==50 and Decimal(m['provider_deductions'])==60 and Decimal(m['trader_receipts'])==50
    assert Decimal(m['net_trader_cash'])==50 and Decimal(m['pending_receipt_amount'])==0
    assert first['calculations']['advisory']['state']=='ACTIVE'
    assert first['calculations']['forward_evidence']['status']=='SYNTHETIC_ONLY'
    assert first['calculations']['forecast_comparison']['status']=='NOT_COMPARABLE'
    assert not first['calculations']['reconciliation']['costs']['slippage_deducted_again']
    page.locator('#forward-observed-metrics').screenshot(path=str(tmp_path/'observed-cash-and-trading-separation.png'))
    monitor(page);import_file(page,original)
    assert page.request.get(base).json()['event_count']==20
    assert not page.request.get(base).json()['assessment_pending']
    changed=json.loads(original.read_text());changed['events'][5]['price']='100.25';conflict=tmp_path/'SYNTHETIC-conflicting-batch.json';conflict.write_text(json.dumps(changed))
    page.locator('#forward-events-file').set_input_files(conflict);page.locator('#forward-events-check').click()
    playwright.expect(page.locator('#forward-event-status')).to_contain_text('Batch ID is bound to different original bytes')
    playwright.expect(page.locator('#forward-events-import')).to_be_disabled()
    correction=deepcopy(events[11]);correction.update(event_id='corrected-exit',price='100.5',supersedes_event_id=events[11]['event_id'],correction_reason='Correct independent supplied exit fill price')
    import_file(page,event_file(tmp_path,'SYNTHETIC-fill-correction.json',[correction]))
    pending=page.request.get(base).json();assert pending['assessment_pending'] and pending['advisory_state']=='WATCH'
    playwright.expect(page.locator('#forward-monitor')).to_contain_text('NEW OR UNASSESSED OBSERVATIONS')
    page.locator('#forward-monitor-state').screenshot(path=str(tmp_path/'new-events-pending-assessment.png'))
    second,second_bytes=assess(page,portal)
    assert Decimal(second['calculations']['metrics']['net_realized_pnl'])==0
    assert second['calculations']['advisory']['state']=='PAUSED'
    assert 'account_balance_mismatch' in second['calculations']['advisory']['reasons']
    page.locator('#forward-issues').screenshot(path=str(tmp_path/'correction-mismatch-pause.png'))
    monitor(page);page.locator('#forward-controls > summary').click()
    playwright.expect(page.locator('#forward-control-resume')).to_be_disabled()
    position=deepcopy(events[13]);position.update(event_id='corrected-position',account_balance='50000',supersedes_event_id=events[13]['event_id'],correction_reason='Reconcile supplied position balance to corrected fills')
    import_file(page,event_file(tmp_path,'SYNTHETIC-position-correction.json',[position]))
    third,third_bytes=assess(page,portal)
    assert third['calculations']['advisory']['state']=='PAUSED'
    assert third['calculations']['recovery']['eligible_for_acknowledgement']
    assert Decimal(third['calculations']['metrics']['provider_balance_from_observed_ledger'])==49940
    monitor(page);page.locator('#forward-controls > summary').click()
    page.locator('#forward-control-reason').fill('Reviewed corrected supplied fills and position; current blockers resolved. Synthetic advisory recovery only.')
    page.locator('#forward-control-resume').click()
    playwright.expect(page.locator('#forward-control-status')).to_contain_text('Review and acknowledge')
    page.locator('#forward-recovery-ack').check();page.locator('#forward-control-resume').click()
    playwright.expect(page.locator('#prop-status')).to_contain_text('Saved advisory ACTIVE',timeout=15000)
    recovered=page.request.get(base).json();assert recovered['advisory_state']=='ACTIVE'
    assert recovered['control_history'][-1]['control']['acknowledged_snapshot_sha256']==recovered['last_completed_snapshot_sha256']
    assert page.request.get(portal['url']+f'/api/prop-analyses/{first["id"]}/downloads/report.json').body()==first_bytes
    page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.locator('#forward-monitor-state').screenshot(path=str(tmp_path/'recovered-monitor-narrow.png'))
    downloads={}
    for label,report,data in [('initial',first,first_bytes),('mismatch',second,second_bytes),('reconciled',third,third_bytes)]:
        (tmp_path/(label+'-report.json')).write_bytes(data);downloads[label+'-report.json']=sha256(data).hexdigest()
        response=page.request.get(portal['url']+f'/api/prop-analyses/{report["id"]}/downloads/analysis.zip');assert response.ok,response.text()
        (tmp_path/(label+'-analysis.zip')).write_bytes(response.body());downloads[label+'-analysis.zip']=sha256(response.body()).hexdigest()
        with zipfile.ZipFile(io.BytesIO(response.body())) as archive:
            for name,entry in report['files'].items():assert sha256(archive.read(name)).hexdigest()==entry['sha256']
    for name,url in {'monitor.json':base,'original-events.json':base+'/batches/'+json.loads(original.read_text())['batch_id']+'/download',
        'events.jsonl':base+'/exports/events.jsonl','current-selection-report.json':portal['url']+f'/api/prop-analyses/{application["analysis_id"]}/downloads/report.json',
        'SYNTHETIC-current-policy-history.csv':portal['url']+'/api/datasets/'+dataset['id']+'/csv'}.items():
        response=page.request.get(url);assert response.ok,response.text();(tmp_path/name).write_bytes(response.body());downloads[name]=sha256(response.body()).hexdigest()
    assert (tmp_path/'original-events.json').read_bytes()==original.read_bytes()
    assert downloads['SYNTHETIC-current-policy-history.csv']==dataset['sha256']
    posts=[];page.on('request',lambda request:posts.append(request.url) if request.method=='POST' else None)
    page.reload();playwright.expect(page.locator('#forward-monitor-state')).to_contain_text('ACTIVE');assert not posts
    page.goto(portal['url']+'/#backtests/prop/job/'+first['id']);playwright.expect(page.locator('#forward-observed-metrics')).to_be_visible();assert not posts
    page.goto(portal['url']+'/#backtests/research');page.locator('#forward-catalogue > summary').click();playwright.expect(page.locator('#forward-catalogue')).to_contain_text('SYNTHETIC current-policy observation arithmetic');assert not posts
    (tmp_path/'evidence.json').write_text(json.dumps(dict(campaign_id=campaign,current_application_id=application['application_id'],current_analysis_id=application['analysis_id'],package_sha256=package['package_sha256'],monitor_id=monitor_id,analysis_ids=[r['id'] for r in [first,second,third]],expected=dict(gross_realized=6,commissions=3,initial_net_realized=3,corrected_net_realized=0,trader_receipts=50,provider_deduction=60,recovered_provider_balance=49940),downloads=downloads,reopen_posts=posts,states=['ACTIVE','PAUSED','PAUSED','ACTIVE after explicit acknowledgement'],server='Owned temporary portal fixture stopped its server.'),indent=2))


def test_no_qualified_current_policy_allows_only_unbound_synthetic_diagnostic(page,portal,tmp_path):
    from test_robust_research_api import PREFIX,save_grid,declaration,save,run
    from test_robust_economic_api import economic
    from test_research_procedure_api import wait_application
    with httpx.Client(base_url=portal['url'],timeout=300) as client:
        _,grid,records=save_grid(client)
        body=declaration(grid,records,economic_studies=[economic(client,'funded')])
        body['qualification']['minimum_mean_session_net']='1000'
        campaign=save(client,body)['campaign_id'];run(client,campaign)
        response=client.post(f'{PREFIX}/{campaign}/procedure/preview',json={});assert response.status_code==200,response.text
        frozen=client.post(f'{PREFIX}/{campaign}/procedure/freeze',json=dict(procedure_id=uuid4().hex,expected_preview_sha256=response.json()['preview_sha256']))
        assert frozen.status_code==201,frozen.text
        app_id=uuid4().hex
        response=client.post(f'{PREFIX}/{campaign}/development-selection/run',json=dict(request_id=app_id,procedure_sha256=frozen.json()['procedure_sha256']))
        assert response.status_code==202,response.text
        application=wait_application(client,campaign,app_id)
    assert all(row['status']=='NO_QUALIFIED_DEPLOYMENT_CANDIDATE' for row in application['result']['recommendation'])
    page.goto(portal['url']+'/#backtests/prop/job/'+application['analysis_id'])
    page.locator('#forward-launcher > summary').click()
    playwright.expect(page.locator('#forward-launch-status')).to_contain_text('unbound diagnostic is synthetic only')
    playwright.expect(page.locator('#forward-policy option')).to_have_count(1)
    # Chromium's option accessibility state can differ from the native DOM
    # property in the styled select. Assert the actual selection guard.
    for kind in ('paper','actual_import'):
        option=page.locator(f'#forward-kind option[value="{kind}"]')
        playwright.expect(option).to_have_attribute('disabled','')
        assert option.evaluate('(element)=>element.disabled') is True
    page.locator('#forward-name').fill('SYNTHETIC unbound diagnostic · no qualified policy')
    page.locator('#forward-source-id').fill('synthetic-observer')
    page.locator('#forward-source-label').fill('SYNTHETIC diagnostic without deployable selection')
    page.locator('#forward-check').click();playwright.expect(page.locator('#forward-create')).to_be_enabled()
    playwright.expect(page.locator('#forward-admission')).to_contain_text('synthetic_diagnostic')
    page.locator('#forward-launcher').screenshot(path=str(tmp_path/'no-qualified-synthetic-only.png'))
    page.locator('#forward-create').click();playwright.expect(page.locator('#forward-monitor-state')).to_be_visible()
    id=page.url.rsplit('/',1)[-1];response=page.request.get(portal['url']+'/api/forward-monitors/'+id);saved=response.json()
    assert saved['declaration']['policy_binding'] is None and saved['declaration']['observation_kind']=='synthetic_harness'
    assert saved['event_count']==0 and saved['last_completed_analysis_id'] is None
    wrong=deepcopy(saved['declaration']);wrong['observation_kind']='actual_import';wrong['monitor_id']=uuid4().hex
    assert page.request.post(portal['url']+'/api/forward-monitors/check',data=wrong).status==422
    (tmp_path/'monitor.json').write_bytes(response.body())
    current=page.request.get(portal['url']+f'/api/prop-analyses/{application["analysis_id"]}/downloads/report.json');assert current.ok,current.text();(tmp_path/'current-report.json').write_bytes(current.body())
    posts=[];page.on('request',lambda request:posts.append(request.url) if request.method=='POST' else None)
    page.reload();playwright.expect(page.locator('#forward-monitor-state')).to_be_visible();assert not posts
    (tmp_path/'evidence.json').write_text(json.dumps(dict(campaign_id=campaign,current_application_id=app_id,current_analysis_id=application['analysis_id'],monitor_id=id,no_qualified_policy=True,synthetic_only=True,actual_import_without_binding_rejected=True,no_assessment_fabricated=True,downloads={name:sha256((tmp_path/name).read_bytes()).hexdigest() for name in ['monitor.json','current-report.json']},reopen_posts=posts,server='Owned temporary portal fixture stopped its server.'),indent=2))
