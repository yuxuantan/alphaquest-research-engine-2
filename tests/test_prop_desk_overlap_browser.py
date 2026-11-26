"""Normal Prop Desk journeys with two overlapping saved strategies."""

import csv
from io import StringIO
import json

import httpx
import pytest
from prop_desk_fixtures import desk_calculator_sources

from test_backtests_browser import browser, page, playwright, portal
from test_prop_desk_oos_browser import normal_sources
from test_prop_phases import phase_history


def test_sequential_overlap_screen_and_reopen(page, portal, tmp_path, monkeypatch, desk_calculator_sources):
    root = portal['url']
    evidence = tmp_path / 'prop-desk-overlap'
    evidence.mkdir()
    raw = phase_history(days=9).replace(b'100,250,100,250', b'100,250,-50,250')
    (evidence / 'SYNTHETIC-overlap.csv').write_bytes(raw)
    desk = page.locator('#prop-desk-screen')
    with httpx.Client(base_url=root, timeout=90) as client:
        _, members = normal_sources(client, raw=raw)

        def unexpected_bar_parse(*args, **kwargs):
            pytest.fail('Warm Prop Desk sources should reuse the observed session inventory.')

        monkeypatch.setattr('alphaquest.research_folds.read_bars', unexpected_bar_parse)
        page.goto(root + '/#prop-desk')

        for phase in ('evaluation', 'funded'):
            if phase == 'funded':
                page.set_viewport_size({'width':390, 'height':844})
                desk.get_by_role('link', name='← Prop Desk setup').click()
                desk.get_by_role('button', name='Optimise', exact=True).click()
                desk.get_by_label('Allocation search').select_option('legacy')
                desk.get_by_role('button', name='Funded', exact=True).click()
            for member in members:
                desk.locator(f'[data-source="{member["source_backtest_id"]}"]').get_by_role('button', name='Add').click()
            desk.get_by_label('Overlapping trades').select_option('sequential_mae')
            desk.get_by_label('Minimum total MNQ').fill('4')
            desk.get_by_label('Maximum total MNQ').fill('4')
            optimise = phase == 'funded'
            endpoint = '/optimizer/subsets' if optimise else '/basket'
            with page.expect_response('**/api/prop-desk' + endpoint) as launched:
                desk.get_by_role('button', name='Run Optimise' if optimise else 'Run simulation', exact=True).click()
            assert launched.value.status == 202, launched.value.text()
            assert launched.value.request.post_data_json['overlap_policy'] == 'sequential_mae'
            analysis_id = launched.value.json()['id']
            if optimise:
                desk.get_by_role('button', name='Inspect combination 3 at 4 MNQ').click(timeout=60000)
            playwright.expect(desk.get_by_text('Overlap risk screen', exact=True)).to_be_visible(timeout=60000)
            base = f'/api/prop-analyses/{analysis_id}'
            files = base + '/files/' + ('combination_3/' if optimise else '')
            chart = client.get(files + 'equity_4.json').json()
            ledger = client.get(files + chart['trades_file'])
            assert ledger.is_success
            rows = list(csv.DictReader(StringIO(ledger.text)))
            assert len(rows) == 18
            assert sum(float(row['net_pnl']) for row in rows) == chart['final_equity_change'] == 9 * (798 + 598)
            assert all(row['overlap'] == row['combined_mae_screen_flag'] == 'True' and
                       row['overlap_mae_incomplete'] == 'False' for row in rows)
            assert {float(row['combined_mae_at_target_usd']) for row in rows} == {1202.0}
            assert chart['overlap_risk']['threshold_usd'] == 1000
            report = client.get(base + '/downloads/report.json')
            assert report.is_success
            assumptions = report.json()
            assert assumptions['model_version'].endswith('-sequential-mae-v1')
            if not optimise:
                assert assumptions['basket']['sizes'][0]['metrics']['median_trading_days_to_target'] == 3
            else:
                pair = assumptions['optimizer']['account_comparison']['rows']['3']
                assert pair['oos_metrics']['probability_any_payout'] == 1
                assert len(list(csv.DictReader(StringIO(client.get(files + pair['oos_trades_file']).text)))) == 2
            (evidence / f'{phase}-trades.csv').write_bytes(ledger.content)
            (evidence / f'{phase}-equity.json').write_text(json.dumps(chart, indent=2))
            (evidence / f'{phase}-report.json').write_bytes(report.content)
            page.reload()
            playwright.expect(desk.get_by_text('Overlap risk screen', exact=True)).to_be_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=evidence / f'{phase}-reopened.png', full_page=True)
