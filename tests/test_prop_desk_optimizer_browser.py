"""Saved strategies through combination ranking, equity and sealed report reopen."""

import csv
from decimal import Decimal
from hashlib import sha256
from io import StringIO
import json
from prop_desk_fixtures import desk_calculator_sources

from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser, page, playwright, portal
from test_prop_desk_optimizer import optimizer_members


def test_combination_optimizer_product_journey(page, portal, tmp_path, desk_calculator_sources):
    evidence = tmp_path / 'prop-desk-subset-evidence'
    evidence.mkdir()
    root = portal['url']
    with ResearchHTTPClient(base_url=root, timeout=60) as client:
        dataset, members = optimizer_members(client)
    page.goto(root + '/#backtests/report/' + members[0]['source_backtest_id'])
    playwright.expect(page.locator('#report-summary')).to_be_visible()
    page.locator('.sidebar').get_by_role('link', name='Prop Desk', exact=True).click()
    desk = page.locator('#prop-desk-screen')
    playwright.expect(desk.get_by_label('Simulation mode')).to_have_count(0)
    playwright.expect(desk.get_by_role('heading', name='Simulation', exact=True)).to_be_visible()
    picker = desk.get_by_role('combobox', name='Qualified configuration')
    simulation = desk.get_by_role('button', name='Run simulation', exact=True)
    playwright.expect(simulation).to_be_visible()
    run = desk.get_by_role('button', name='Run Optimise', exact=True)
    optimise = desk.get_by_role('button', name='Optimise', exact=True)
    picker.select_option(members[0]['source_backtest_id'])
    desk.get_by_role('button', name='Add to portfolio', exact=True).click()
    page.screenshot(path=evidence / 'simulation-desktop.png', full_page=True)
    optimise.click()
    desk.get_by_label('Allocation search').select_option('legacy')
    playwright.expect(run).to_be_enabled()
    playwright.expect(simulation).to_have_count(0)
    playwright.expect(desk.get_by_role('heading', name='Search settings')).to_be_visible()
    playwright.expect(desk.get_by_text('rank them by in-sample pass probability', exact=False)).to_be_visible()
    playwright.expect(desk.get_by_role('heading', name='Candidate pool')).to_be_visible()
    playwright.expect(desk.get_by_role('button', name='Remove member 1')).to_be_visible()
    for member in members[1:]:
        picker.select_option(member['source_backtest_id'])
        desk.get_by_role('button', name='Add to candidate pool', exact=True).click()
    desk.get_by_role('link', name='← Simulation').click()
    playwright.expect(desk.get_by_role('heading', name='Portfolio', exact=True)).to_be_visible()
    playwright.expect(simulation).to_be_visible()
    playwright.expect(desk.get_by_role('button', name='Remove member 2')).to_have_count(0)
    optimise.click()
    playwright.expect(desk.get_by_role('button', name='Remove member 3')).to_be_visible()
    desk.get_by_label('Minimum total MNQ').fill('2')
    desk.get_by_label('Maximum total MNQ').fill('3')
    count = desk.locator('#prop-desk-workload')
    playwright.expect(count).to_have_text('7 combinations · 14 combination-size pairs')
    desk.get_by_label('At least this many strategies per combination').fill('2')
    playwright.expect(count).to_have_text('4 combinations · 8 combination-size pairs')
    desk.get_by_label('At least this many strategies per combination').fill('1')
    desk.get_by_role('button', name='Remove member 3').click()
    playwright.expect(count).to_have_text('3 combinations · 6 combination-size pairs')
    picker.select_option(members[2]['source_backtest_id'])
    desk.get_by_role('button', name='Add to candidate pool', exact=True).click()
    desk.get_by_label('Maximum total MNQ').fill('60')
    playwright.expect(count).to_contain_text('Limit 48')
    playwright.expect(run).to_be_disabled()
    desk.get_by_label('Maximum total MNQ').fill('3')

    endpoint = '**/api/prop-desk/optimizer/subsets'
    playwright.expect(desk.get_by_label('Include linked OOS equity')).to_be_checked()
    playwright.expect(desk.get_by_role('link', name='Open OOS backtest report · 2026-01-15 to 2026-01-15')).to_have_count(3)
    page.evaluate('scrollTo(0,0)')
    page.screenshot(path=evidence / 'setup-desktop.png', full_page=True)

    saved = {}
    for phase in ('evaluation', 'funded'):
        name = phase.title()
        if phase == 'funded':
            page.set_viewport_size({'width':390, 'height':844})
            desk.get_by_role('link', name='← Optimise', exact=True).click()
            desk.get_by_role('button', name='Funded', exact=True).click()
            playwright.expect(desk.get_by_text('rank them by in-sample payout probability', exact=False)).to_be_visible()
            playwright.expect(desk.get_by_label('Observation horizon (trading days)')).to_have_value('261')
            size_rule = desk.get_by_label('Funded size rule')
            playwright.expect(size_rule).to_have_value('first_year')
            size_rule.select_option('account_life')
            page.screenshot(path=evidence / 'optimise-mobile.png', full_page=True)
        with page.expect_response(endpoint, timeout=30000) as launched:
            run.click()
        assert launched.value.status == 202, launched.value.text()
        job = launched.value.json()
        assert 'check_sha256' not in launched.value.request.post_data_json
        assert launched.value.request.post_data_json['members'] == members
        saved[phase] = job['id']
        (evidence / f'{phase}-launch.json').write_text(json.dumps(dict(
            request=launched.value.request.post_data_json, response=job), indent=2))
        playwright.expect(desk.get_by_role('heading', name=name + ' combination rankings')).to_be_visible(timeout=60000)
        table = desk.get_by_role('region', name=name + ' combination rankings')
        playwright.expect(table.get_by_role('row')).to_have_count(8)
        playwright.expect(table.get_by_role('row').nth(1)).to_contain_text('1 (within 1 SE)')
        playwright.expect(table.get_by_role('columnheader',
            name='OOS pass' if phase == 'evaluation' else 'OOS any payout', exact=True)).to_be_visible()
        if phase == 'funded':
            playwright.expect(table.get_by_role('columnheader', name='Any payout', exact=True)).to_be_visible()
        button = table.get_by_role('button', name='Inspect combination 6 at 2 MNQ', exact=True)
        button.click()
        playwright.expect(button).to_have_attribute('aria-pressed', 'true')
        playwright.expect(desk.get_by_label('Inspect tested size')).to_have_value('2')
        desk.get_by_label('Inspect tested size').select_option('3')
        playwright.expect(desk.get_by_label('Inspect tested size')).to_have_value('3')
        playwright.expect(desk.get_by_text('$3,591.00', exact=True)).to_be_visible()
        playwright.expect(desk.get_by_role('img', name='Portfolio and members historical closed-trade equity')).to_be_visible()
        playwright.expect(desk).to_contain_text('OOS chart · 2026-01-15')
        url = root + '/api/prop-analyses/' + job['id']
        download = desk.get_by_role('link', name='Admitted trades for this size ↓')
        ledger = page.request.get(root + download.get_attribute('href'))
        assert ledger.ok
        rows = list(csv.DictReader(StringIO(ledger.text())))
        assert len(rows) == 9 and sum(Decimal(row['net_pnl']) for row in rows) == Decimal('3591')
        (evidence / f'{phase}-admitted-trades.csv').write_bytes(ledger.body())
        report = page.request.get(url + '/downloads/report.json')
        assert report.ok
        saved_optimizer = report.json()['optimizer']
        assert saved_optimizer['size_rule'] == ('optimal' if phase == 'evaluation' else 'account_life')
        assert saved_optimizer['workload'] == dict(combinations=7, pairs=14)
        assert len(saved_optimizer['ranking']) == 7 and saved_optimizer['unranked'] == []
        assert [(row['combination'], row['micros'], row['score']) for row in saved_optimizer['ranking'][:3]] == [
            (2, 2, 1), (3, 2, 1), (6, 2, 1)]
        assert all(row['score'] == 0 for row in saved_optimizer['ranking'][3:])
        (evidence / f'{phase}-report.json').write_bytes(report.body())
        with page.expect_download() as archive:
            desk.get_by_role('link', name='All evidence ZIP ↓').click()
        archive.value.save_as(evidence / f'{phase}-analysis.zip')
        if phase == 'evaluation':
            page.evaluate('scrollTo(0,0)')
            page.screenshot(path=evidence / 'evaluation-desktop.png', full_page=True)

    page.reload()
    playwright.expect(desk.get_by_label('Inspect tested size')).to_have_value('3')
    playwright.expect(desk.get_by_role('button', name='Inspect combination 6 at 2 MNQ')).to_have_attribute('aria-pressed', 'true')
    playwright.expect(desk.get_by_text('$3,591.00', exact=True)).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.evaluate('scrollTo(0,0)')
    page.screenshot(path=evidence / 'funded-mobile-reopened.png', full_page=True)
    page.locator('#prop-desk-header').get_by_role('link', name='Saved runs').click()
    page.locator(f'[data-job-id="{saved["funded"]}"]').get_by_role('link', name='View results').click()
    page.locator('#jobs-detail-content').get_by_role('link', name='Open Prop Desk').click()
    playwright.expect(desk.get_by_role('heading', name='Funded combination rankings')).to_be_visible()

    dataset_csv = page.request.get(root + '/api/datasets/' + dataset['id'] + '/csv')
    assert dataset_csv.ok
    (evidence / 'SYNTHETIC-optimizer.csv').write_bytes(dataset_csv.body())
    (evidence / 'journey.json').write_text(json.dumps(dict(members=members, analysis_ids=saved,
        evidence_type='Synthetic local subset workflow. Bridge labels and subset counts were checked separately.',
        sha256={file.name:sha256(file.read_bytes()).hexdigest() for file in sorted(evidence.iterdir())}), indent=2))
