"""Actual upload -> IS backtest -> benchmark -> manual OOS -> saved downloads."""

import hashlib
import json
from time import sleep

from test_backtests_browser import browser, page, portal, playwright
from test_market_benchmark import EXPECTED, FIXTURES, SPLIT
from research_fixtures import declare_in_form


def test_actual_product_market_comparison_and_saved_evidence(page, portal, tmp_path):
    page.goto(portal['url'])
    page.locator('#csv-file').set_input_files(str(FIXTURES / 'SYNTHETIC-holding-IS-OOS.csv'))
    page.locator('#dataset-name').fill('SYNTHETIC holding comparison')
    page.locator('#symbol').fill('SYNTHETIC')
    page.locator('#source-timezone').select_option('UTC')
    page.locator('#dataset-tick-size').fill('.25')
    page.locator('#dataset-point-value').fill('20')
    page.locator('#validate-button').click()
    playwright.expect(page.locator('#validation-result')).to_contain_text('Validation passed')
    page.locator('#save-button').click()
    playwright.expect(page.locator('#validation-result')).to_contain_text('Dataset saved')
    dataset = next(d for d in page.request.get(portal['url'] + '/api/datasets').json() if d['name'] == 'SYNTHETIC holding comparison')
    page.goto(portal['url'] + '/#backtests/new')
    page.locator('#backtest-dataset').select_option(dataset['id'])
    page.locator('#backtest-strategy').select_option('consecutive_green_hold')
    for key, value in dict(green_bar_count=1, hold_minutes=2, contracts=1).items():
        page.locator('#strategy-' + key).fill(str(value))
    page.locator('#backtest-initial-capital').fill('10000')
    page.locator('#backtest-slippage-ticks').fill('1')
    page.locator('#backtest-commission').fill('1')
    page.locator('#backtest-benchmark-contracts').fill('0')
    assert not page.locator('#backtest-benchmark-contracts').evaluate('(el) => el.checkValidity()')
    page.locator('#backtest-benchmark-contracts').fill('1')
    declare_in_form(page, SPLIT)
    playwright.expect(page.locator('#start-backtest')).to_be_enabled()
    page.screenshot(path=str(tmp_path / 'configured-IS-benchmark.png'), full_page=True)
    page.locator('#start-backtest').click()
    playwright.expect(page.locator('#market-benchmark-results')).to_be_visible(timeout=60000)
    is_id = page.url.rsplit('/', 1)[-1]
    playwright.expect(page.locator('#market-benchmark-status')).to_contain_text('Executable futures performance unverified')
    playwright.expect(page.locator('#market-benchmark-metrics tr[data-metric="net_pnl"]')).to_contain_text('168')
    playwright.expect(page.locator('#market-benchmark-metrics tr[data-metric="net_pnl"]')).to_contain_text('188')
    playwright.expect(page.locator('#market-benchmark-metrics tr[data-metric="max_drawdown_amount"]')).to_contain_text('226')
    playwright.expect(page.locator('#market-benchmark-metrics tr[data-metric="max_drawdown_amount"]')).to_contain_text('220')
    playwright.expect(page.locator('#market-benchmark-excess')).to_contain_text('-20')
    playwright.expect(page.locator('#report-drawdown-amount')).to_have_text('0')
    page.locator('#market-benchmark-chart').focus()
    page.keyboard.press('Home')
    playwright.expect(page.locator('#market-benchmark-readout')).to_contain_text('Initial balance')
    page.keyboard.press('ArrowRight')
    page.keyboard.press('ArrowRight')
    playwright.expect(page.locator('#market-benchmark-readout')).to_contain_text('Strategy 9774.00 CU · Holding 9794.00 CU')
    page.locator('#report-market-benchmark').screenshot(path=str(tmp_path / 'IS-market-comparison.png'))
    page.locator('#market-benchmark-view').select_option('excess')
    playwright.expect(page.locator('#market-benchmark-chart polyline')).to_have_count(1)
    page.locator('#report-market-benchmark').screenshot(path=str(tmp_path / 'IS-excess-net.png'))
    files = {}
    for suffix, selector in [('comparison.json', '#market-benchmark-json'), ('equity.csv', '#market-benchmark-csv')]:
        with page.expect_download() as downloaded:
            page.locator(selector).click()
        destination = tmp_path / ('IS-' + suffix)
        downloaded.value.save_as(destination)
        files[destination.name] = hashlib.sha256(destination.read_bytes()).hexdigest()
    comparison = json.loads((tmp_path / 'IS-comparison.json').read_text())
    assert float(comparison['accounts']['holding']['net_pnl']) == 188
    assert comparison['observed_bar_count'] == 4
    assert page.request.get(portal['url'] + '/api/backtests/' + is_id + '/oos').json()['used'] == 0
    # Delayed asset delivery must not let the report-loaded event precede the
    # comparison listener when opening an existing report directly.
    def delayed_script(route):
        sleep(.3)
        route.continue_()
    page.route('**/static/market-benchmark.js*', delayed_script)
    page.reload()
    playwright.expect(page.locator('#market-benchmark-results')).to_be_visible()
    page.unroute('**/static/market-benchmark.js*', delayed_script)
    assert page.request.get(portal['url'] + '/api/backtests/' + is_id + '/exports/market_benchmark').body() == (tmp_path / 'IS-comparison.json').read_bytes()
    page.once('dialog', lambda dialog: dialog.accept())
    page.locator('#report-run-oos').click()
    playwright.expect(page.locator('#report-research-title')).to_have_text('Out-of-sample backtest', timeout=60000)
    playwright.expect(page.locator('#market-benchmark-context')).to_contain_text('OOS period only')
    playwright.expect(page.locator('#market-benchmark-metrics tr[data-metric="net_pnl"]')).to_contain_text('388')
    oos_id = page.url.rsplit('/', 1)[-1]
    page.locator('#report-market-benchmark').screenshot(path=str(tmp_path / 'OOS-market-comparison.png'))
    for kind in ['market_benchmark', 'market_equity', 'report']:
        response = page.request.get(portal['url'] + '/api/backtests/' + oos_id + '/exports/' + kind)
        assert response.status == 200
        (tmp_path / ('OOS-' + kind + ('.csv' if kind == 'market_equity' else '.json'))).write_bytes(response.body())
    assert page.request.delete(portal['url'] + '/api/datasets/' + dataset['id']).status == 204
    page.reload()
    playwright.expect(page.locator('#market-benchmark-results')).to_be_visible()
    playwright.expect(page.locator('#market-benchmark-metrics tr[data-metric="net_pnl"]')).to_contain_text('388')
    page.set_viewport_size(dict(width=390, height=844))
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('#report-market-benchmark').screenshot(path=str(tmp_path / 'OOS-mobile.png'))
    (tmp_path / 'SYNTHETIC-source.csv').write_bytes((FIXTURES / 'SYNTHETIC-holding-IS-OOS.csv').read_bytes())
    (tmp_path / 'independent-expected.json').write_text(json.dumps(EXPECTED, indent=2))
    (tmp_path / 'verification.json').write_text(json.dumps(dict(synthetic=True, is_id=is_id, oos_id=oos_id, expected=EXPECTED,
                                                              downloads_sha256=files, reopened_after_dataset_deletion=True,
                                                              manual_oos_only=True, delayed_script_reload_verified=True, mobile_no_page_overflow=True), indent=2))
