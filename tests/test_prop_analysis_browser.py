import json
import httpx
from test_backtests_browser import browser,page,portal,playwright
from test_prop_analysis_api import backtest,export_for


def test_local_report_reload_reopen_and_download(page,portal,tmp_path):
    from types import SimpleNamespace
    with httpx.Client(base_url=portal['url']) as client:r=backtest(client)
    adapter=SimpleNamespace(app=portal['app'])
    path=export_for(adapter,r,tmp_path)
    page.goto(portal['url']+f"/#backtests/report/{r['id']}");page.locator('#report-prop-setup').click()
    playwright.expect(page.locator('#prop-config')).to_be_visible()
    page.locator('#prop-trade-file').fill(str(path));page.locator('#prop-export-timezone').select_option('UTC')
    page.locator('#prop-check').click();playwright.expect(page.locator('#prop-run')).to_be_enabled()
    playwright.expect(page.locator('#prop-check-output')).to_contain_text('52.00')
    page.locator('#prop-run').click();playwright.expect(page.locator('#prop-report')).to_be_visible(timeout=20000)
    playwright.expect(page.locator('#prop-heading-note')).to_contain_text('AlphaQuest local model')
    playwright.expect(page.get_by_role('heading',name='Funded outcomes are unavailable')).to_be_visible()
    playwright.expect(page.get_by_role('tab',name='Sizing',exact=True)).to_have_count(0)
    playwright.expect(page.locator('#prop-report-content')).to_contain_text('52.00')
    with page.expect_download() as result:page.get_by_role('link',name='Report data (JSON)',exact=True).click()
    destination=tmp_path/'download.json';result.value.save_as(destination);data=json.loads(destination.read_text());assert data['format_version']==3
    posts=[];page.on('request',lambda req:posts.append(req.url) if req.method=='POST' else None)
    page.reload();playwright.expect(page.locator('#prop-report')).to_be_visible(timeout=10000);assert not posts
    page.locator('#prop-back').click();page.locator('#report-prop-setup').click();page.locator('#prop-saved a').first.click()
    playwright.expect(page.locator('#prop-report')).to_be_visible();assert not posts


def presentation_fixture(record):
    """Synthetic saved-response fixture for presentation, never a model oracle."""
    source=dict(backtest=record,reconciliation=dict(source_count=2,source_totals=dict(net_pnl='52.00')),
                excursion_input=dict(measured_mae_count=2),excursion_provenance='SYNTHETIC measured-excursion presentation fixture.')
    selected={'micros':9,'sims':20000,'E[payout]':2005.425,'median life':0.,'P(>=1 payout)':.32005,'blown':.8373,
              'E[P] 12m':1889.6,'median 12m':0.,'P(>=1) 12m':.32075,'T1 median':20.,'T1 p75':28.,'T1 p90':37.}
    sweep=[dict(micros=2,sims=3000,slot_year=200.,**{'E[payout]':605.,'P(>=1 payout)':.218,'blown':.14,'days alive':163.8}),
           dict(micros=9,sims=3000,slot_year=6414.8,**{'E[payout]':1664.666666,'P(>=1 payout)':.314,'blown':.852,'days alive':53.6}),
           dict(micros=10,sims=3000,slot_year=6300.,**{'E[payout]':1538.166666,'P(>=1 payout)':.296,'blown':.866,'days alive':49.3})]
    calculations=dict(evaluation=dict(selected_micros=25,simulations=20000,passed=6818,pass_rate=.3409,fail_drawdown=.65185,timeout=.00725,
                       pass_rate_ci=[.3343616454112101,.34749946270714255],cost_per_funded=272.7371663244353,
                       days_to_funded=19.519,days_to_funded_median=14.,median_days_to_pass=5.,evaluations_per_funded=2.9334115576415374),
        evaluation_sweep=[dict(micros=25,passed=900,simulations=3000)],
        samples=dict(train=['2021-01-05','2024-11-08'],validation=['2024-11-11','2026-07-06'],data=['2021-01-05','2026-07-06'],weekdays=[1004,431]),
        funded=dict(selected=selected,sweep=sweep,outcomes=dict(never_paid=.67995,paid_partial=.22265,paid_all=.0974),
                    selection_economics=dict(pass_rate=.525,replacement_days=5)),
        history=dict(years=[dict(year=2025,out_of_sample_share=1.,payouts=30000,costs=32728,net=-2728,new_funded_accounts=120)],
                     totals=dict(net=-2728,payouts=30000,costs=32728,new_funded_accounts=120),
                     accounts=[dict(account=1,start='2025-01-01',end='2025-02-01',outcome='blown',payouts=0,payout_days=[])]),rules={},seeds={})
    return dict(id='a'*32,format_version=3,created_at_utc='2026-10-26T14:25:00Z',source=source,calculations=calculations,
                settings=dict(EVAL_PRICE='49',ACTIVATION_FEE='129',SLOTS='20'),files={},model_version='synthetic-presentation-fixture',runtime={},implementation_sha256={},application_commit='fixture')


def open_presentation_fixture(page,portal,record,mutate=lambda r:None):
    fixture=presentation_fixture(record);mutate(fixture);id=fixture['id']
    page.route(f'**/api/prop-analyses/{id}',lambda route:route.fulfill(json=dict(id=id,status='complete',progress='Saved presentation fixture')))
    page.route(f'**/api/prop-analyses/{id}/downloads/report.json',lambda route:route.fulfill(
        body=json.dumps(fixture),content_type='application/json',headers={'Content-Disposition':'attachment; filename="presentation-fixture.json"'}))
    page.goto(portal['url']+f'/#backtests/prop/job/{id}')
    playwright.expect(page.get_by_role('heading',name='What happens to one funded account?')).to_be_visible()
    return fixture


def test_funded_insights_tabs_sorting_units_and_exact_download(page,portal,tmp_path):
    with httpx.Client(base_url=portal['url']) as client:record=backtest(client)
    posts=[];page.on('request',lambda req:posts.append(req.url) if req.method=='POST' else None)
    fixture=open_presentation_fixture(page,portal,record)
    overview=page.get_by_role('tabpanel',name='Overview')
    for text in ['$2,005.43','$0.00','32.0%','83.7%','68.0%','Most accounts receive no payout.','before evaluation and activation costs']:
        playwright.expect(overview).to_contain_text(text)
    playwright.expect(overview.get_by_role('meter',name='No payouts',exact=True)).to_have_attribute('value','0.67995')
    playwright.expect(overview).to_contain_text('Do not add the failure rate')
    playwright.expect(overview).to_contain_text('Among accounts that receive at least one payout.')
    # Arrow keys select and focus tabs; the job hash never changes.
    page.get_by_role('tab',name='Overview',exact=True).focus();page.keyboard.press('ArrowRight')
    playwright.expect(page.get_by_role('tab',name='Evaluation',exact=True)).to_be_focused()
    playwright.expect(page.get_by_role('tabpanel',name='Evaluation')).to_be_visible()
    playwright.expect(page.get_by_role('tabpanel',name='Evaluation')).to_contain_text('$272.74')
    page.keyboard.press('ArrowRight');sizing=page.get_by_role('tabpanel',name='Sizing')
    playwright.expect(sizing).to_be_visible()
    playwright.expect(sizing.locator('tbody tr').first).to_have_attribute('aria-label','Selected size: 9 MNQ')
    playwright.expect(sizing).to_contain_text('52.5% evaluation pass rate and 5 replacement trading days')
    playwright.expect(sizing.locator('thead')).to_have_text('SizeAnnual net / slotAvg. lifetime payoutAny payoutDrawdown failureAvg. lifetime · days')
    page.get_by_label('Sort sizes by').select_option('micros')
    playwright.expect(sizing.locator('tbody tr').first).to_contain_text('2 MNQ')
    page.get_by_label('Sort sizes by').select_option('blown')
    playwright.expect(sizing.locator('tbody tr').first).to_contain_text('14.0%')
    page.get_by_role('tab',name='Historical replay',exact=True).click();history=page.get_by_role('tabpanel',name='Historical replay')
    playwright.expect(history).to_contain_text('20 slots taking the same trades')
    playwright.expect(history).to_contain_text('not an annual forecast')
    playwright.expect(history.locator('td.prop-negative')).to_have_text('-$2,728')
    page.get_by_text('Inspect 1 account lifecycle and payout dates',exact=True).click()
    playwright.expect(history.get_by_role('cell',name='Drawdown failure',exact=True)).to_be_visible()
    page.get_by_role('tab',name='Source & model',exact=True).click()
    playwright.expect(page.get_by_role('tabpanel',name='Source & model')).to_contain_text('Display values are rounded.')
    page.get_by_role('tab',name='Source & model',exact=True).focus();page.keyboard.press('Home')
    playwright.expect(page.get_by_role('tab',name='Overview',exact=True)).to_be_focused()
    with page.expect_download() as result:page.get_by_role('link',name='Report data (JSON)',exact=True).click()
    path=tmp_path/'report.json';result.value.save_as(path);assert json.loads(path.read_text())==fixture
    assert json.loads(path.read_text())['calculations']['funded']['selected']['E[payout]']==2005.425
    page.reload();playwright.expect(overview).to_be_visible();assert not posts


def test_mobile_insights_fit_and_missing_values_stay_unavailable(page,portal):
    with httpx.Client(base_url=portal['url']) as client:record=backtest(client)
    page.set_viewport_size({'width':390,'height':844})
    def missing(report):
        report['calculations']['funded']['selected']['T1 p90']=None
        report['calculations']['evaluation']['cost_per_funded']=None
        report['source']['excursion_input']['measured_mae_count']=0
    open_presentation_fixture(page,portal,record,missing)
    playwright.expect(page.get_by_text('Excursion coverage:',exact=False)).to_contain_text('close-only fallback')
    playwright.expect(page.get_by_role('tabpanel',name='Overview')).to_contain_text('Not reached')
    playwright.expect(page.get_by_role('tabpanel',name='Overview')).to_contain_text('Unavailable')
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.get_by_role('tab',name='Sizing',exact=True).click()
    playwright.expect(page.get_by_role('tabpanel',name='Sizing').get_by_role('row',name='Selected size: 9 MNQ')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    assert page.locator('#prop-view-sizing .prop-readable-scroll').evaluate('(node) => node.scrollWidth > node.clientWidth')
    page.get_by_role('tab',name='Sizing',exact=True).focus();page.keyboard.press('End')
    model_tab=page.get_by_role('tab',name='Source & model',exact=True)
    playwright.expect(model_tab).to_be_focused()
    assert model_tab.evaluate('(node) => {const r=node.getBoundingClientRect();return r.left>=0 && r.right<=innerWidth;}')
