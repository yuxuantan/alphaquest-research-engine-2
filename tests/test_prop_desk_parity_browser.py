"""Normal Simulation presets, frozen row OOS, and standalone diagnostics."""

import csv
from hashlib import sha256
from io import StringIO
import json

import httpx
import pytest
from prop_desk_fixtures import desk_calculator_sources

from test_backtests_browser import browser, page, playwright, portal
from test_prop_desk_basket import run
from test_prop_desk_oos_browser import SUBSETS, normal_sources


def test_prop_desk_presets_and_row_oos(page, portal, monkeypatch, tmp_path, desk_calculator_sources):
    root = portal['url']
    evidence = tmp_path / 'prop-desk-parity-evidence'
    evidence.mkdir()
    desk = page.locator('#prop-desk-screen')
    with httpx.Client(base_url=root, timeout=90) as client:
        raw, members = normal_sources(client)
        alternate_raw, alternate = normal_sources(client, empty_oos=True)
        (evidence/'SYNTHETIC-winning.csv').write_bytes(raw)
        (evidence/'SYNTHETIC-flat.csv').write_bytes(alternate_raw)

        def no_parse(*args, **kwargs):
            pytest.fail('Running with warm sources must use the session inventory.')

        monkeypatch.setattr('alphaquest.research_folds.read_bars', no_parse)
        page.goto(root + '/#prop-desk')
        first = members[0]['source_backtest_id']
        def add_members():
            for member in members:
                desk.locator(f'[data-source="{member["source_backtest_id"]}"]').get_by_role('button', name='Add').click()

        card = desk.locator(f'[data-source="{first}"]')
        card.drag_to(desk.locator('#prop-desk-members'))
        playwright.expect(desk.get_by_label('Weight for member 1')).to_be_visible()
        desk.get_by_role('button', name='Clear', exact=True).click()
        playwright.expect(desk.get_by_label('Weight for member 1')).to_have_count(0)
        add_members()
        desk.get_by_label('Account profile').select_option('lucidflex-50k')
        desk.get_by_role('button', name='30 days', exact=True).click()
        playwright.expect(desk.get_by_label('Observation horizon (trading days)')).to_have_value('30')
        desk.get_by_label('Account profile').select_option('apex-50k-eod')
        desk.get_by_label('Simulation size rule').select_option('optimal')
        desk.get_by_label('Minimum total MNQ').fill('4')
        desk.get_by_label('Maximum total MNQ').fill('5')
        with page.expect_response('**/api/prop-desk/basket') as launch:
            desk.get_by_role('button', name='Run simulation').click()
        assert launch.value.status == 202, launch.value.text()
        simulation = launch.value.json()['id']
        playwright.expect(desk.get_by_role('button', name='Optimal · IS-selected 4 MNQ')).to_be_visible(timeout=60000)
        playwright.expect(desk.get_by_label('Inspect tested size')).to_have_value('4')
        playwright.expect(desk.get_by_text('Out of sample account paths', exact=False)).to_be_visible()
        listing = client.get(f'/api/prop-desk/{simulation}').json()['report']
        assert listing['model_version'] == 'prop-desk-simulation-v2'
        assert listing['basket']['selected_micros'] == 4
        values = listing['basket']['sizes'][0]['account_comparison']
        for side in ('is_metrics', 'oos_metrics'):
            assert values[side]['outcome_counts'] == dict(passed=1000, breached=0, provider_expired=0)
            assert values[side]['median_trading_days_to_target'] == 4
        ledger = client.get(f'/api/prop-analyses/{simulation}/files/{values["oos_trades_file"]}')
        row, = csv.DictReader(StringIO(ledger.text))
        assert row['source_backtest_id'] == members[0]['oos_backtest_id']
        assert (float(row['net_pnl']), float(row['commission'])) == (798, 2)
        (evidence/'evaluation-oos-trades.csv').write_bytes(ledger.content)
        desk.get_by_label('Inspect tested size').select_option('5')
        desk.get_by_role('button', name='Optimal · IS-selected 4 MNQ').click()
        playwright.expect(desk.get_by_label('Inspect tested size')).to_have_value('4')
        playwright.expect(desk.get_by_role('img', name='Portfolio and members historical closed-trade equity')).to_be_visible()
        page.screenshot(path=evidence/'evaluation-desktop.png', full_page=True)
        page.reload()
        playwright.expect(desk.get_by_label('Inspect tested size')).to_have_value('4')

        page.set_viewport_size({'width':390, 'height':844})
        desk.get_by_role('link', name='← Prop Desk setup').click()
        add_members()
        desk.get_by_label('Minimum total MNQ').fill('4')
        desk.get_by_label('Maximum total MNQ').fill('5')
        desk.get_by_role('button', name='Funded', exact=True).click()
        desk.get_by_label('Simulation size rule').select_option('first_year')
        with page.expect_response('**/api/prop-desk/basket') as funded_launch:
            desk.get_by_role('button', name='Run simulation').click()
        assert funded_launch.value.status == 202, funded_launch.value.text()
        funded = funded_launch.value.json()['id']
        playwright.expect(desk.get_by_role('button', name='First year · IS-selected 4 MNQ')).to_be_visible(timeout=60000)
        funded_report = client.get(f'/api/prop-desk/{funded}').json()['report']
        funded_oos = funded_report['basket']['sizes'][0]['account_comparison']['oos_metrics']
        assert funded_oos['mean_trader_receipts'] == funded_oos['median_trader_receipts'] == 13000
        assert funded_oos['probability_any_payout'] == 1 and funded_oos['reporting_sessions'] == 261
        assert funded_oos['milestones'][0]['median_trading_day'] == 5
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=evidence/'funded-mobile.png', full_page=True)

        desk.get_by_role('link', name='← Prop Desk setup').click()
        desk.get_by_role('button', name='Optimise', exact=True).click()
        with page.expect_response('**/api/prop-desk/optimizer/subsets') as ranked:
            desk.get_by_role('button', name='Run simulation').click()
        assert ranked.value.status == 202, ranked.value.text()
        search_id = ranked.value.json()['id']
        playwright.expect(desk.get_by_role('columnheader', name='OOS any payout')).to_be_visible(timeout=60000)
        search = client.get(f'/api/prop-desk/{search_id}').json()['report']['optimizer']
        assert search['workload'] == dict(combinations=3, pairs=6)
        scored = search['account_comparison']
        assert scored['oos_days'] == ['2026-01-15'] and set(scored['rows']) == {'1', '2', '3'}
        assert scored['rows']['3']['oos_metrics']['mean_trader_receipts'] == 13000
        base = dict(members=alternate, phase='funded', profile_id='apex-50k-eod',
                    minimum_micros=4, maximum_micros=5, observation_sessions=261, compare_accounts=True)
        changed = run(client, SUBSETS, base)
        alternate_search = changed['report']['optimizer']
        assert alternate_search['ranking_sha256'] == search['ranking_sha256']
        assert alternate_search['account_comparison']['rows']['3']['oos_metrics']['probability_any_payout'] == 0
        missing = run(client, SUBSETS, dict(base, members=[members[0], dict(members[1], oos_backtest_id=None)]))
        unavailable = missing['report']['optimizer']['account_comparison']['rows']['3']
        assert unavailable['unavailable'] == 'No linked OOS backtest for ' + members[1]['source_backtest_id'][:8] + '.'
        assert 'oos_metrics' not in unavailable
        with page.expect_download() as download:
            desk.get_by_role('link', name='All evidence ZIP ↓').click()
        download.value.save_as(evidence/'optimise.zip')
        page.reload()
        playwright.expect(desk.get_by_role('columnheader', name='OOS any payout')).to_be_visible()
        page.screenshot(path=evidence/'optimise-mobile-reopened.png', full_page=True)

        page.goto(root + '/#prop-desk?analysis=' + simulation)
        desk.get_by_label('Diagnostic sizing').select_option('standalone')
        with page.expect_response('**/api/prop-desk/diagnostics') as diagnosed:
            desk.get_by_role('button', name='Run strategy diagnostics').click()
        assert diagnosed.value.status == 202, diagnosed.value.text()
        diagnosis = diagnosed.value.json()['id']
        playwright.expect(desk.get_by_role('heading', name='Held-out trades versus backtest')).to_be_visible(timeout=60000)
        diagnostic = client.get(f'/api/prop-desk/{diagnosis}').json()['report']
        assert diagnostic['configuration']['allocated_mnq'] == 1
        diagnostic_csv = client.get(f'/api/prop-analyses/{diagnosis}/files/strategy_trades.csv')
        assert [float(r['net_pnl']) for r in csv.DictReader(StringIO(diagnostic_csv.text)) if r['role'] == 'oos'] == [399]
        (evidence/'standalone-trades.csv').write_bytes(diagnostic_csv.content)
        page.screenshot(path=evidence/'standalone-mobile.png', full_page=True)
        ids = dict(evaluation=simulation, funded=funded, optimise=search_id,
                   alternate=changed['id'], missing=missing['id'], diagnostic=diagnosis)
        for name, report_id in ids.items():
            actual = client.get(f'/api/prop-analyses/{report_id}/downloads/report.json')
            assert actual.is_success, actual.text
            (evidence/f'{name}.json').write_bytes(actual.content)
        (evidence/'journey.json').write_text(json.dumps(dict(
            analysis_ids=ids, fixture='Synthetic normal saved backtests',
            expected=dict(oos_net=798, diagnostic_oos_net=399, pass_day=4, funded_receipts=13000),
            sha256={p.name:sha256(p.read_bytes()).hexdigest() for p in sorted(evidence.iterdir())}), indent=2))
