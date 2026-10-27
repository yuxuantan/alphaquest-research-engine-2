"""Usable automatic Apex workflow with actual standard-count saved outputs."""

from hashlib import sha256
import csv
import io
import json
import re

from test_backtests_browser import browser,page,portal,playwright
from test_automatic_prop import synthetic_history,expected_cash


def test_automatic_apex_backtest_optimize_check_reopen_and_download(page,portal,tmp_path):
    source=tmp_path/'SYNTHETIC-automatic-apex-cash.csv'
    source.write_bytes(synthetic_history())
    page.goto(portal['url'])
    page.locator('#csv-file').set_input_files(source)
    page.locator('#dataset-name').fill('SYNTHETIC automatic Apex cash arithmetic')
    page.locator('#source-timezone').select_option('UTC')
    page.locator('#dataset-tick-size').fill('0.25')
    page.locator('#dataset-point-value').fill('1000')
    page.locator('#validate-button').click()
    playwright.expect(page.locator('#validation-result')).to_contain_text('Validation passed')
    page.locator('#save-button').click()
    playwright.expect(page.locator('#validation-result')).to_contain_text('Dataset saved')
    dataset=next(d for d in page.request.get(portal['url']+'/api/datasets').json() if d['name']=='SYNTHETIC automatic Apex cash arithmetic')
    page.get_by_role('link',name='Backtests',exact=True).click()
    page.locator('#backtest-dataset').select_option(dataset['id'])
    page.locator('#strategy-green_bar_count').fill('1')
    page.locator('#strategy-hold_minutes').fill('1')
    page.locator('#strategy-contracts').fill('1')
    page.locator('#backtest-slippage-ticks').fill('0')
    page.locator('#backtest-commission').fill('0')
    page.locator('#start-backtest').click()
    playwright.expect(page.locator('#report-historical-net')).to_have_text('$352,880',timeout=180000)
    page.screenshot(path=str(tmp_path/'automatic-backtest.png'),full_page=True)
    backtest_id=page.url.rsplit('/',1)[1]
    record=page.request.get(f"{portal['url']}/api/backtests/{backtest_id}").json()
    prop_id=record['run_metadata']['automatic_prop_analysis']['id']
    report_url=f"{portal['url']}/api/prop-analyses/{prop_id}/downloads/report.json"
    report_bytes=page.request.get(report_url).body()
    report=json.loads(report_bytes);expected_cash(report)
    inline=page.locator('#report-prop-summary')
    playwright.expect(inline.locator('#report-prop-historical-net')).to_have_text('$352,880')
    playwright.expect(inline.locator('#report-prop-payouts')).to_have_text('$360,000')
    playwright.expect(inline.locator('#report-prop-costs')).to_have_text('$7,120')
    playwright.expect(inline.locator('#report-prop-evaluation')).to_contain_text('Average acquisition cost: $178.00')
    assert float(inline.locator('#report-prop-average-payout').get_attribute('title').split(': ')[1])==report['calculations']['funded']['selected']['E[payout]']
    assert inline.evaluate("n => n.previousElementSibling.querySelector('h2').id")=='equity-chart-title'
    inline.scroll_into_view_if_needed();inline.screenshot(path=str(tmp_path/'inline-prop-summary.png'))
    with page.expect_download() as downloaded:
        inline.get_by_role('link',name='Report data (JSON)',exact=False).click()
    assert sha256(open(downloaded.value.path(),'rb').read()).hexdigest()==sha256(report_bytes).hexdigest()
    page.get_by_role('link',name='Open default prop analysis',exact=False).click()
    playwright.expect(page.locator('#prop-report')).to_be_visible(timeout=10000)
    page.get_by_role('tab',name='Historical replay',exact=True).click()
    history=page.get_by_role('tabpanel',name='Historical replay')
    for text in ('$352,880','$360,000','$7,120','20 slots'):
        playwright.expect(history).to_contain_text(text)
    page.screenshot(path=str(tmp_path/'historical-cash-and-fees.png'),full_page=True)
    with page.expect_download() as downloaded:
        page.get_by_role('link',name='Report data (JSON)',exact=True).click()
    downloaded.value.save_as(tmp_path/'default-prop-report.json')
    assert (tmp_path/'default-prop-report.json').read_bytes()==report_bytes
    # The normal configuration/check/run path can reopen the automatic result.
    page.locator('#prop-back').click()
    page.locator('#report-prop-setup').click()
    playwright.expect(page.locator('#prop-activation')).to_have_value('129')
    page.locator('#prop-overrides').fill('{"unsupported_automatic_test":1}')
    page.locator('#prop-check').click()
    playwright.expect(page.locator('#prop-status')).to_contain_text('Unknown prop analysis setting')
    playwright.expect(page.locator('#prop-run')).to_be_disabled()
    page.locator('#prop-overrides').fill('{}')
    page.locator('#prop-check').click()
    playwright.expect(page.locator('#prop-run')).to_be_enabled()
    playwright.expect(page.locator('#prop-check-output')).to_contain_text('180000')
    page.screenshot(path=str(tmp_path/'source-check.png'),full_page=True)
    page.locator('#prop-run').click()
    playwright.expect(page).to_have_url(re.compile('/#backtests/prop/job/'+prop_id+'$'))
    playwright.expect(page.locator('#prop-report')).to_be_visible()
    assert len(page.request.get(f"{portal['url']}/api/prop-analyses/sources/{backtest_id}").json()['analyses'])==1

    def configure_optimization():
        page.goto(portal['url']+'/#optimizations')
        page.locator('#backtest-dataset').select_option(dataset['id'])
        page.locator('#backtest-slippage-ticks').fill('0')
        page.locator('#backtest-commission').fill('0')
        for label,value in [('Green bar count start','1'),('Green bar count end','2'),('Hold minutes start','1'),('Hold minutes end','1')]:
            page.get_by_label(label,exact=True).fill(value)
        page.get_by_label('Green bar count step',exact=True).fill('1')
        settings=page.request.get(portal['url']+'/api/optimizations/settings').json()
        page.locator('#optimization-workers').select_option(str(min(2,settings['max_workers'])))
        page.locator('#optimization-reuse').check()
        playwright.expect(page.locator('#optimization-count')).to_have_text('Total combinations: 2 = 2 backtests')

    configure_optimization()
    page.screenshot(path=str(tmp_path/'configured-optimization.png'),full_page=True)
    page.locator('#start-backtest').click()
    playwright.expect(page.locator('#optimization-status')).to_contain_text('COMPLETE',timeout=180000)
    optimization_url=page.url;job_id=page.url.rsplit('/',1)[1]
    job=page.request.get(f"{portal['url']}/api/optimizations/{job_id}").json()
    rows=page.request.get(f"{portal['url']}/api/optimizations/{job_id}/results").json()['items']
    assert [r['metrics']['historical_net'] for r in rows]==[352880,None]
    for direction in ('ascending','descending'):
        page.get_by_role('button',name='Historical net',exact=False).click()
        playwright.expect(page.locator('#optimization-results th[data-column="historical_net"]')).to_have_attribute('aria-sort',direction)
        playwright.expect(page.locator('#optimization-results tbody td[data-column="historical_net"]').first).to_contain_text('$352,880')
        playwright.expect(page.locator('#optimization-results tbody td[data-column="historical_net"]').last).to_contain_text('N/A')
    page.screenshot(path=str(tmp_path/'optimization-historical-net.png'),full_page=True)
    with page.expect_download() as downloaded:
        page.locator('#optimization-download').click()
    downloaded.value.save_as(tmp_path/'optimization-results.csv')
    exported=list(csv.DictReader(io.StringIO((tmp_path/'optimization-results.csv').read_text())))
    assert [r['historical_net'] for r in exported]==['352880','']
    page.locator('#optimization-results tbody td[data-column="historical_net"] a').first.click()
    playwright.expect(page.locator('#prop-report')).to_be_visible(timeout=10000)
    page.get_by_role('tab',name='Historical replay',exact=True).click()
    playwright.expect(page.get_by_role('tabpanel',name='Historical replay')).to_contain_text('$352,880')
    page.goto(optimization_url)
    page.reload()
    playwright.expect(page.locator('#optimization-results tbody tr')).to_have_count(2)
    configure_optimization();page.locator('#start-backtest').click()
    playwright.expect(page.locator('#optimization-status')).to_contain_text('2 reused · 0 computed',timeout=10000)
    page.screenshot(path=str(tmp_path/'optimization-reused.png'),full_page=True)
    assert page.request.get(portal['url']+'/api/backtests').json()['total']==3
    assert sha256(page.request.get(report_url).body()).hexdigest()==sha256(report_bytes).hexdigest()
    page.set_viewport_size(dict(width=390,height=844))
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(tmp_path/'mobile-results.png'),full_page=True)
    # Reopen the observed no-pass trial directly in its normal backtest report.
    page.goto(portal['url']+'/#backtests/report/'+rows[1]['run_id'])
    playwright.expect(page.locator('#report-prop-historical-net')).to_have_text('N/A')
    playwright.expect(page.locator('#report-prop-status')).to_contain_text('No validation evaluation passed')
    assert page.locator('#report-prop-average-payout').count()==0
    page.locator('#report-prop-summary').screenshot(path=str(tmp_path/'inline-no-pass.png'))
    # Existing reports without automatic metadata discover their saved analysis.
    # Only the HTTP presentation of the old metadata shape is adapted here.
    legacy=json.loads(json.dumps(record));legacy['run_metadata'].pop('automatic_prop_analysis')
    page.route(f'**/api/backtests/{backtest_id}',lambda route:route.fulfill(json=legacy))
    posts=[];page.on('request',lambda req:posts.append(req.url) if req.method=='POST' else None)
    page.goto(portal['url']+'/#backtests/report/'+backtest_id)
    playwright.expect(page.locator('#report-prop-historical-net')).to_have_text('$352,880')
    playwright.expect(page.locator('#report-prop-context')).to_contain_text('Latest completed saved analysis')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert page.locator('#report-prop-metrics strong').evaluate_all('nodes => nodes.every(n => n.getBoundingClientRect().height <= parseFloat(getComputedStyle(n).lineHeight) + 1)')
    page.locator('#report-prop-summary').screenshot(path=str(tmp_path/'inline-mobile.png'))
    page.reload()
    playwright.expect(page.locator('#report-prop-historical-net')).to_have_text('$352,880')
    assert not posts
    assert sha256(page.request.get(report_url).body()).hexdigest()==sha256(report_bytes).hexdigest()
    (tmp_path/'verification.json').write_text(json.dumps(dict(
        synthetic=True,backtest=record,job=job,rows=rows,expected_source_net=180000,
        expected_historical_payouts=360000,expected_acquisition_costs=7120,expected_historical_net=352880,
        evaluation_fee=49,activation_fee=129,slots=20,standard_counts_verified=True,
        source_check_and_rejection_verified=True,cached_configure_run_verified=True,
        sorting_and_csv_verified=True,report_reopen_and_original_hash_verified=True,
        inline_summary_values_and_position_verified=True,inline_exact_download_verified=True,
        inline_no_pass_verified=True,legacy_metadata_discovery_and_mobile_verified=True,
        inline_reload_submits_no_analysis=True),indent=2))


def test_inline_summary_missing_analysis_and_load_failure_leave_equity_usable(page,portal):
    from test_backtest_api import body
    dataset=portal['saved']['arithmetic_5m']
    response=page.request.post(portal['url']+'/api/backtests',data=body(dataset['id']))
    assert response.status==201
    record=response.json();id=record['id']
    page.goto(portal['url']+'/#backtests/report/'+id)
    playwright.expect(page.locator('#report-prop-status')).to_contain_text('incompatible')
    playwright.expect(page.locator('#equity-chart')).to_be_visible()
    legacy=json.loads(json.dumps(record));legacy['run_metadata'].pop('automatic_prop_analysis')
    page.route(f'**/api/backtests/{id}',lambda route:route.fulfill(json=legacy))
    page.route(f'**/api/prop-analyses/sources/{id}?discover_exports=false',lambda route:route.fulfill(json=dict(analyses=[])))
    page.reload()
    playwright.expect(page.locator('#report-prop-status')).to_contain_text('No saved prop analysis yet')
    assert page.locator('#report-prop-historical-net').count()==0
    page.route(f'**/api/prop-analyses/sources/{id}?discover_exports=false',lambda route:route.fulfill(status=503,json=dict(detail='Controlled saved-analysis load failure')))
    page.reload()
    playwright.expect(page.locator('#report-prop-status')).to_contain_text('Controlled saved-analysis load failure')
    playwright.expect(page.locator('#equity-chart')).to_be_visible()
    playwright.expect(page.locator('#report-net')).to_be_visible()
