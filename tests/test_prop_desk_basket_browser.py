"""Normal Prop Desk basket setup, overlap rule, sweep and saved chart."""
import csv
from hashlib import sha256
from io import StringIO
import json
from prop_desk_fixtures import desk_calculator_sources

from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser, page, playwright, portal
from test_prop_desk_basket import saved_members


def test_basket_product_equity_sizing_and_reopen(page, portal, tmp_path, desk_calculator_sources):
    evidence = tmp_path / 'prop-desk-basket-evidence'
    evidence.mkdir()
    root = portal['url']
    with ResearchHTTPClient(base_url=root, timeout=45) as client:
        dataset, members = saved_members(client)
    page.goto(root + '/#backtests/report/' + members[0]['source_backtest_id'])
    playwright.expect(page.locator('#report-summary')).to_be_visible()
    page.locator('.sidebar').get_by_role('link', name='Prop Desk', exact=True).click()
    desk = page.locator('#prop-desk-screen')
    playwright.expect(desk.get_by_label('Simulation mode')).to_have_count(0)
    playwright.expect(desk.get_by_role('heading', name='Simulation', exact=True)).to_be_visible()
    picker = desk.get_by_role('combobox', name='Qualified configuration')
    check = desk.get_by_role('button', name='Check source', exact=True)
    run = desk.get_by_role('button', name='Run simulation', exact=True)
    playwright.expect(check).to_have_count(0)
    playwright.expect(run).to_be_disabled()
    first = members[0]['source_backtest_id']
    pairings = {member['source_backtest_id']: member['oos_backtest_id'] for member in members}
    for offset in range(2):
        response = page.request.get(f'{root}/api/prop-desk/sources?offset={offset}&limit=1').json()
        item, = response['items']
        assert response['total'] == 2 and item['oos']['id'] == pairings[item['id']]
    for oos_id in pairings.values():
        playwright.expect(desk.locator(f'[data-source="{oos_id}"]')).to_have_count(0)
    playwright.expect(desk.locator(f'[data-source="{first}"]').get_by_text('OOS linked')).to_be_visible()
    desk.get_by_role('button', name='Add Consecutive green hold ' + first[:8]).click()
    picker.select_option(members[1]['source_backtest_id'])
    desk.get_by_role('button', name='Add to portfolio', exact=True).click()
    playwright.expect(desk.get_by_role('heading', name='Portfolio', exact=True)).to_be_visible()
    desk.get_by_role('button', name='Equal weight').click()
    desk.get_by_label('Weight for member 1').fill('2')
    desk.get_by_label('Minimum total MNQ').fill('3')
    desk.get_by_label('Maximum total MNQ').fill('5')
    playwright.expect(desk.get_by_label('Include linked OOS equity')).to_be_checked()
    playwright.expect(desk.get_by_role('link', name='Open OOS backtest report · 2026-01-15 to 2026-01-15')).to_have_count(2)
    page.evaluate('scrollTo(0,0)')
    page.screenshot(path=evidence / 'setup-desktop.png', full_page=True)
    ids = {}
    for phase in ('evaluation', 'funded'):
        if phase == 'funded':
            page.set_viewport_size({'width': 390, 'height': 844})
            desk.get_by_role('link', name='← Prop Desk setup').click()
            desk.get_by_role('button', name='Funded', exact=True).click()
            desk.get_by_label('Observation horizon (trading days)').fill('261')
        with page.expect_response('**/api/prop-desk/basket') as launched:
            run.click()
        assert launched.value.status == 202
        assert 'check_sha256' not in launched.value.request.post_data_json
        assert launched.value.request.post_data_json['members'] == members
        (evidence / f'{phase}-launch.json').write_text(json.dumps(dict(
            request=launched.value.request.post_data_json, response=launched.value.json()), indent=2))
        playwright.expect(desk.get_by_role('heading', name=f'{phase.title()} basket results')).to_be_visible(timeout=30000)
        ids[phase] = page.url.split('analysis=', 1)[1].split('&', 1)[0]
        url = root + '/api/prop-analyses/' + ids[phase]
        selector = desk.get_by_label('Inspect tested size')
        playwright.expect(desk.get_by_text('$5,382.00', exact=True)).to_be_visible()
        slider = desk.get_by_role('slider',name='Tested size slider')
        slider.press('End')
        playwright.expect(selector).to_have_value('5')
        playwright.expect(slider).to_have_attribute('aria-valuetext', '5 MNQ')
        playwright.expect(desk.get_by_text('$8,073.00', exact=True)).to_be_visible()
        playwright.expect(desk.get_by_role('img', name='Portfolio and members historical closed-trade equity')).to_be_visible()
        member_curve = desk.get_by_role('button', name='Member 1', exact=True)
        member_curve.click()
        playwright.expect(member_curve).to_have_attribute('aria-pressed', 'false')
        member_curve.click()
        playwright.expect(desk).to_contain_text('OOS chart · 2026-01-15')
        ledger = page.request.get(url + '/files/admitted_trades_5.csv')
        assert ledger.ok
        rows = list(csv.DictReader(StringIO(ledger.text())))
        assert len(rows) == 9 and sum(float(row['net_pnl']) for row in rows) == 8073
        if phase == 'funded':
            playwright.expect(desk.get_by_role('heading', name='Payout milestones')).to_be_visible()
            playwright.expect(desk.get_by_role('img', name='Trader receipts by total MNQ')).to_be_visible()
            playwright.expect(desk).to_contain_text('First-year mean trader receipts')
        with page.expect_download() as archive:
            desk.get_by_role('link', name='All evidence ZIP ↓').click()
        archive.value.save_as(evidence / f'{phase}-analysis.zip')
        report = page.request.get(url + '/downloads/report.json')
        assert report.ok
        (evidence / f'{phase}-report.json').write_bytes(report.body())
        page.evaluate('scrollTo(0,0)')
        display = 'mobile' if phase == 'funded' else 'desktop'
        page.screenshot(path=evidence / f'{phase}-{display}.png', full_page=True)

    page.set_viewport_size({'width': 390, 'height': 844})
    page.reload()
    playwright.expect(desk.get_by_label('Inspect tested size')).to_have_value('5')
    playwright.expect(desk.get_by_text('$8,073.00', exact=True)).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    playwright.expect(page.locator('.mobile-nav').get_by_role('link', name='Prop Desk', exact=True)).to_be_visible()
    page.evaluate('scrollTo(0,0)')
    page.screenshot(path=evidence / 'funded-mobile-reopened.png', full_page=True)
    dataset_csv = page.request.get(root + '/api/datasets/' + dataset['id'] + '/csv')
    assert dataset_csv.ok
    (evidence / 'SYNTHETIC-basket.csv').write_bytes(dataset_csv.body())
    (evidence / 'journey.json').write_text(json.dumps(dict(members=members, analysis_ids=ids,
        evidence_type='Synthetic product demonstration; Bridge parity unverified.',
        sha256={file.name: sha256(file.read_bytes()).hexdigest() for file in sorted(evidence.iterdir())}), indent=2))
