"""Rendered equity axes adapt to financial ranges without altering saved results."""

from research_fixtures import ResearchHTTPClient

from decimal import Decimal

import httpx
import pytest

from test_backtests_browser import browser, page, portal, playwright
from test_backtest_api import body


@pytest.mark.parametrize('values,labels', [
    (('45960.04', '139169.62'), ['25,000', '50,000', '75,000', '100,000', '125,000', '150,000']),
    (('10000', '10000'), ['9,900', '9,950', '10,000', '10,050', '10,100']),
    (('-1250', '-450'), ['-1,400', '-1,200', '-1,000', '-800', '-600', '-400']),
    (('-123.45', '234.56'), ['-200', '-100', '0', '100', '200', '300']),
    (('0.012', '0.018'), ['0.012', '0.014', '0.016', '0.018']),
    (('1000000000000', '1900000000000'), ['1E12', '1.25E12', '1.5E12', '1.75E12', '2E12']),
    (('0.000000012', '0.000000018'), ['1.2E-8', '1.4E-8', '1.6E-8', '1.8E-8']),
    (('10000', '9500'), ['9,400', '9,600', '9,800', '10,000']),
    (('-500', '-500'), ['-505', '-502.5', '-500', '-497.5', '-495']),
    (('0', '0'), ['-1', '-0.5', '0', '0.5', '1']),
], ids=['screenshot-range', 'flat', 'negative', 'cross-zero', 'fractional', 'large', 'tiny', 'falling', 'flat-negative', 'flat-zero'])
def test_dynamic_equity_axis_labels_bounds_and_mobile_readouts(page, portal, values, labels):
    with ResearchHTTPClient(base_url=portal['url']) as client:
        response = client.post('/api/backtests', json=body(portal['saved']['arithmetic_5m']['id']))
        assert response.status_code == 201, response.text
        record = response.json()
    # Isolate rendering with a bounded chart response representing each range.
    # The real saved fixture report and its API results must remain unchanged.
    points = [{'trade_number': i, 'exit_time_utc': '2026-01-05T10:30:00Z' if i else None,
               'equity': value, 'net_pnl': str(Decimal(value) - Decimal(values[i - 1])) if i else '0'}
              for i, value in enumerate(values)]
    preview = {'items': points, 'peak': max(points, key=lambda p: Decimal(p['equity'])),
               'total': len(points), 'sampled': False}
    page.route('**/chart?*', lambda route: route.fulfill(json=preview))
    page.goto(portal['url'] + '/#backtests/report/' + record['id'])
    playwright.expect(page.locator('#backtest-completion')).to_be_visible()
    axis = page.locator('#equity-chart .chart-y-label')
    playwright.expect(axis).to_have_text(labels)
    chart = page.locator('#equity-chart')
    assert float(chart.get_attribute('data-y-min')) <= min(map(float, values))
    assert float(chart.get_attribute('data-y-max')) >= max(map(float, values))
    assert chart.evaluate("el => el.querySelector('polyline').getAttribute('points').split(' ').every(p => { const y = Number(p.split(',')[1]); return Number.isFinite(y) && y >= 29.999 && y <= 235.001; })")
    chart.focus()
    page.keyboard.press('Home')
    playwright.expect(page.locator('#chart-readout')).to_contain_text('Equity ' + values[0] + ' CU')
    page.keyboard.press('End')
    playwright.expect(page.locator('#chart-readout')).to_contain_text('Equity ' + values[-1] + ' CU')
    page.set_viewport_size({'width': 390, 'height': 844})
    playwright.expect(axis).to_have_text(labels)
    assert axis.evaluate_all('els => els.every(el => el.getBBox().x >= 0)')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    with ResearchHTTPClient(base_url=portal['url']) as client:
        assert client.get('/api/backtests/' + record['id']).json() == record
