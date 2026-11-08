"""Normal current policy → predeclared supplied scope → descriptive comparison.

The receiver clock is injected only into the ordinary test server constructor.
The product has no clock-changing endpoint. Every saved declaration/source says
this is a deterministic synthetic clock harness, never real elapsed observations.
"""
from copy import deepcopy
from datetime import timedelta
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
from test_forward_browser import event_file,import_file,monitor
from test_forward_reconcile import fixture
from tests.forward_comparison_fixtures import prospective_observation,coverage_events_for_binding
from alphaquest.forward_reconcile import stamp
from alphaquest.forward_comparison import boundary,iso


def assess_at(page,portal,clock):
    page.locator('#forward-asof').fill(clock);page.locator('#forward-assess').click()
    playwright.expect(page.locator('#prop-heading-title')).to_have_text('Forward observation assessment',timeout=30000)
    id=page.url.rsplit('/',1)[-1]
    response=page.request.get(portal['url']+f'/api/prop-analyses/{id}/downloads/report.json')
    assert response.ok,response.text()
    return response.json(),response.body()


def supplied_comparison_events(binding):
    base,_=coverage_events_for_binding(binding,complete=False)
    start=stamp(binding['coverage_start_utc']);trades=[]
    for index,event in enumerate(fixture()[1:14],1):
        event=deepcopy(event);event['event_id']='trade-'+event['event_id']
        event['event_time_utc']=iso(start+timedelta(hours=1,seconds=index))
        if event.get('quantity')==2:event['quantity']=3
        if event['kind']=='fill':event['commission']='1.5'
        if event['kind']=='position':event['account_balance']='50003'
        trades.append(event)
    events=base[:4]+trades+base[4:]
    for index,event in enumerate(events,1):
        event['source_sequence']=index
        if event['kind']=='position' and event['event_time_utc']==binding['coverage_cutoff_utc']:
            event['account_balance']='49953'
        if event['kind']=='account_coverage':
            event.update(plan_sha256=binding['plan_sha256'],package_sha256=binding['package_sha256'],
                account_id=binding['plan']['account_id'],coverage='partial',
                statement='Deterministic synthetic receiver clock; initial supplied coverage intentionally partial. No broker verification.')
    return events


def test_prospective_funded_scope_partial_then_complete_exact_cash_delta(page,portal,tmp_path):
    with httpx.Client(base_url=portal['url'],timeout=300) as client:
        dataset,campaign,application,package=current_policy(client)
    plan,created=prospective_observation(application,package)
    clock=[created];portal['app'].state.forward_monitors.clock=lambda:clock[0]
    page.goto(portal['url']+'/#backtests/prop/job/'+application['analysis_id'])
    page.locator('#forward-launcher > summary').click()
    page.locator('#forward-name').fill('SYNTHETIC full Funded scope · deterministic receiver clock')
    page.locator('#forward-policy').select_option(package['package_sha256'])
    page.locator('#forward-source-id').fill('synthetic-observer')
    page.locator('#forward-source-label').fill('SYNTHETIC deterministic receiver clock, independently supplied events, no broker')
    page.locator('#forward-synthetic-clock').check()
    page.locator('#forward-observation-scope > summary').click();page.locator('#forward-scope-enabled').check()
    page.locator('#forward-scope-account').fill('synthetic-funded')
    page.locator('#forward-scope-first').fill(plan['first_session']);page.locator('#forward-scope-translate').click()
    playwright.expect(page.locator('#forward-scope-cutoff')).to_have_value(plan['cutoff_date_exclusive'])
    assert page.locator('.forward-scope-session').evaluate_all('(rows)=>rows.map(row=>row.value)')==plan['open_sessions']
    page.locator('#forward-scope-assumption').fill('Predeclared synthetic same-weekday calendar-pattern translation; stationarity and future behavior are not established.')
    # Absolute dates are not silently relabeled as the saved model calendar.
    page.locator('#forward-scope-alignment').select_option('exact_saved_dates');page.locator('#forward-check').click()
    playwright.expect(page.locator('#forward-launch-status')).to_contain_text('Exact calendar comparison requires the original saved absolute dates.')
    playwright.expect(page.locator('#forward-create')).to_be_disabled()
    page.locator('#forward-launch-status').screenshot(path=str(tmp_path/'exact-date-mismatch-rejection.png'))
    page.locator('#forward-scope-alignment').select_option('declared_pattern_translation');page.locator('#forward-check').click()
    playwright.expect(page.locator('#forward-create')).to_be_enabled(timeout=30000)
    playwright.expect(page.locator('#forward-scope-binding-facts')).to_contain_text(iso(boundary(plan['first_session'],plan['cutoff_date_exclusive'])[0]))
    page.locator('#forward-source-check').screenshot(path=str(tmp_path/'prospective-synthetic-scope-check.png'))
    page.locator('#forward-create').click();playwright.expect(page.locator('#forward-monitor-state')).to_be_visible()
    id=page.url.rsplit('/',1)[-1];base=portal['url']+'/api/forward-monitors/'+id
    saved=page.request.get(base).json();binding=saved['source_check']['forecast_observation_plan']
    assert saved['declaration']['source']['receiver_clock_provenance']=='synthetic_harness_clock'
    assert binding['original_window']['first_session']=='2026-01-27'
    assert binding['plan']['first_session']==plan['first_session']
    assert binding['plan']['cutoff_date_exclusive']==plan['cutoff_date_exclusive']
    events=supplied_comparison_events(binding);end=stamp(binding['coverage_cutoff_utc'])
    clock[0]=iso(end+timedelta(seconds=1))
    partial_file=event_file(tmp_path,'SYNTHETIC-partial-scope-events.json',events)
    import_file(page,partial_file);partial,partial_bytes=assess_at(page,portal,iso(end+timedelta(seconds=2)))
    assert partial['calculations']['forecast_comparison']['status']=='NOT_COMPARABLE'
    assert partial['calculations']['policy_conformance']['status']=='MATCH'
    monitor(page)
    coverage=deepcopy(events[-1]);coverage.update(event_id='completed-coverage',coverage='complete',
        supersedes_event_id=events[-1]['event_id'],correction_reason='Supply the completed synthetic observation coverage.',
        statement='Complete deterministic synthetic account scope, including every supplied signal/order/fill/position/cash event and no-trade sessions. No broker or provider verification.')
    clock[0]=iso(end+timedelta(seconds=3))
    complete_file=event_file(tmp_path,'SYNTHETIC-complete-coverage-correction.json',[coverage])
    import_file(page,complete_file);complete,complete_bytes=assess_at(page,portal,iso(end+timedelta(seconds=4)))
    out=complete['calculations'];comparison=out['forecast_comparison'];metrics=comparison['metrics']
    assert comparison['status']=='SYNTHETIC_SCOPE_COMPARISON',comparison['reasons']
    assert Decimal(metrics['expected_trader_receipts'])==1500
    assert Decimal(metrics['observed_trader_receipts'])==50
    assert Decimal(metrics['observed_minus_expected'])==-1450
    assert comparison['observation_count']==1 and not comparison['coverage']['independently_verified']
    assert comparison['coverage']['receiver_clock_provenance']=='synthetic_harness_clock'
    assert comparison['calendar_alignment']['original_window']['first_session']=='2026-01-27'
    assert Decimal(out['metrics']['net_realized_pnl'])==3
    assert Decimal(out['metrics']['provider_balance_from_observed_ledger'])==49953
    assert Decimal(out['metrics']['provider_deductions'])==50 and Decimal(out['metrics']['trader_receipts'])==50
    assert out['policy_conformance']['status']=='MATCH'
    entry,=out['policy_conformance']['decisions'];assert entry['recalculated']['quantity']==3
    assert not out['policy_conformance']['supplied_context_independently_verified']
    playwright.expect(page.locator('#forward-comparison-metrics')).to_contain_text('-1450')
    page.locator('#forward-forecast-comparison').screenshot(path=str(tmp_path/'single-observation-cash-comparison.png'))
    page.locator('#forward-policy-conformance > summary').click()
    playwright.expect(page.locator('#forward-sizing-decisions')).to_contain_text('3 / entry intent')
    page.locator('#forward-policy-conformance').screenshot(path=str(tmp_path/'fixed-quantity-conformance.png'))
    page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.locator('#forward-comparison-metrics').screenshot(path=str(tmp_path/'comparison-narrow.png'))
    downloads={}
    for label,report,data in [('partial',partial,partial_bytes),('complete',complete,complete_bytes)]:
        (tmp_path/(label+'-report.json')).write_bytes(data);downloads[label+'-report.json']=sha256(data).hexdigest()
        response=page.request.get(portal['url']+f'/api/prop-analyses/{report["id"]}/downloads/analysis.zip');assert response.ok,response.text()
        (tmp_path/(label+'-analysis.zip')).write_bytes(response.body());downloads[label+'-analysis.zip']=sha256(response.body()).hexdigest()
        with zipfile.ZipFile(io.BytesIO(response.body())) as archive:
            for name,entry in report['files'].items():assert sha256(archive.read(name)).hexdigest()==entry['sha256']
    for name,url in {'monitor.json':base,'events.jsonl':base+'/exports/events.jsonl',
        'current-policy-report.json':portal['url']+f'/api/prop-analyses/{application["analysis_id"]}/downloads/report.json',
        'SYNTHETIC-current-history.csv':portal['url']+'/api/datasets/'+dataset['id']+'/csv'}.items():
        response=page.request.get(url);assert response.ok,response.text();(tmp_path/name).write_bytes(response.body());downloads[name]=sha256(response.body()).hexdigest()
    assert downloads['SYNTHETIC-current-history.csv']==dataset['sha256']
    assert page.request.get(portal['url']+f'/api/prop-analyses/{partial["id"]}/downloads/report.json').body()==partial_bytes
    posts=[];page.on('request',lambda request:posts.append(request.url) if request.method=='POST' else None)
    page.reload();playwright.expect(page.locator('#forward-comparison-metrics')).to_contain_text('-1450');assert not posts
    (tmp_path/'evidence.json').write_text(json.dumps(dict(campaign_id=campaign,current_analysis_id=application['analysis_id'],monitor_id=id,
        partial_analysis_id=partial['id'],complete_analysis_id=complete['id'],package_sha256=package['package_sha256'],
        plan_sha256=binding['plan_sha256'],expected=dict(frozen_mean=1500,received=50,observed_minus_expected=-1450,trading_net=3,provider_balance=49953,fixed_entry_quantity=3),
        synthetic_clock=dict(created=created,received=clock[0],assessment=iso(end+timedelta(seconds=4)),provenance='synthetic_harness_clock',product_clock_control=False),
        downloads=downloads,reopen_posts=posts,prior_snapshot_unchanged=True,server='Owned temporary server stopped and joined.'),indent=2))
