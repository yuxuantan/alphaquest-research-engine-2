"""Real native policy comparisons in the existing phase campaign, never a demo UI."""
from decimal import Decimal
from hashlib import sha256
import io
import json
import re
import zipfile

import httpx
import pytest
from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser, page, playwright, portal
from test_native_replay_api import source


def configure_native_campaign(page, portal, original, phase, quantities, *, horizon=9, capture=1):
    page.goto(portal['url']+'/#backtests/report/'+original['id'])
    page.locator('#report-prop-setup').click()
    page.locator('#campaign-new-'+phase).click()
    page.locator('#campaign-execution').select_option('native')
    page.locator('.campaign-sizes').fill(quantities)
    page.locator('#campaign-paths').fill('4')
    page.locator('#campaign-seed').fill('1729')
    page.locator('#campaign-block').select_option('1')
    page.locator('#campaign-native-horizon').fill(str(horizon))
    page.locator('#campaign-native-capture').fill(str(capture))
    page.locator('#campaign-native-calendar-version').fill('explicit-demo-weekdays-v1')
    page.locator('.campaign-native-start').fill('2026-01-26')
    page.locator('#campaign-native-coverage-end').fill('2026-02-05')
    if phase=='funded':page.locator('#campaign-delay').fill('2')


def run_campaign(page, portal, tmp_path, expected_count):
    page.locator('#campaign-check').click()
    playwright.expect(page.locator('#campaign-run')).to_be_enabled(timeout=90000)
    playwright.expect(page.locator('#campaign-native-work tbody tr')).to_have_count(expected_count)
    page.locator('#campaign-native-fields').screenshot(path=str(tmp_path/'native-campaign-declaration.png'))
    page.locator('#campaign-native-work').screenshot(path=str(tmp_path/'native-campaign-work.png'))
    page.locator('#campaign-run').click()
    playwright.expect(page.locator('#prop-heading-title')).to_have_text('Research campaign',timeout=180000)
    campaign_id=page.url.rsplit('/',1)[-1]
    campaign=page.request.get(portal['url']+'/api/research-campaigns/'+campaign_id).json()
    response=page.request.get(portal['url']+f"/api/prop-analyses/{campaign['analysis_id']}/downloads/report.json")
    assert response.ok,response.text()
    return campaign,response.json()


def preserve(page, portal, tmp_path, original, campaign, report, expected):
    rows=report['calculations']['candidates'];analysis=report['id']
    assert all(row['manifest']['native_execution']['model']=='observed_contiguous_blocks_with_prior_prefix_v1' for row in rows)
    assert all(row['native_forecast']['metrics']['paths']==4 for row in rows)
    assert all(row['native_forecast']['observed_future_data'] is False for row in rows)
    playwright.expect(page.locator('#campaign-native-forecast-result')).to_contain_text('not an observed historical outcome')
    page.locator('#campaign-native-forecast-metrics').screenshot(path=str(tmp_path/'candidate-forecast-metrics.png'))
    page.locator('#campaign-native-forecast-captures-detail > summary').click()
    page.locator('#campaign-native-forecast-clock-mapping').screenshot(path=str(tmp_path/'native-source-model-clocks.png'))
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.locator('#campaign-native-forecast-decisions').screenshot(path=str(tmp_path/'native-decisions-narrow.png'))
    page.set_viewport_size({'width':1440,'height':1100})
    downloads={}
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client:
        urls={'report.json':f'/api/prop-analyses/{analysis}/downloads/report.json',
              'analysis.zip':f'/api/prop-analyses/{analysis}/downloads/analysis.zip',
              'campaign.json':f"/api/research-campaigns/{campaign['campaign_id']}",
              'source-report.json':f"/api/backtests/{original['id']}",
              'SYNTHETIC-MNQ-observed-bars.csv':f"/api/datasets/{original['run_metadata']['dataset']['id']}/csv"}
        for name,url in urls.items():
            response=client.get(url);assert response.status_code==200,(name,response.text)
            (tmp_path/name).write_bytes(response.content);downloads[name]=sha256(response.content).hexdigest()
        assert downloads['SYNTHETIC-MNQ-observed-bars.csv']==original['run_metadata']['dataset']['sha256']
        with zipfile.ZipFile(io.BytesIO((tmp_path/'analysis.zip').read_bytes())) as bundle:
            for name in ('native_forecasts.json','native_forecast_paths.json','native_forecast_schedules.json','native_forecast_captures.json'):
                assert name in bundle.namelist()
            for name,value in report['files'].items():
                assert sha256(bundle.read(name)).hexdigest()==(value['sha256'] if isinstance(value,dict) else value)
        before=downloads['report.json'];posts=[]
        page.on('request',lambda request:posts.append(request.url) if request.method=='POST' else None)
        page.reload();playwright.expect(page.locator('#campaign-candidates tbody tr')).to_have_count(len(rows),timeout=60000)
        assert posts==[]
        again=client.get(f'/api/prop-analyses/{analysis}/downloads/report.json')
        assert sha256(again.content).hexdigest()==before
    (tmp_path/'evidence.json').write_text(json.dumps(dict(source_id=original['id'],campaign_id=campaign['campaign_id'],analysis_id=analysis,
        engine_identity=report['implementation'],expected=expected,downloads=downloads,reopen_posts=posts,
        source_research=original['run_metadata']['research'],source_fixture='SYNTHETIC observed MNQ bars; saved CSV contains the explicit unexecuted fixture OOS row.',
        server='Owned portal fixture stops its temporary uvicorn server.'),indent=2))


@pytest.mark.parametrize('phase,quantities',[('funded','1,3'),('evaluation','3,10')])
def test_native_campaign_fixed_policies_have_independent_economic_results(page,portal,tmp_path,phase,quantities):
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client:original=source(client,days=7,payout=True)
    configure_native_campaign(page,portal,original,phase,quantities)
    campaign,report=run_campaign(page,portal,tmp_path,2)
    rows={row['manifest']['configuration']['micros']:row for row in report['calculations']['candidates']}
    if phase=='funded':
        assert Decimal(str(rows[1]['metrics']['expected_payouts']))==0
        assert Decimal(str(rows[3]['metrics']['expected_payouts']))==1500
        assert report['calculations']['ranking'][0]==rows[3]['candidate_id']
        for path in rows[3]['native_forecast']['paths']:
            event,=path['payout_events'];assert event['request_date']=='2026-01-30' and event['receipt_date']=='2026-02-01'
        expected={'fixed_1_received_cash':0,'fixed_3_received_cash':1500,'request_date':'2026-01-30','receipt_date':'2026-02-01'}
        selected=rows[3]
    else:
        for quantity,days in [(3,7),(10,2)]:
            assert Decimal(str(rows[quantity]['metrics']['cost_per_funded']))==70
            assert Decimal(str(rows[quantity]['metrics']['expected_calendar_days_to_funded']))==days
        assert report['calculations']['frontier']==[rows[10]['candidate_id']]
        expected={'fixed_3_acquisition_cost':70,'fixed_3_calendar_days':7,'fixed_10_acquisition_cost':70,'fixed_10_calendar_days':2}
        selected=rows[10]
    page.locator('#campaign-inspect').select_option(selected['candidate_id'])
    preserve(page,portal,tmp_path,original,campaign,report,expected)


def test_native_campaign_compares_actual_dynamic_policy_paths(page,portal,tmp_path):
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client:original=source(client)
    configure_native_campaign(page,portal,original,'funded','40',horizon=3,capture=4)
    page.locator('.campaign-sizing-mode').select_option('policies')
    page.locator('.campaign-planning-commission').fill('0')
    page.locator('.campaign-policy-dollars').fill('100')
    page.locator('.campaign-add-policy').click()
    second=page.locator('.campaign-sizing-policy').nth(1)
    second.locator('.campaign-policy-kind').select_option('percentage_risk')
    second.locator('.campaign-policy-percent').fill('0.2')
    second.locator('.campaign-policy-reference').select_option('current_account_balance')
    campaign,report=run_campaign(page,portal,tmp_path,2)
    rows={row['manifest']['configuration']['sizing']['policy']['kind']:row for row in report['calculations']['candidates']}
    expected_quantities={'fixed_dollar_risk':[[10,5,10],[10,10,10],[5,5,10],[10,10,10]],
                         'percentage_risk':[[10,5,10],[10,10,10],[5,5,10],[10,9,10]]}
    for kind,row in rows.items():
        assert Decimal(str(row['metrics']['expected_payouts']))==0
        assert [[decision['quantity'] for decision in capture['result']['sizing_decisions']] for capture in row['native_forecast']['captures']]==expected_quantities[kind]
    page.locator('#campaign-inspect').select_option(rows['percentage_risk']['candidate_id'])
    preserve(page,portal,tmp_path,original,campaign,report,dict(quantities=expected_quantities,received_cash_for_both=0))


def test_native_campaign_frozen_manual_oos_uses_actual_strategy_bars(page,portal,tmp_path):
    from test_native_phase_campaigns import source_with_complete_oos
    with httpx.Client(base_url=portal['url'],timeout=300) as client:original=source_with_complete_oos(client)
    configure_native_campaign(page,portal,original,'funded','1,3',horizon=7)
    page.locator('.campaign-native-start').fill('2026-01-12')
    page.locator('#campaign-native-coverage-end').fill('2026-01-19')
    campaign,report=run_campaign(page,portal,tmp_path,2)
    selected=report['calculations']['winner']
    assert next(row for row in report['calculations']['candidates'] if row['candidate_id']==selected)['manifest']['configuration']['micros']==3
    page.locator(f'.campaign-pick[value="{selected}"]').check()
    page.locator('#campaign-rationale').fill('Predeclared synthetic native cash comparison; retain the 3 MNQ IS choice for actual later bars.')
    page.locator('#campaign-freeze').click()
    playwright.expect(page.get_by_role('heading',name='Frozen IS selection')).to_be_visible(timeout=30000)
    base=portal['url']+'/api/research-campaigns/'+campaign['campaign_id']
    frozen=page.request.get(base+'/exports/frozen_package.json').body()
    page.locator('#campaign-launch-oos').click()
    playwright.expect(page.get_by_role('link',name='Open frozen OOS assessment')).to_be_visible(timeout=180000)
    page.get_by_role('link',name='Open frozen OOS assessment').click()
    playwright.expect(page.locator('#prop-heading-title')).to_have_text('Frozen native chronological OOS')
    playwright.expect(page.locator('#campaign-native-oos-outcomes')).to_contain_text(re.compile(r'1,?500'))
    analysis=page.url.rsplit('/',1)[-1]
    response=page.request.get(portal['url']+f'/api/prop-analyses/{analysis}/downloads/report.json')
    assert response.ok,response.text()
    actual_report=response.json();calc=actual_report['calculations'];row,=calc['candidates']
    assert calc['selection_status']=='assessment_only_no_reselection'
    assert not calc.get('ranking') and not calc.get('winner')
    assert row['frozen_candidate_id']==selected
    outcome=row['native_chronological_replay'];event,=outcome['payout_events']
    assert Decimal(str(outcome['cash_received']))==1500 and Decimal(str(outcome['pending_cash']))==0
    assert Decimal(str(outcome['trading_profit']))==4500
    assert event['request_date']=='2026-01-30' and event['receipt_date']=='2026-02-01'
    child=row['native_backtest_id']
    trades=page.request.get(portal['url']+f'/api/backtests/{child}/trades').json()['items']
    assert len(trades)==5 and all(trade['contracts']==3 for trade in trades)
    assert {trade['entry_time_utc'][:10] for trade in trades}=={'2026-01-26','2026-01-27','2026-01-28','2026-01-29','2026-01-30'}
    assert page.request.get(base+'/exports/frozen_package.json').body()==frozen
    page.locator('#campaign-native-oos-outcomes').screenshot(path=str(tmp_path/'actual-oos-outcomes.png'))
    page.locator('#campaign-native-oos-cash-ledger').screenshot(path=str(tmp_path/'actual-oos-cash-ledger.png'))
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.locator('#campaign-native-oos-decisions').screenshot(path=str(tmp_path/'actual-oos-decisions-narrow.png'))
    downloads={}
    for name,url in {'report.json':f'/api/prop-analyses/{analysis}/downloads/report.json',
        'analysis.zip':f'/api/prop-analyses/{analysis}/downloads/analysis.zip',
        'frozen-package.json':f"/api/research-campaigns/{campaign['campaign_id']}/exports/frozen_package.json",
        'SYNTHETIC-complete-IS-OOS-MNQ.csv':f"/api/datasets/{original['run_metadata']['dataset']['id']}/csv"}.items():
        saved=page.request.get(portal['url']+url);assert saved.ok,saved.text()
        (tmp_path/name).write_bytes(saved.body());downloads[name]=sha256(saved.body()).hexdigest()
    assert downloads['SYNTHETIC-complete-IS-OOS-MNQ.csv']==original['run_metadata']['dataset']['sha256']
    with zipfile.ZipFile(io.BytesIO((tmp_path/'analysis.zip').read_bytes())) as bundle:
        for name,item in actual_report['files'].items():assert sha256(bundle.read(name)).hexdigest()==item['sha256']
    posts=[];page.on('request',lambda request:posts.append(request.url) if request.method=='POST' else None)
    page.reload();playwright.expect(page.locator('#campaign-native-oos-outcomes')).to_be_visible()
    assert posts==[]
    (tmp_path/'evidence.json').write_text(json.dumps(dict(source_id=original['id'],campaign_id=campaign['campaign_id'],analysis_id=analysis,
        source_research=original['run_metadata']['research'],controlled_oos_backtest=child,engine_identity=actual_report['implementation'],
        expected=dict(trades=5,quantity=3,trading_profit=4500,cash_received=1500,pending_cash=0,request_date='2026-01-30',receipt_date='2026-02-01',selection_unchanged=True),
        downloads=downloads,reopen_posts=posts,synthetic=True,server='Owned temporary server stopped in fixture teardown.'),indent=2))
