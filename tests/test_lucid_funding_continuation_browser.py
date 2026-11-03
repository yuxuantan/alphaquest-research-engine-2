"""Slow valid funding through the normal saved report/configure/check/run UI."""
import json
from datetime import date, timedelta

from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser, page, portal, playwright
from test_backtest_api import body


def test_long_evaluation_calibrates_funded_results_and_reopens_with_same_settings(page, portal, tmp_path):
    lines = ['Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol']
    day = date(2026, 1, 5)
    for _ in range(8):
        for minute, prices in ((0, '99,100,99,100'), (1, '100,100.5,100,100.5'), (2, '100.5,100.5,100.5,100.5')):
            lines.append(day.strftime('%m/%d/%Y') + f',18:0{minute},{prices},100,60,40')
        day += timedelta(days=1)
        while day.weekday() > 4:day += timedelta(days=1)
    with ResearchHTTPClient(base_url=portal['url'], timeout=300) as client:
        saved = client.post('/api/datasets', params=dict(filename='SYNTHETIC-slow-funding.csv',
            name='SYNTHETIC $1 per MNQ per day; 3000-session evaluation', symbol='NQ',
            source_timezone='UTC', tick_size='.25', point_value='20'), content=('\n'.join(lines)+'\n').encode())
        assert saved.status_code == 201, saved.text
        request = body(saved.json()['id'])
        request['strategy_parameters'] = dict(green_bar_count=1, hold_minutes=1, contracts=1)
        request['execution_settings'].update(slippage_ticks=0, commission_per_contract_per_side='0')
        response = client.post('/api/backtests', json=request)
        assert response.status_code == 201, response.text
        record = response.json()
    posts = []
    page.on('request', lambda r: posts.append(r.url) if r.method == 'POST' else None)
    page.goto(portal['url'] + '/#backtests/report/' + record['id'])
    page.locator('#report-prop-setup').click()
    playwright.expect(page.locator('#prop-config')).to_be_visible()
    page.locator('#prop-model').select_option('1')
    page.locator('#prop-commission-mode').select_option('source')
    page.locator('#prop-max-nq').fill('0.1')
    page.locator('#prop-slots').fill('4')
    page.locator('#prop-check').click()
    playwright.expect(page.locator('#prop-run')).to_be_enabled()
    page.screenshot(path=str(tmp_path / 'source-check.png'), full_page=True)
    page.locator('#prop-run').click()
    playwright.expect(page.locator('#prop-report')).to_be_visible(timeout=180000)
    id = page.url.rsplit('/', 1)[-1]
    report = page.request.get(portal['url'] + '/api/prop-analyses/' + id + '/downloads/report.json').json()
    c = report['calculations']
    assert c['training_economics']['replacement_days'] == 3000
    assert c['training_economics']['funding_chain_simulations'] == 20000
    assert c['training_economics']['funding_chain_diagnostics']['continued_paths'] == 20000
    assert c['evaluation']['pass_rate'] == 1
    assert c['evaluation']['days_to_funded'] == 3000
    assert c['funded'] is None and c['history'] is None
    assert c['joint_sizing']['status'] == 'unavailable'
    assert c['joint_sizing']['funded_profiles'][0]['method'] == 'analytical_zero_payout_bound'
    playwright.expect(page.get_by_role('tab', name='Sizing', exact=True)).to_be_visible()
    playwright.expect(page.locator('#prop-report-content')).to_contain_text('Funded outcomes are unavailable')
    page.get_by_role('tab', name='Evaluation', exact=True).click()
    playwright.expect(page.locator('#prop-view-evaluation')).to_contain_text('Paths continued beyond 2,000 sessions')
    playwright.expect(page.locator('#prop-view-evaluation')).to_contain_text('3,000 trading days')
    with page.expect_download() as download:
        page.get_by_role('link', name='Download training calibration (JSON)', exact=True).click()
    download.value.save_as(tmp_path / 'training_economics.json')
    page.screenshot(path=str(tmp_path / '3000-session-calibration.png'), full_page=True)
    # The ordinary reconfiguration action retains Lucid and the selected costs,
    # quantity cap, slots and all advanced settings; it never executes a backtest.
    page.get_by_role('link', name='Configure new analysis', exact=True).click()
    playwright.expect(page.locator('#prop-config')).to_be_visible()
    playwright.expect(page.locator('#prop-model')).to_have_value('1')
    playwright.expect(page.locator('#prop-max-nq')).to_have_value('0.1')
    playwright.expect(page.locator('#prop-slots')).to_have_value('4')
    playwright.expect(page.locator('#prop-commission-mode')).to_have_value('source')
    page.locator('#prop-check').click()
    playwright.expect(page.locator('#prop-run')).to_be_enabled()
    page.locator('#prop-run').click()
    playwright.expect(page.locator('#prop-report')).to_be_visible(timeout=30000)
    assert page.url.endswith(id)  # Same current-model request reopens, no recompute.
    posts.clear()
    page.reload()
    playwright.expect(page.locator('#prop-report')).to_be_visible()
    assert not posts
    (tmp_path / 'report.json').write_text(json.dumps(report, indent=2))
    (tmp_path / 'verification.json').write_text(json.dumps(dict(synthetic=True, source_id=record['id'], analysis_id=id,
        expected_replacement_days=3000, observed_replacement_days=c['training_economics']['replacement_days'],
        expected_joint_status='unavailable', observed_joint_status=c['joint_sizing']['status'],
        training_chains=20000, continued_chains=20000, reload_read_only=True), indent=2))
